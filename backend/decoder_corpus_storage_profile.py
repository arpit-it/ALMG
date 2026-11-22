"""Read-only logical storage observations for a saved run and its progress snapshots."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
if __package__:
    from . import decoder_corpus_optimizer as training, decoder_corpus_interruptions as interruptions
    from .run_manifest import digest, file_digest
else:
    import decoder_corpus_optimizer as training, decoder_corpus_interruptions as interruptions
    from run_manifest import digest, file_digest

MAX_ARTIFACT_BYTES=16*1024**2
MAX_RECORD_BYTES=256000
MAX_PROGRESS_RECORDS=1024


def _measure(path, *, expected_sha=None, expected_record=None):
    limit=MAX_RECORD_BYTES if expected_record is not None else MAX_ARTIFACT_BYTES
    with path.open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('Storage profile file exceeds its bounded size.')
    sha=hashlib.sha256(raw).hexdigest()
    if expected_sha is not None and sha!=expected_sha:raise ValueError('Storage profile artifact changed.')
    if expected_record is not None and json.loads(raw)!=expected_record:raise ValueError('Storage profile record changed.')
    return {'bytes':len(raw),'sha256':sha}


def _category(name):
    if name=='record.json':return 'manifest'
    if '/' in name:return 'midpoint_checkpoint'
    if name.startswith('reference-'):return 'completed_reference'
    return {'trained-model.json':'trained_model','optimizer.json':'active_optimizer','tokenizer.json':'tokenizer'}.get(name,'other')


def _record(root, record, kind):
    folder=training._folder(root,record['id']);files=[]
    for name,sha in sorted(record['files'].items()):
        files.append({'name':name,'category':_category(name),**_measure(folder/name,expected_sha=sha)})
    files.append({'name':'record.json','category':'manifest',**_measure(folder/'record.json',expected_record=record)})
    return {'record_id':record['id'],'record_revision':record['revision'],'kind':kind,
            'phase':record.get('cancellation_phase'),'completed_steps':record['completed_steps'],
            'files':files,'total_bytes':sum(row['bytes'] for row in files)}


def profile(root, identifier):
    parent=training.read(root,identifier)
    if parent.get('status','completed')!='completed':raise ValueError('Choose a completed corpus run for its retained storage profile.')
    records=[_record(root,parent,'run')];unknown=[];truncated=False
    for index,path in enumerate((Path(root)/interruptions.DIRECTORY).glob('*/record.json')):
        if index>=MAX_PROGRESS_RECORDS:
            truncated=True;break
        try:
            with path.open('rb') as stream:raw=stream.read(MAX_RECORD_BYTES+1)
            if len(raw)>MAX_RECORD_BYTES:raise ValueError('oversized')
            candidate=json.loads(raw)
            if not isinstance(candidate,dict):raise ValueError('invalid record')
        except (OSError,ValueError,UnicodeError):
            unknown.append({'record_id':path.parent.name[:128],'reason':'unreadable_or_oversized_progress_record'});continue
        origin=candidate.get('original_run_id')
        if not isinstance(origin,str) or len(origin)!=32 or any(char not in '0123456789abcdef' for char in origin):
            unknown.append({'record_id':path.parent.name[:128],'reason':'missing_or_invalid_source_binding'});continue
        if origin!=identifier:continue
        current=training.read(root,path.parent.name)
        if (current!=candidate or current.get('original_run_id')!=identifier
                or current['review']['revision']!=parent['review']['revision']):
            raise ValueError('Storage profile progress/source binding changed.')
        records.append(_record(root,current,'retained_progress'))
    records[1:]=sorted(records[1:],key=lambda record:record['record_id'])
    complete=not unknown and not truncated
    progress_bytes=sum(record['total_bytes'] for record in records[1:])
    reserve=parent['review']['estimates'].get('interruption_checkpoint_extra_disk_bytes')
    reserve=reserve if type(reserve) is int and reserve>=0 else None
    covers=None if reserve is None else False if progress_bytes>reserve else True if complete else None
    categories={}
    for record in records:
        for row in record['files']:categories[row['category']]=categories.get(row['category'],0)+row['bytes']
    result={'format':'almg-corpus-storage-profile-v1','schema_version':1,'measured':True,
            'observed_at':datetime.now(timezone.utc).isoformat(),
            'source':{'record_id':identifier,'record_revision':parent['revision'],'review_revision':parent['review']['revision']},
            'records':records,'retained_progress_count':len(records)-1,
            'run_bytes':records[0]['total_bytes'],'retained_progress_bytes':progress_bytes,
            'total_bytes':sum(record['total_bytes'] for record in records),
            'file_count':sum(len(record['files']) for record in records),'category_bytes':categories,
            'inventory_complete':complete,'scan_truncated':truncated,'unclassified_progress_records':unknown,
            'calculated_progress_reserve_bytes':reserve,'reserve_covers_observed_progress':covers,
            'training_approved':False,'release_approved':False,
            'scope':'Sequential validated logical file-length observations for this run and its matching published progress snapshots, including record manifests. Not an atomic snapshot or physical allocated disk blocks; duplicate content at separate paths is counted separately. Excludes inputs, initialization, continuations, other runs, unpublished/incomplete artifacts, filesystem overhead and future writes. Unknown records or scan truncation make the inventory incomplete. Reserve comparison is diagnostic only: it does not lower admission reserves, guarantee future capacity or approve training.',
            'implementation_sha256':file_digest(Path(__file__))}
    result['revision']=digest(result)
    return result
