"""Read-only preapproval admission for the existing bounded streamed SGD trial."""
from pathlib import Path
import json
from tempfile import NamedTemporaryFile
from time import perf_counter
if __package__:
    from . import decoder_stream_training as training,decoder_architecture_feasibility as hardware,decoder_stream_training_calibration as calibration,training_resources
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_training as training,decoder_architecture_feasibility as hardware,decoder_stream_training_calibration as calibration,training_resources
    from run_manifest import digest,file_digest


def review(root,window_id,confirmed,reviewed,precision='float32',device='metal'):
    if confirmed is not True:raise ValueError('Confirm local streamed-training feasibility inspection.')
    current=training.review(root,window_id)
    if current!=reviewed:raise ValueError('Reopen the exact stream training review.')
    record=current['windows'];settings=current['settings'];v=record['vocabulary_size'];d=settings['width'];length=settings['context_length'];batch=settings['batch_windows'];ff=d*2
    # The existing recipe has one attention head/layer, no affine norms or biases.
    count=2*v*d+length*d+4*d*d+2*d*ff;parameters=count*4
    activation=4*batch*(8*length*d+2*length*ff+2*length*length)
    source,_=training.windows._sources(root,record['comparison_id'],record['overlap_id'],True)
    existing=source['index']['source_bytes']+(training.windows._folder(root,window_id)/'windows.sqlite3').stat().st_size
    existing+=(training.windows.indexes._folder(root,record['index_id'])/'records.sqlite3').stat().st_size
    checkpoint_bytes=count*100+4*1024**2;checkpoint_count=1+settings['total_steps']//settings['chunk_steps']
    estimates={'parameter_count':count,'parameter_bytes':parameters,'gradient_bytes':parameters,'optimizer_state_bytes':0,
               'activation_layout_bytes':activation,'estimated_gpu_working_bytes':parameters*4+activation,
               'existing_source_index_window_storage_bytes':existing,'additional_dataset_copy_bytes':0,
               'checkpoint_count':checkpoint_count,'checkpoint_storage_budget_bytes':checkpoint_count*checkpoint_bytes,
               'required_available_memory_bytes':max(256*1024**2+count*100+parameters*4+activation,256*1024**2+65536*8),
               'required_free_disk_bytes':64*1024**2+checkpoint_count*checkpoint_bytes,
               'measured':False,'duration_estimate_seconds':None,
               'assumptions':'Bounded FP32 width-8/context-16, batch-4, one-layer SGD20 recipe only. No optimizer moments. '
                 'JSON checkpoint budget uses 100 bytes per parameter plus tokenizer/metadata allowance. Existing storage counts source bytes, index DB and window DB, not all preprocessing artifacts. '
                 'No dataset copy or materialization. Runtime overhead and peak memory are not measured; this is not a full-epoch training guarantee.'}
    profile=hardware.hardware(root);calibrated=calibration.apply(root,current,profile,estimates);reasons=[]
    if precision!='float32' or device!='metal':reasons.append('This streamed trial supports float32 Metal only; no CPU/CUDA training fallback is implemented.')
    if profile['system']!='Darwin' or profile['machine']!='arm64' or not profile['metal_available']:reasons.append('Apple silicon with available MLX Metal is required.')
    if not hardware._fits(profile,estimates):reasons.append('Available memory, free disk or Metal working-set recommendation does not cover the trial reserves.')
    reasons.extend(profile['errors'])
    report={'format':'almg-stream-training-feasibility-v2','schema_version':2,'scope':'manual_stream_sgd20_trial_only_not_full_epoch',
            'training_review_sha256':digest(current),'windows_id':window_id,'windows_revision':record['revision'],
            'precision':precision,'device':device,'hardware':profile,'estimates':estimates,'calibration':calibrated,'feasible':not reasons,'blockers':reasons,
            'training_approved':False,'release_approved':False,'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_stream_training_feasibility.py','decoder_stream_training_calibration.py')})}
    report['revision']=digest(report)
    return report


