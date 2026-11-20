"""Read-only preapproval admission for the existing bounded streamed SGD trial."""
from pathlib import Path
if __package__:
    from . import decoder_stream_training as training,decoder_architecture_feasibility as hardware,training_resources
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_training as training,decoder_architecture_feasibility as hardware,training_resources
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
    profile=hardware.hardware(root);reasons=[]
    if precision!='float32' or device!='metal':reasons.append('This streamed trial supports float32 Metal only; no CPU/CUDA training fallback is implemented.')
    if profile['system']!='Darwin' or profile['machine']!='arm64' or not profile['metal_available']:reasons.append('Apple silicon with available MLX Metal is required.')
    if not hardware._fits(profile,estimates):reasons.append('Available memory, free disk or Metal working-set recommendation does not cover the trial reserves.')
    reasons.extend(profile['errors'])
    report={'format':'almg-stream-training-feasibility-v1','schema_version':1,'scope':'manual_stream_sgd20_trial_only_not_full_epoch',
            'training_review_sha256':digest(current),'windows_id':window_id,'windows_revision':record['revision'],
            'precision':precision,'device':device,'hardware':profile,'estimates':estimates,'feasible':not reasons,'blockers':reasons,
            'training_approved':False,'release_approved':False,'implementation_sha256':file_digest(Path(__file__))}
    report['revision']=digest(report)
    return report


def begin(root,window_id,confirmed,reviewed,approved):
    if confirmed is not True:raise ValueError('Confirm the separate twenty-step streamed training approval.')
    if not isinstance(approved,dict):raise ValueError('Review streamed-training hardware feasibility before approval.')
    fresh=review(root,window_id,True,reviewed,approved.get('precision'),approved.get('device'))
    if (approved.get('revision')!=digest({k:v for k,v in approved.items() if k!='revision'}) or approved.get('feasible') is not True
            or any(approved.get(key)!=fresh[key] for key in ('format','schema_version','scope','training_review_sha256','windows_id','windows_revision','precision','device','estimates','implementation_sha256'))):raise ValueError('Streamed-training feasibility changed; review it again.')
    if not fresh['feasible']:raise training_resources.ResourceUnavailable('Streamed trial blocked: '+' '.join(fresh['blockers']))
    return training.begin(root,window_id,True,reviewed)
