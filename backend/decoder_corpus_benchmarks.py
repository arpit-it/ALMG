"""Reviewed evaluation-only text snapshots with a fixed corpus tokenizer."""
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import uuid
if __package__:
    from . import decoder_corpus_optimizer as training, decoder_corpus_evaluation as heldout, decoder_corpus_leakage_audit as overlap
    from .decoder_tokenizer import Tokenizer
    from .run_manifest import digest,file_digest
else:
    import decoder_corpus_optimizer as training, decoder_corpus_evaluation as heldout, decoder_corpus_leakage_audit as overlap
    from decoder_tokenizer import Tokenizer
    from run_manifest import digest,file_digest


def _prepare(documents, tokenizer, length):
    if tokenizer.artifact()['format']!='almg-whitespace-tokenizer-v1':raise ValueError('This benchmark version requires the saved word tokenizer.')
    if type(length) is not int or length not in (4,8,16):raise ValueError('Use a reviewed corpus sequence length.')
    if not isinstance(documents,list) or not 1<=len(documents)<=8:raise ValueError('Provide one to eight local benchmark documents.')
    windows=[];sources=[];seen_names=set();seen_tokens=set();blockers=[]
    for document in documents:
        if not isinstance(document,dict) or set(document)!={'name','text','license_basis','permission_note','independent_evaluation_only'}:
            raise ValueError('Provide benchmark name, text, permission basis/note and evaluation-only declaration.')
        name=document['name'];text=document['text'];basis=document['license_basis'];note=document['permission_note']
        if (not isinstance(name,str) or not 1<=len(name)<=120 or not name.strip() or any(ord(c)<32 for c in name) or name in seen_names
            or not isinstance(text,str) or not 1<=len(text)<=16384 or basis not in ('user_created','permission_recorded','needs_review')
            or not isinstance(note,str) or len(note)>512 or type(document['independent_evaluation_only']) is not bool):
            raise ValueError('Invalid or duplicate benchmark document metadata.')
        tokens=tokenizer.encode(text)
        if len(tokens)<2 or tuple(tokens) in seen_tokens:raise ValueError('Benchmark documents require at least two tokens and distinct tokenized contents.')
        seen_names.add(name);seen_tokens.add(tuple(tokens));sha=hashlib.sha256(text.encode('utf-8')).hexdigest()
        if basis=='needs_review' or not note.strip():blockers.append(f'Record source permission and a note for {name}.')
        if document['independent_evaluation_only'] is not True:blockers.append(f'Declare {name} reserved for evaluation, outside training and improvement data.')
        sources.append({'name':name,'source_sha256':sha,'token_count':len(tokens),'license_basis':basis,
                        'permission_note':note,'independent_evaluation_only':document['independent_evaluation_only']})
        for start in range(0,len(tokens)-1,length):
            values=tokens[start:start+length+1];count=len(values)-1
            windows.append({'document_sha256':sha,'group':'evaluation_only','offset':start,
                            'inputs':values[:-1]+[0]*(length-count),'targets':values[1:]+[0]*(length-count),
                            'target_mask':[1]*count+[0]*(length-count)})
            if len(windows)>32:raise ValueError('This benchmark version supports at most 32 document-bound windows.')
    return sources,windows,blockers


