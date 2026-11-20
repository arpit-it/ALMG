"""Use compatible isolated stream observations only to raise calculated reserves."""
from pathlib import Path
if __package__:
    from . import decoder_stream_training as training,decoder_stream_training_measurements as measurements,decoder_stream_duration as duration
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_training as training,decoder_stream_training_measurements as measurements,decoder_stream_duration as duration
    from run_manifest import digest,file_digest


def apply(root,current,profile,estimates):
    implementation=digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_stream_training_measurements.py','decoder_stream_chunk_worker.py')})
    admission_implementation=digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_stream_training_feasibility.py','decoder_stream_training_calibration.py','decoder_stream_duration.py')})
    parent=Path(root)/'decoder-stream-training-runs';references=[];observations=[];peaks={'metal':0,'rss':0,'checkpoint':0};sources={}
    for folder in sorted(parent.iterdir()) if parent.exists() else []:
        try:
            state=training.read(root,folder.name)
            if state['windows_id']!=current['windows']['id'] or digest(state['review'])!=digest(current):continue
            for record in measurements.read(root,state['id'],True)['records']:
                observed=record['measurements'];device=record['execution_admission']['hardware']
                if (record['implementation_sha256']!=implementation or record['execution_admission']['implementation_sha256']!=admission_implementation
                        or any(device.get(key)!=profile.get(key) for key in ('system','machine','mlx_version','metal_device'))):continue
                reference={'run_id':state['id'],'after_revision':record['after_revision'],'revision':record['revision'],'completed_steps':record['completed_steps']}
                values={'metal':observed['metal_peak_bytes'],'rss':observed['process_peak_rss_bytes'],
                        'checkpoint':sum(path.stat().st_size for path in (folder/record['checkpoint']).iterdir() if path.is_file())}
                references.append(reference)
                observations.append(record)
                for key,value in values.items():
                    if value>peaks[key]:peaks[key]=value;sources[key]=reference
        except (OSError,ValueError,TypeError,KeyError,AttributeError):continue
    estimates['calculated_required_available_memory_bytes']=estimates['required_available_memory_bytes']
    estimates['calibrated_gpu_working_bytes']=max(estimates['estimated_gpu_working_bytes'],peaks['metal'])
    if references:
        estimates['required_available_memory_bytes']=max(estimates['required_available_memory_bytes'],256*1024**2+peaks['rss']+estimates['calibrated_gpu_working_bytes'])
        estimates['checkpoint_storage_budget_bytes']=max(estimates['checkpoint_storage_budget_bytes'],estimates['checkpoint_count']*peaks['checkpoint'])
        estimates['required_free_disk_bytes']=max(estimates['required_free_disk_bytes'],64*1024**2+estimates['checkpoint_storage_budget_bytes'])
    work=duration.estimate(observations);estimates['duration_estimate_seconds']=work['estimated_twenty_update_request_work_seconds']
    return {'compatible_chunk_count':len(references),'evidence_sha256':digest(references),'peak_sources':sources,'duration_estimate':work,
            'observed_metal_peak_bytes':peaks['metal'] or None,'observed_process_peak_rss_bytes':peaks['rss'] or None,'observed_checkpoint_bytes':peaks['checkpoint'] or None,
            'scope':'exact_training_review_same_hardware_mlx_chunk_and_admission_implementation',
            'policy':'All matching saved trials are considered, including final evaluation chunks. Measurements never lower calculated reserves. '
              'RSS and Metal peak can overlap; their admission sum plus base reserve is deliberately conservative. Not a full-epoch feasibility or duration guarantee.'}
