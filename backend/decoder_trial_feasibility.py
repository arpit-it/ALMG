"""Preapproval hardware evidence for unchanged bounded saved decoder trials."""
from pathlib import Path
import json
if __package__:
    from . import decoder_trials as trials,decoder_architecture_feasibility as architecture,training_resources
    from .run_manifest import digest,file_digest
else:
    import decoder_trials as trials,decoder_architecture_feasibility as architecture,training_resources
    from run_manifest import digest,file_digest


def review(root,dataset=None):
    binding=None;vocabulary=4;windows=4
    if dataset is not None:
        manifest,tokenizer,_,batches=trials.decoder_dataset_training.preflight(root,dataset)
        vocabulary=len(tokenizer.vocabulary);windows=len(batches['train'])
        directory=Path(root)/'decoder-datasets'/manifest['id']
        encoded=max(128000,sum((directory/name).stat().st_size for name in manifest['files']))
        binding={'id':manifest['id'],'manifest_sha256':digest(manifest),'dataset_sha256':manifest['dataset_sha256'],
                 'tokenizer_sha256':tokenizer.fingerprint(),'vocabulary_size':vocabulary,'window_counts':{key:len(value) for key,value in batches.items()}}
        specification=trials.specification(manifest)
    else:
        specification=trials.specification();encoded=specification['resource_budget']['encoded_data_bytes']
    hardware=architecture.hardware(root)
    # Fixed width-8/context-16 decoder; local loss retains all reviewed training-window graphs.
    parameter_bytes=(vocabulary*8*2+16*8+4*8*8+2*8*16)*4
    activation_bytes=4*windows*(8*16*8+2*16*16+2*16*16+4*16*vocabulary)
    estimates={'parameter_bytes':parameter_bytes,'gradient_bytes':parameter_bytes,'optimizer_state_bytes':0,
        'parallel_parameter_budget_bytes':parameter_bytes*8,'activation_layout_bytes':activation_bytes,
        'required_available_memory_bytes':256*1024**2+encoded*8+parameter_bytes*8+activation_bytes*2,
        'required_free_disk_bytes':64*1024**2+encoded*4+parameter_bytes*32,
        'precision':'float32','measured':False,'duration_estimate_seconds':None,
        'scope':('Reviewed local dataset, fixed width-8/context-16 FP32 SGD, 100 steps and step-50 checkpoint; all training-window graphs and vocabulary-dependent logits are budgeted.' if binding else 'Fixed generated four-word fixture only; SGD resume comparison includes uninterrupted 100 steps plus a separate 50+50 trajectory.')+' Not a 50M model or general pretraining estimate.'}
    reasons=list(hardware['errors'])
    if hardware['system']!='Darwin' or hardware['machine']!='arm64' or not hardware['metal_available']:reasons.append('This saved decoder trial requires Apple silicon with MLX Metal; CPU/CUDA training fallback is unavailable.')
    if not architecture._fits(hardware,{**estimates,'estimated_gpu_working_bytes':parameter_bytes*8+activation_bytes*2}):reasons.append('Available memory, disk or Metal working-set recommendation does not cover this fixed trial. Close other apps or free disk, then review again.')
    report={'format':'almg-local-dataset-decoder-feasibility-v1' if binding else 'almg-generated-decoder-feasibility-v1','schema_version':1,'specification_sha256':digest(specification),
        'scope':'reviewed_local_text_trial_only' if binding else 'generated_local_text_fixture_only','dataset':binding,'hardware':hardware,'estimates':estimates,'feasible':not reasons,'blockers':reasons,
        'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_trial_feasibility.py','decoder_trials.py','decoder_training.py','decoder_recipe.py','decoder_dataset_training.py','decoder_datasets.py','training_resources.py','decoder_architecture_feasibility.py')})}
    report['revision']=digest(report);return report


