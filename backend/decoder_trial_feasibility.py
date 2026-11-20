"""Preapproval hardware evidence for unchanged bounded saved decoder trials."""
from pathlib import Path
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
        or any(approved.get(key)!=fresh[key] for key in ('format','schema_version','specification_sha256','scope','dataset','estimates','implementation_sha256'))):raise ValueError('Saved decoder hardware review changed; reopen feasibility before approval.')
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
