"""Explicitly saved immutable evaluation snapshots; saving never approves release."""
from datetime import datetime,timezone
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import uuid
if __package__:
    from . import decoder_corpus_evaluation as heldout, decoder_corpus_generation_evaluation as generation, decoder_corpus_leakage_audit as leakage
    from .run_manifest import digest,file_digest
else:
    import decoder_corpus_evaluation as heldout, decoder_corpus_generation_evaluation as generation, decoder_corpus_leakage_audit as leakage
    from run_manifest import digest,file_digest


def _id(identifier):
    if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('Select a saved evaluation or completed model ID.')
    return identifier


def review(root, identifier):
    _id(identifier)
    loss=heldout.evaluate(root,identifier,baseline_initialization=True)
    generated=generation.evaluate(root,identifier,baseline_initialization=True)
    overlap=leakage.audit(root,loss['corpus_id'])
    result={'format':'almg-corpus-evaluation-review-v1','schema_version':1,
            'source':loss['source'],'corpus_id':loss['corpus_id'],'corpus_revision':loss['corpus_revision'],
            'evaluation_data_binding':loss['evaluation_data_binding'],
            'heldout':loss,'generation':generated,'overlap':overlap,
            'training_approved':False,'release_approved':False,'language_quality_validated':False,
            'scope':'Deterministic bounded pretraining diagnostics with original-initialization baselines. Saving retains this evidence only; overlap findings remain review-needed and no general language-quality or release acceptance is inferred. Timing and process-memory observations are separate reports and are not included.',
            'implementation_sha256':file_digest(Path(__file__))}
    result['revision']=digest(result)
    _validate_report(result)
    return result


def _validate_report(report):
    try:
        valid=(report['format']=='almg-corpus-evaluation-review-v1' and type(report['schema_version']) is int and report['schema_version']==1
               and report['revision']==digest({k:v for k,v in report.items() if k!='revision'})
               and all(report[field] is False for field in ('training_approved','release_approved','language_quality_validated')))
        for name,expected in (('heldout','almg-corpus-heldout-evaluation-v1'),('generation','almg-corpus-generation-evaluation-v1'),('overlap','almg-corpus-leakage-audit-v1')):
            leaf=report[name]
            valid=valid and leaf['format']==expected and type(leaf['schema_version']) is int and leaf['schema_version']==1
            valid=valid and leaf['revision']==digest({k:v for k,v in leaf.items() if k!='revision'}) and leaf['protocol_revision']==digest(leaf['protocol'])
            valid=valid and all(leaf[key]==report[key] for key in ('corpus_id','corpus_revision','evaluation_data_binding'))
            valid=valid and leaf['training_approved'] is False and leaf['release_approved'] is False
            if name!='overlap':
                valid=valid and leaf['source']==report['source'] and leaf['comparison']['baseline_source']['kind']=='original_initialization'
                valid=valid and leaf['comparison']['baseline_source']['optimizer_updates']==0 and leaf['language_quality_validated'] is False
        _id(report['source']['record_id'])
        valid=valid and all(isinstance(report['source'][key],str) and re.fullmatch('[a-f0-9]{64}',report['source'][key]) for key in ('record_revision','model_sha256'))
        valid=valid and report['heldout']['comparison']['baseline_source']==report['generation']['comparison']['baseline_source']
    except (KeyError,TypeError,ValueError):valid=False
    if not valid:raise ValueError('Evaluation report integrity or source/protocol binding changed.')


def save(root, identifier, confirmed, reviewed):
    if confirmed is not True:raise ValueError('Confirm saving this private evaluation snapshot; this does not approve release.')
    current=review(root,identifier)
    if not isinstance(reviewed,dict) or current!=reviewed:raise ValueError('Evaluation review changed; reopen it before saving.')
    text=json.dumps(current,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    if len(text.encode('utf-8'))>2*1024**2:raise ValueError('Evaluation report exceeds its bounded size.')
    parent=Path(root)/'decoder-corpus-evaluations';parent.mkdir(parents=True,exist_ok=True);evaluation_id=uuid.uuid4().hex
    with TemporaryDirectory(prefix='.evaluation-',dir=parent) as temporary:
        folder=Path(temporary)/evaluation_id;folder.mkdir();(folder/'report.json').write_text(text,encoding='utf-8')
        record={'format':'almg-saved-corpus-evaluation-v1','schema_version':1,'id':evaluation_id,
                'created_at':datetime.now(timezone.utc).isoformat(),'source':current['source'],
                'report_revision':current['revision'],'files':{'report.json':file_digest(folder/'report.json')},
                'training_approved':False,'release_approved':False}
        record['revision']=digest(record)
        (folder/'record.json').write_text(json.dumps(record,allow_nan=False),encoding='utf-8')
        result=_read_folder(folder);folder.rename(parent/evaluation_id)
    return result


def _read_folder(folder):
    if (folder/'record.json').stat().st_size>65536 or (folder/'report.json').stat().st_size>2*1024**2:raise ValueError('Saved evaluation exceeds its bounded size.')
    record=json.loads((folder/'record.json').read_text(encoding='utf-8'));report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    _validate_report(report)
    if not isinstance(record,dict):raise ValueError('Invalid saved evaluation manifest.')
    try:
        if len(record['created_at'])>64 or datetime.fromisoformat(record['created_at']).tzinfo is None:raise ValueError('Invalid evaluation timestamp.')
    except (KeyError,TypeError,ValueError):raise ValueError('Invalid saved evaluation timestamp.') from None
    if (record.get('format')!='almg-saved-corpus-evaluation-v1' or type(record.get('schema_version')) is not int or record['schema_version']!=1
        or record.get('id')!=folder.name or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})
        or record.get('files')!={'report.json':file_digest(folder/'report.json')} or record.get('source')!=report['source']
        or record.get('report_revision')!=report['revision'] or record.get('training_approved') is not False or record.get('release_approved') is not False):
        raise ValueError('Saved evaluation manifest binding changed.')
    return {'record':record,'report':report}


def read(root, identifier):
    return _read_folder(Path(root)/'decoder-corpus-evaluations'/_id(identifier))


def history(root, identifier):
    _id(identifier);records=[]
    for folder in (Path(root)/'decoder-corpus-evaluations').glob('[0-9a-f]'*32):
        if not folder.is_dir():continue
        try:record=read(root,folder.name)['record']
        except (OSError,ValueError,KeyError,TypeError):continue
        if record['source']['record_id']==identifier:records.append(record)
    return sorted(records,key=lambda item:(item['created_at'],item['id']),reverse=True)[:20]