def admit(root,approved=None,dataset=None):
    fresh=review(root,dataset)
    if approved is not None and (not isinstance(approved,dict) or approved.get('feasible') is not True
        or approved.get('revision')!=digest({k:v for k,v in approved.items() if k!='revision'})
        or any(approved.get(key)!=fresh.get(key) for key in ('format','schema_version','specification_sha256','scope','dataset','estimates','implementation_sha256','resume'))):raise ValueError('Saved decoder hardware review changed; reopen feasibility before approval.')
    if not fresh['feasible']:raise training_resources.ResourceUnavailable('Saved decoder trial blocked: '+' '.join(fresh['blockers']))
    return fresh


def start(root,confirmed,submit,approved=None,**options):
    if confirmed is not True:raise ValueError('Confirm the saved decoder trial after reviewing feasibility.')
    dataset=options.get('dataset');admission=admit(root,approved,dataset)
    def save_and_submit(function,*arguments):
        # Core start invokes submit before any optimizer worker can run. Preserve its schema and approval hash.
        fresh=admit(root,approved,dataset)
        with trials._LOCK:
            record=trials.read(root,arguments[1]);record['local_dataset_trial_hardware' if dataset is not None else 'generated_trial_hardware']={
                'approval':approved or admission,'admission':fresh,'reviewed_before_approval':approved is not None,
                'execution_policy':'Existing trial checks memory/disk again before and during fitting; this snapshot records submission admission, not measured execution peaks.'}
            trials.write(root,record)
        return submit(function,*arguments)
    return trials.start(root,confirmed,save_and_submit,**options)


def _checkpoint(root,trial_id):
    directory=trials.folder(root,trial_id)/'artifacts/step-50'
    if not directory.exists():return {'completed_steps':0,'files':{}}
    try:
        names=('manifest.json','decoder.json','tokenizer.json')
        if any((directory/name).stat().st_size>16*1024**2 for name in names):raise ValueError('Checkpoint exceeds the bounded trial size.')
        manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'));training=manifest['training']
        if (manifest.get('format')!='almg-decoder-bundle-v1' or manifest.get('schema_version')!=1 or training.get('schema_version')!=1 or training.get('kind')!='decoder_sgd_checkpoint'
            or training.get('completed_steps')!=50 or type(training.get('completed_steps')) is not int
            or manifest.get('training_sha256')!=digest(training) or training.get('revision_sha256')!=digest(training['revision'])
            or set(manifest['files'])!={'decoder.json','tokenizer.json'}
            or any(file_digest(directory/name)!=manifest['files'][name] for name in manifest['files'])):raise ValueError('Checkpoint metadata or file hashes changed.')
        return {'completed_steps':50,'files':{name:file_digest(directory/name) for name in names}}
    except (OSError,ValueError,TypeError,KeyError) as error:raise ValueError('Checkpoint is unreadable or changed; preserve it and review recovery before resuming.') from error


def resume_review(root,trial_id):
    with trials._LOCK:
        record=trials.read(root,trial_id)
        if record['status']!='interrupted' or (str(Path(root)),trial_id) in trials._ACTIVE:raise ValueError('Only an inactive interrupted trial can be reviewed for resume.')
        if (trials.folder(root,trial_id)/'artifacts/bundle').exists():raise ValueError('A completed bundle exists; preserve it and approve a new trial instead.')
        if record['specification']!=trials.specification(record.get('dataset')):raise ValueError('Saved training implementation changed; approve a new trial instead.')
        binding={'trial_id':trial_id,'previous_approval_sha256':digest(record['approval']),'checkpoint':_checkpoint(root,trial_id)}
    report=review(root,record.get('dataset'));report['resume']=binding;report['revision']=digest({k:v for k,v in report.items() if k!='revision'});return report


