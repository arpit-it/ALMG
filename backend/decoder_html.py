"""Bounded offline HTML text extraction with reviewed original-byte provenance."""
import base64
import hashlib
from html.parser import HTMLParser
import platform
from pathlib import Path

if __package__:
    from . import decoder_datasets as datasets
    from .run_manifest import digest,file_digest
else:
    import decoder_datasets as datasets
    from run_manifest import digest,file_digest

_VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
_SKIP={'script','style','template','noscript','head'}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.stack=[];self.parts=[]

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        hidden=tag in _SKIP or 'hidden' in attrs or str(attrs.get('aria-hidden','')).lower()=='true'
        suppressed=hidden or bool(self.stack and self.stack[-1][1])
        if not suppressed:self.parts.append(' ')
        if tag not in _VOID:
            if len(self.stack)>=128:raise ValueError('HTML nesting exceeds 128 elements.')
            self.stack.append((tag,suppressed))

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in _VOID:self.handle_endtag(tag)

    def handle_endtag(self,tag):
        for index in range(len(self.stack)-1,-1,-1):
            if self.stack[index][0]==tag:
                del self.stack[index:];break
        if not self.stack or not self.stack[-1][1]:self.parts.append(' ')

    def handle_data(self,data):
        if not self.stack or not self.stack[-1][1]:self.parts.append(data)


def _extract(documents):
    if not isinstance(documents,list) or not 3<=len(documents)<=16:raise ValueError('Select 3 to 16 local HTML documents.')
    extracted=[];sources=[];total=0
    for document in documents:
        if not isinstance(document,dict) or set(document)!={'name','data'}:raise ValueError('Provide a named original HTML byte payload.')
        name=document['name'];data=document['data']
        if (not isinstance(name,str) or not 1<=len(name)<=255 or not name.lower().endswith(('.html','.htm'))
                or not isinstance(data,str) or len(data)>90000):raise ValueError('Select bounded .html or .htm UTF-8 files.')
        raw=base64.b64decode(data,validate=True);total+=len(raw)
        if len(raw)>65536 or total>128000:raise ValueError('Each HTML source must fit 64 KiB; the selection must fit 128000 bytes.')
        text=raw.decode('utf-8').removeprefix('\ufeff')
        parser=_Text();parser.feed(text);parser.close()
        text=' '.join(''.join(parser.parts).split())
        if not text:raise ValueError(f'No extractable body text in {name}.')
        encoded=text.encode('utf-8')
        if len(encoded)>65536:raise ValueError('Extracted HTML text exceeds 64 KiB.')
        extracted.append({'name':name,'text':text})
        sources.append({'name':name,'original_source_sha256':hashlib.sha256(raw).hexdigest(),'original_bytes':len(raw),
                        'extracted_source_sha256':hashlib.sha256(encoded).hexdigest(),'extracted_bytes':len(encoded),
                        'preview':text[:512],'preview_truncated':len(text)>512})
    if sum(source['extracted_bytes'] for source in sources)>128000:raise ValueError('Extracted HTML selection exceeds 128000 bytes.')
    return extracted,sources


def review(documents):
    _,sources=_extract(documents)
    record={'format':'almg-local-html-extraction-review-v1','schema_version':1,'sources':sources,
            'method':{'version':1,'parser':'python_html_parser','encoding':'strict_utf8',
                      'excluded':['head','script','style','template','noscript','comments','hidden_attribute','aria_hidden_true'],
                      'maximum_nesting':128,'network_access':False,'linked_resources_fetched':False,
                      'limitations':'Static tag text only; no browser rendering, CSS/layout or JavaScript execution. Other personal information may remain.'},
            'implementation_sha256':file_digest(Path(__file__)),'python':platform.python_version(),
            'tokenizer_kind':'utf8_bytes','original_html_in_dataset':False,'training_approved':False}
    record['revision']=digest(record)
    return record


def prepare(root,documents,confirmed,reviewed,*,_dataset_id=None):
    if confirmed is not True:raise ValueError('Confirm the exact local HTML extraction review.')
    current=review(documents)
    if not isinstance(reviewed,dict) or reviewed!=current:raise ValueError('The HTML extraction review changed. Reopen it before preparation.')
    extracted,_=_extract(documents)
    provenance={k:v for k,v in current.items() if k not in ('sources','revision')}
    provenance.update(format='almg-local-html-extraction-provenance-v1',review_revision=current['revision'],
                      sources=[{k:v for k,v in source.items() if k not in ('preview','preview_truncated')} for source in current['sources']])
    provenance['revision']=digest(provenance)
    # Keep the reviewed identity and independently hash the preview-free provenance.
    return datasets.prepare(root,extracted,True,'utf8_bytes',_dataset_id=_dataset_id,_derivation={
        'version':1,'operation':'extract_local_html','extraction_review_revision':current['revision'],
        'extraction_provenance':provenance,'policy':'original_hashes_preserved_no_training_approval'})