def _review(root, corpus_id, documents):
    corpus=training.inputs.read(root,corpus_id);source=corpus['review']['source']
    initialized=training.hardware.initializations.read(root,source['plan_id'],source['initialization_id'])
    _,_,_,existing,tokenizer=training._source(root,initialized,corpus)
    sources,windows,blockers=_prepare(documents,tokenizer,corpus['review']['sequence_length'])
    findings={split:overlap.audit_pair(windows,existing[split],tokenizer) for split in ('train','validation','test')}
    blockers+=['Benchmark windows overlap saved '+split+' windows; provide separate evaluation text.' for split,item in findings.items() if item['overlap_detected']]
    result={'format':'almg-corpus-benchmark-review-v1','schema_version':1,'corpus_id':corpus['id'],'corpus_revision':corpus['revision'],
            'training_data_binding':heldout.data_binding(corpus),'sequence_length':corpus['review']['sequence_length'],
            'tokenizer_sha256':tokenizer.fingerprint(),'sources':sources,'documents_sha256':digest(documents),'windows_sha256':digest(windows),
            'window_count':len(windows),'target_tokens':sum(sum(row['target_mask']) for row in windows),
            'overlap_protocol_revision':digest(overlap.PROTOCOL),'overlap_checks':findings,
            'compatible':not blockers,'blockers':blockers,'purpose':'evaluation_only','tokenizer_refitted':False,
            'independent_evaluation_certified':False,'training_approved':False,'release_approved':False,
            'limitations':'Local user-provided benchmark text with recorded permissions and evaluation-only declarations. Uses the existing saved word tokenizer without refitting or adding training/improvement rows. Exact active-window and within-window four-token-span checks cover all existing corpus splits. No semantic/fuzzy/cross-window/global-usage independence certification. This stage prepares inputs only; it neither scores a model nor approves training/release. Benchmark execution and broader provenance verification remain separate.',
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_corpus_benchmarks.py','decoder_corpus_inputs.py','decoder_corpus_leakage_audit.py','decoder_tokenizer.py')})}
    result['revision']=digest(result)
    return result,windows,tokenizer.artifact()


def review(root, corpus_id, documents):
    return _review(root,corpus_id,documents)[0]


def save(root, corpus_id, confirmed, documents, reviewed):
    if confirmed is not True:raise ValueError('Confirm saving private evaluation-only benchmark inputs.')
    current,windows,tokenizer=_review(root,corpus_id,documents)
    if not isinstance(reviewed,dict) or reviewed!=current:raise ValueError('Benchmark review changed; review the exact text and permissions again.')
    if not current['compatible']:raise ValueError('Resolve benchmark permission, evaluation-only and overlap findings before saving.')
    parent=Path(root)/'decoder-corpus-benchmarks';parent.mkdir(parents=True,exist_ok=True);identifier=uuid.uuid4().hex
    with TemporaryDirectory(prefix='.benchmark-',dir=parent) as temporary:
        folder=Path(temporary)/identifier;folder.mkdir()
        for name,value in (('documents.json',documents),('windows.json',windows),('tokenizer.json',tokenizer)):
            (folder/name).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        record={'format':'almg-saved-corpus-benchmark-v1','schema_version':1,'id':identifier,'review':current,
                'files':{name:file_digest(folder/name) for name in ('documents.json','windows.json','tokenizer.json')}}
        record['revision']=digest(record);(folder/'record.json').write_text(json.dumps(record,allow_nan=False),encoding='utf-8')
        result=_read(folder);folder.rename(parent/identifier)
    return result


def _read(folder):
    if (folder/'record.json').stat().st_size>256000:raise ValueError('Benchmark record exceeds its bounded size.')
    record=json.loads((folder/'record.json').read_text(encoding='utf-8'))
    if (not isinstance(record,dict) or record.get('format')!='almg-saved-corpus-benchmark-v1' or type(record.get('schema_version')) is not int
        or record['schema_version']!=1 or record.get('id')!=folder.name or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})
        or set(record.get('files',{}))!={'documents.json','windows.json','tokenizer.json'}):raise ValueError('Invalid saved benchmark manifest.')
    for name,sha in record['files'].items():
        if (folder/name).stat().st_size>2*1024**2 or file_digest(folder/name)!=sha:raise ValueError('Saved benchmark content changed.')
    reviewed=record['review'];documents=json.loads((folder/'documents.json').read_text(encoding='utf-8'))
    tokenizer=Tokenizer.restore(json.loads((folder/'tokenizer.json').read_text(encoding='utf-8')))
    sources,windows,blockers=_prepare(documents,tokenizer,reviewed['sequence_length'])
    if (reviewed.get('format')!='almg-corpus-benchmark-review-v1' or type(reviewed.get('schema_version')) is not int or reviewed['schema_version']!=1
        or reviewed.get('revision')!=digest({k:v for k,v in reviewed.items() if k!='revision'}) or reviewed.get('compatible') is not True or blockers
        or reviewed['documents_sha256']!=digest(documents) or reviewed['windows_sha256']!=digest(windows) or reviewed['sources']!=sources
        or reviewed['tokenizer_sha256']!=tokenizer.fingerprint() or json.loads((folder/'windows.json').read_text(encoding='utf-8'))!=windows
        or reviewed.get('blockers')!=[] or set(reviewed.get('overlap_checks',{}))!={'train','validation','test'}
        or any(item.get('overlap_detected') is not False for item in reviewed['overlap_checks'].values())
        or reviewed.get('purpose')!='evaluation_only' or reviewed.get('tokenizer_refitted') is not False
        or any(reviewed.get(key) is not False for key in ('training_approved','release_approved','independent_evaluation_certified'))):
        raise ValueError('Saved benchmark review or input binding changed.')
    return record


def read(root, identifier):
    if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('Select a saved benchmark ID.')
    return _read(Path(root)/'decoder-corpus-benchmarks'/identifier)