def begin(root,window_id,confirmed,reviewed,approved):
    if confirmed is not True:raise ValueError('Confirm the separate twenty-step streamed training approval.')
    if not isinstance(approved,dict):raise ValueError('Review streamed-training hardware feasibility before approval.')
    fresh=review(root,window_id,True,reviewed,approved.get('precision'),approved.get('device'))
    if (approved.get('revision')!=digest({k:v for k,v in approved.items() if k!='revision'}) or approved.get('feasible') is not True
            or any(approved.get(key)!=fresh[key] for key in ('format','schema_version','scope','training_review_sha256','windows_id','windows_revision','precision','device','estimates','calibration','implementation_sha256'))):raise ValueError('Streamed-training feasibility changed; review it again.')
    if not fresh['feasible']:raise training_resources.ResourceUnavailable('Streamed trial blocked: '+' '.join(fresh['blockers']))
    state=training.begin(root,window_id,True,reviewed)
    try:_save_profile(root,state,approved,fresh)
    except OSError as error:raise ValueError(f"Trial {state['id']} was initialized but hardware-profile publication failed; its checkpoint is retained. Reopen saved trials.") from error
    return state


def _save_profile(root,state,approved,fresh):
    record={'format':'almg-stream-training-hardware-profile-v1','schema_version':1,'run_id':state['id'],
            'training_review_sha256':digest(state['review']),'approval_sha256':digest(state['approval']),
            'initial_state_revision':state['revision'],'initial_checkpoint':state['checkpoint'],
            'initial_checkpoint_manifest_sha256':state['checkpoint_manifest_sha256'],
            'approved_feasibility':approved,'execution_feasibility':fresh,'release_approved':False}
    record['revision']=digest(record);directory=training._folder(root,state['id']);temporary=None
    try:
        with NamedTemporaryFile(mode='w',encoding='utf-8',dir=directory,prefix='.hardware-',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name);stream.write(json.dumps(record,allow_nan=False,indent=2))
        temporary.replace(directory/'hardware-feasibility.json')
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def read_profile(root,run_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm review of the private saved hardware profile.')
    state=training.read(root,run_id);directory=training._folder(root,run_id);path=directory/'hardware-feasibility.json'
    if not path.exists():return {'available':False,'reason':'No saved hardware approval profile. This may be a legacy trial or an interrupted profile publication; no historical hardware values are inferred.'}
    if path.stat().st_size>128000:raise ValueError('Saved hardware profile exceeds its size limit.')
    record=json.loads(path.read_text(encoding='utf-8'))
    if (record.get('format')!='almg-stream-training-hardware-profile-v1' or record.get('schema_version')!=1 or record.get('run_id')!=run_id
            or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'}) or record.get('release_approved') is not False
            or record.get('training_review_sha256')!=digest(state['review']) or record.get('approval_sha256')!=digest(state['approval'])):raise ValueError('Saved hardware profile binding changed.')
    checkpoint=record['initial_checkpoint']
    if not isinstance(checkpoint,str) or Path(checkpoint).name!=checkpoint or not checkpoint.startswith('step-000000-'):raise ValueError('Invalid initial hardware-profile checkpoint.')
    initial=directory/checkpoint
    if file_digest(initial/'manifest.json')!=record['initial_checkpoint_manifest_sha256']:raise ValueError('Hardware-profile initial checkpoint changed.')
    _,_,manifest=training.decoder_bundle.load(initial)
    if manifest['training']['approval_sha256']!=record['approval_sha256'] or manifest['training']['completed_steps']!=0:raise ValueError('Hardware-profile checkpoint receipt changed.')
    for key in ('approved_feasibility','execution_feasibility'):
        report=record[key]
        version={'almg-stream-training-feasibility-v1':1,'almg-stream-training-feasibility-v2':2}.get(report.get('format'))
        if (version is None or report.get('schema_version')!=version
                or report.get('revision')!=digest({k:v for k,v in report.items() if k!='revision'}) or report.get('feasible') is not True
                or report.get('training_review_sha256')!=record['training_review_sha256'] or report.get('windows_id')!=state['windows_id']
                or report.get('training_approved') is not False or report.get('release_approved') is not False):raise ValueError('Saved feasibility snapshot changed.')
    return {'available':True,'record':record}


def step(root,run_id,confirmed,expected_revision):
    """Recheck current trial reserves at each explicitly requested continuation."""
    if confirmed is not True:raise ValueError('Confirm running the next five manual updates now.')
    with training._LOCK:
        started=perf_counter()
        state=training.read(root,run_id)
        # A stale/replayed request remains a no-op, even if resources changed.
        if expected_revision!=state['revision'] or state['status']=='complete':return state
        fresh=review(root,state['windows_id'],True,state['review'])
        if not fresh['feasible']:raise training_resources.ResourceUnavailable('Streamed continuation blocked; previous checkpoint retained. '+' '.join(fresh['blockers']))
        if __package__:
            from . import decoder_stream_training_measurements as measurements
        else:
            import decoder_stream_training_measurements as measurements
        return measurements.execute(root,state,fresh,started)
