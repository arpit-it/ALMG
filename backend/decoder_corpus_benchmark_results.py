"""Confirmed immutable benchmark scoring snapshots with historical reads."""
from datetime import datetime,timezone
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import uuid
if __package__:
    from . import decoder_corpus_benchmark_evaluation as evaluation
    from .run_manifest import digest,file_digest
else:
    import decoder_corpus_benchmark_evaluation as evaluation
    from run_manifest import digest,file_digest


def _id(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{32}',value):raise ValueError('Select a saved benchmark, model or evaluation ID.')
    return value


def _validate(report):
    try:
        valid=(report['format']=='almg-corpus-benchmark-evaluation-v1' and type(report['schema_version']) is int and report['schema_version']==1
               and report['revision']==digest({k:v for k,v in report.items() if k!='revision'})
               and report['protocol_revision']==digest(report['protocol'])
               and all(report[key] is False for key in ('training_approved','release_approved','language_quality_validated','independent_evaluation_certified')))
        _id(report['source']['record_id']);_id(report['benchmark_binding']['id'])
        valid=valid and all(isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) for value in
                           (report['source']['record_revision'],report['source']['model_sha256'],report['benchmark_binding']['revision'],report['benchmark_binding']['review_revision']))
        valid=valid and set(report['current_overlap_checks'])=={'train','validation','test'} and all(item['overlap_detected'] is False for item in report['current_overlap_checks'].values())
    except (KeyError,TypeError,ValueError):valid=False
    if not valid:raise ValueError('Saved benchmark evaluation integrity or source binding changed.')


def save(root, benchmark_id, candidate_id, confirmed, reviewed, baseline_id=None, *, baseline_initialization=False):
    if confirmed is not True:raise ValueError('Confirm saving this private benchmark scoring report; this does not approve release.')
    current=evaluation.evaluate(root,benchmark_id,candidate_id,baseline_id,baseline_initialization=baseline_initialization)
    if not isinstance(reviewed,dict) or reviewed!=current:raise ValueError('Benchmark evaluation changed; reopen the exact candidate/baseline report before saving.')
    _validate(current);text=json.dumps(current,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    if len(text.encode('utf-8'))>2*1024**2:raise ValueError('Benchmark evaluation exceeds its bounded size.')
    parent=Path(root)/'decoder-benchmark-evaluations';parent.mkdir(parents=True,exist_ok=True);identifier=uuid.uuid4().hex
    with TemporaryDirectory(prefix='.benchmark-evaluation-',dir=parent) as temporary:
        folder=Path(temporary)/identifier;folder.mkdir();(folder/'report.json').write_text(text,encoding='utf-8')
        record={'format':'almg-saved-benchmark-evaluation-v1','schema_version':1,'id':identifier,
                'created_at':datetime.now(timezone.utc).isoformat(),'source':current['source'],'benchmark_binding':current['benchmark_binding'],
                'report_revision':current['revision'],'files':{'report.json':file_digest(folder/'report.json')},'training_approved':False,'release_approved':False}
        record['revision']=digest(record);(folder/'record.json').write_text(json.dumps(record,allow_nan=False),encoding='utf-8')
        result=_read(folder);folder.rename(parent/identifier)
    return result


def _read(folder):
    if (folder/'record.json').stat().st_size>65536 or (folder/'report.json').stat().st_size>2*1024**2:raise ValueError('Saved benchmark evaluation exceeds its bounded size.')
    record=json.loads((folder/'record.json').read_text(encoding='utf-8'));report=json.loads((folder/'report.json').read_text(encoding='utf-8'));_validate(report)
    if not isinstance(record,dict):raise ValueError('Invalid benchmark evaluation manifest.')
    try:
        if len(record['created_at'])>64 or datetime.fromisoformat(record['created_at']).tzinfo is None:raise ValueError('Invalid timestamp.')
    except (KeyError,TypeError,ValueError):raise ValueError('Invalid saved benchmark evaluation timestamp.') from None
    if (record.get('format')!='almg-saved-benchmark-evaluation-v1' or type(record.get('schema_version')) is not int or record['schema_version']!=1
        or record.get('id')!=folder.name or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})
        or record.get('files')!={'report.json':file_digest(folder/'report.json')} or record.get('source')!=report['source']
        or record.get('benchmark_binding')!=report['benchmark_binding'] or record.get('report_revision')!=report['revision']
        or record.get('training_approved') is not False or record.get('release_approved') is not False):raise ValueError('Saved benchmark evaluation manifest binding changed.')
    return {'record':record,'report':report}


def read(root, identifier):
    return _read(Path(root)/'decoder-benchmark-evaluations'/_id(identifier))


def history(root, benchmark_id, candidate_id):
    _id(benchmark_id);_id(candidate_id);records=[]
    for folder in (Path(root)/'decoder-benchmark-evaluations').glob('[0-9a-f]'*32):
        if not folder.is_dir():continue
        try:record=read(root,folder.name)['record']
        except (OSError,ValueError,KeyError,TypeError):continue
        if record['source']['record_id']==candidate_id and record['benchmark_binding']['id']==benchmark_id:records.append(record)
    return sorted(records,key=lambda item:(item['created_at'],item['id']),reverse=True)[:20]