def resume(root,trial_id,confirmed,submit,approved=None,**options):
    if confirmed is not True:raise ValueError('Review and confirm the saved trial resume.')
    fresh=resume_review(root,trial_id)
    # Validate the full reviewed action, including the prior approval and checkpoint hashes.
    if approved is not None and (not isinstance(approved,dict) or approved.get('feasible') is not True
        or approved.get('revision')!=digest({k:v for k,v in approved.items() if k!='revision'})
        or any(approved.get(key)!=fresh.get(key) for key in ('format','schema_version','specification_sha256','scope','dataset','estimates','implementation_sha256','resume'))):raise ValueError('Resume hardware or checkpoint review changed; reopen it before approval.')
    if not fresh['feasible']:raise training_resources.ResourceUnavailable('Saved trial resume blocked: '+' '.join(fresh['blockers']))
    binding=fresh['resume'];dataset=trials.read(root,trial_id).get('dataset')
    def save_and_submit(function,*arguments):
        admission=admit(root,None,dataset)
        if _checkpoint(root,trial_id)!=binding['checkpoint']:raise ValueError('Checkpoint changed before submission; review resume again.')
        admission['resume']=binding;admission['revision']=digest({k:v for k,v in admission.items() if k!='revision'})
        if any(admission.get(key)!=fresh.get(key) for key in ('format','schema_version','specification_sha256','scope','dataset','estimates','implementation_sha256','resume')):raise ValueError('Resume feasibility changed before submission; review it again.')
        with trials._LOCK:
            record=trials.read(root,trial_id)
            if not record.get('previous_approvals') or digest(record['previous_approvals'][-1])!=binding['previous_approval_sha256']:raise ValueError('Previous approval changed before resume submission.')
            record['resume_hardware_reviews']=[*record.get('resume_hardware_reviews',[]),{
                'approval':approved or fresh,'admission':admission,'reviewed_before_approval':approved is not None}]
            trials.write(root,record)
        return submit(function,*arguments)
    return trials.start(root,True,save_and_submit,trial_id=trial_id,**options)


def factory_review(root,job,proposal_revision):
    proposal=job['decoder_proposal'];dataset=job.get('decoder_dataset')
    if proposal_revision!=proposal['revision']:raise ValueError('Review the current decoder approach before hardware approval.')
    current=trials.approved_proposal(root,proposal['id'],proposal_revision,trials.specification(dataset))
    if current!=proposal:raise ValueError('Factory proposal changed; reopen the current approach.')
    report=review(root,dataset);report['factory']={'job_id':job['id'],'proposal_id':proposal['id'],'proposal_revision':proposal_revision}
    report['revision']=digest({k:v for k,v in report.items() if k!='revision'});return report


def factory_start(root,job,confirmed,submit,proposal_revision,approved=None,**options):
    if confirmed is not True:raise ValueError('Confirm the reviewed factory decoder handoff.')
    fresh=factory_review(root,job,proposal_revision)
    keys=('format','schema_version','specification_sha256','scope','dataset','estimates','implementation_sha256','factory')
    if approved is not None and (not isinstance(approved,dict) or approved.get('feasible') is not True
        or approved.get('revision')!=digest({k:v for k,v in approved.items() if k!='revision'})
        or any(approved.get(key)!=fresh.get(key) for key in keys)):raise ValueError('Factory hardware or approach review changed; reopen it before approval.')
    if not fresh['feasible']:raise training_resources.ResourceUnavailable('Factory decoder handoff blocked: '+' '.join(fresh['blockers']))
    base={key:value for key,value in (approved or fresh).items() if key not in ('factory','revision')};base['revision']=digest(base)
    def save_factory_and_submit(function,*arguments):
        admission=factory_review(root,job,proposal_revision)
        if not admission['feasible'] or any(admission.get(key)!=fresh.get(key) for key in keys):raise ValueError('Factory feasibility changed before submission; review again.')
        with trials._LOCK:
            record=trials.read(root,arguments[1])
            record['local_dataset_trial_hardware' if job.get('decoder_dataset') is not None else 'generated_trial_hardware']['reviewed_before_approval']=approved is not None
            record['factory_hardware_review']={
                'approval':approved or fresh,'admission':admission,'reviewed_before_approval':approved is not None}
            trials.write(root,record)
        return submit(function,*arguments)
    return start(root,True,save_factory_and_submit,base,proposal_id=job['decoder_proposal']['id'],proposal_revision=proposal_revision,dataset=job.get('decoder_dataset'),**options)
