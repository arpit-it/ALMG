"""Bounded offline JSONL text import with original-byte and line provenance."""
import base64
import hashlib
import json
from pathlib import Path
import platform

if __package__:
    from . import decoder_datasets as datasets
    from .run_manifest import digest,file_digest
else:
    import decoder_datasets as datasets
    from run_manifest import digest,file_digest


def _object(pairs):
    if len(pairs)!=1 or pairs[0][0]!='text' or not isinstance(pairs[0][1],str):
        raise ValueError('Each JSONL record must contain exactly one string field named text; metadata is not silently discarded.')
    return {'text':pairs[0][1]}


def _extract(documents):
    if not isinstance(documents,list) or not 1<=len(documents)<=16:raise ValueError('Select 1 to 16 local JSONL files.')
    extracted=[];sources=[];names=set();total=extracted_bytes=0
    for number,document in enumerate(documents,1):
        if not isinstance(document,dict) or set(document)!={'name','data'}:raise ValueError('Provide named original JSONL bytes.')
        name=document['name'];data=document['data']
        if (not isinstance(name,str) or not 1<=len(name)<=255 or not name.lower().endswith('.jsonl') or name in names
                or not isinstance(data,str) or len(data)>90000):raise ValueError('Select uniquely named bounded UTF-8 .jsonl files.')
        names.add(name);raw=base64.b64decode(data,validate=True);total+=len(raw)
        if len(raw)>65536 or total>128000:raise ValueError('Each JSONL file must fit 64 KiB; the selection must fit 128000 bytes.')
        raw.decode('utf-8');records=[];blank=0
        # Split on LF only: Unicode line separators inside JSON strings are content.
        lines=raw.split(b'\n')
        if lines and lines[-1]==b'':lines.pop()
        for line_number,line in enumerate(lines,1):
            text=line.decode('utf-8')
            if line_number==1:text=text.removeprefix('\ufeff')
            if not text.strip():blank+=1;continue
            try:
                row=json.loads(text,object_pairs_hook=_object)
                if not isinstance(row,dict):raise ValueError('Expected an object containing text.')
                body=row['text'];encoded=body.encode('utf-8')
                if not body.strip() or len(encoded)>65536:raise ValueError('Text must be nonempty and fit 64 KiB.')
            except (ValueError,TypeError,UnicodeError,RecursionError) as error:
                raise ValueError(f'{name}, line {line_number}: {error}') from error
            extracted_bytes+=len(encoded)
            if len(extracted)>=16 or extracted_bytes>128000:raise ValueError('Import 3 to 16 text records totaling at most 128000 extracted bytes.')
            document_name=f'{number}-{name[:220]}#L{line_number}'
            extracted.append({'name':document_name,'text':body})
            records.append({'line':line_number,'document_name':document_name,'raw_line_sha256':hashlib.sha256(line).hexdigest(),
                            'extracted_source_sha256':hashlib.sha256(encoded).hexdigest(),'extracted_bytes':len(encoded),
                            'preview':body[:512],'preview_truncated':len(body)>512})
        if not records:raise ValueError(f'No text records in {name}.')
        sources.append({'name':name,'original_source_sha256':hashlib.sha256(raw).hexdigest(),'original_bytes':len(raw),
                        'blank_lines':blank,'records':records})
    if len(extracted)<3:raise ValueError('Import at least three text records for train, validation and test partitioning.')
    return extracted,sources


def review(documents):
    extracted,sources=_extract(documents)
    record={'format':'almg-local-jsonl-extraction-review-v1','schema_version':1,'sources':sources,'text_records':len(extracted),
            'method':{'version':1,'encoding':'strict_utf8','record_separator':'LF','schema':{'text':'string'},
                      'unknown_and_duplicate_fields':'rejected','blank_lines':'ignored_and_counted',
                      'network_access':False,'maximum_records':16,
                      'limitations':'Bounded text-only JSONL import, not a streaming importer. Text may contain personal information. Source permission is not verified.'},
            'implementation_sha256':file_digest(Path(__file__)),'python':platform.python_version(),
            'tokenizer_kind':'utf8_bytes','original_jsonl_in_dataset':False,'training_approved':False}
    record['revision']=digest(record);return record


def prepare(root,documents,confirmed,reviewed,*,_dataset_id=None):
    if confirmed is not True:raise ValueError('Confirm the exact local JSONL extraction review.')
    current=review(documents)
    if not isinstance(reviewed,dict) or reviewed!=current:raise ValueError('The JSONL extraction review changed. Select and review the current files.')
    extracted,_=_extract(documents)
    provenance={k:v for k,v in current.items() if k not in ('sources','revision')}
    provenance.update(format='almg-local-jsonl-extraction-provenance-v1',review_revision=current['revision'],sources=[
        {**source,'records':[{k:v for k,v in row.items() if k not in ('preview','preview_truncated')} for row in source['records']]}
        for source in current['sources']])
    provenance['revision']=digest(provenance)
    return datasets.prepare(root,extracted,True,'utf8_bytes',_dataset_id=_dataset_id,_derivation={
        'version':1,'operation':'extract_local_jsonl','extraction_review_revision':current['revision'],
        'extraction_provenance':provenance,'policy':'original_file_and_line_hashes_preserved_no_training_approval'})
