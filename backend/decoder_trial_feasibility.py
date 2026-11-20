"""Preapproval hardware evidence for the unchanged generated-text decoder trial."""
from pathlib import Path
if __package__:
    from . import decoder_trials as trials,decoder_architecture_feasibility as architecture,training_resources
    from .run_manifest import digest,file_digest
else:
    import decoder_trials as trials,decoder_architecture_feasibility as architecture,training_resources
    from run_manifest import digest,file_digest


def review(root):
    specification=trials.specification();hardware=architecture.hardware(root)
    # Exact fixed generated fixture: vocab 4, width 8, context 16, one block, FF 16.
    parameter_bytes=(4*8+16*8+8*4+4*8*8+2*8*16)*4
    activation_bytes=4*4*(8*16*8+2*16*16+2*16*16)
    encoded=specification['resource_budget']['encoded_data_bytes']
    estimates={'parameter_bytes':parameter_bytes,'gradient_bytes':parameter_bytes,'optimizer_state_bytes':0,
        'parallel_parameter_budget_bytes':parameter_bytes*8,'activation_layout_bytes':activation_bytes,
        'required_available_memory_bytes':256*1024**2+encoded*8+parameter_bytes*8+activation_bytes*2,
        'required_free_disk_bytes':64*1024**2+encoded*4+parameter_bytes*32,
        'precision':'float32','measured':False,'duration_estimate_seconds':None,
        'scope':'Fixed generated four-word fixture only; SGD resume comparison includes uninterrupted 100 steps plus a separate 50+50 trajectory. Not a 50M model or general pretraining estimate.'}
    reasons=list(hardware['errors'])
    if hardware['system']!='Darwin' or hardware['machine']!='arm64' or not hardware['metal_available']:reasons.append('This generated decoder trial requires Apple silicon with MLX Metal; CPU/CUDA training fallback is unavailable.')
    if not architecture._fits(hardware,{**estimates,'estimated_gpu_working_bytes':parameter_bytes*8+activation_bytes*2}):reasons.append('Available memory, disk or Metal working-set recommendation does not cover this fixed trial. Close other apps or free disk, then review again.')
    report={'format':'almg-generated-decoder-feasibility-v1','schema_version':1,'specification_sha256':digest(specification),
        'scope':'generated_local_text_fixture_only','hardware':hardware,'estimates':estimates,'feasible':not reasons,'blockers':reasons,
        'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_trial_feasibility.py','decoder_trials.py','decoder_training.py','decoder_recipe.py','training_resources.py','decoder_architecture_feasibility.py')})}
    report['revision']=digest(report);return report


def admit(root,approved=None):
    fresh=review(root)
    if approved is not None and (not isinstance(approved,dict) or approved.get('feasible') is not True
        or approved.get('revision')!=digest({k:v for k,v in approved.items() if k!='revision'})
        or any(approved.get(key)!=fresh[key] for key in ('format','schema_version','specification_sha256','scope','estimates','implementation_sha256'))):raise ValueError('Generated decoder hardware review changed; reopen feasibility before approval.')
    if not fresh['feasible']:raise training_resources.ResourceUnavailable('Generated decoder trial blocked: '+' '.join(fresh['blockers']))
    return fresh


def start(root,confirmed,submit,approved=None,**options):
    if confirmed is not True:raise ValueError('Confirm the generated decoder trial after reviewing feasibility.')
    if options.get('dataset') is not None:raise ValueError('This hardware review covers generated text only; reviewed datasets use their separate workflow.')
    admission=admit(root,approved)
    def save_and_submit(function,*arguments):
        # Core start invokes submit before any optimizer worker can run. Preserve its schema and approval hash.
        fresh=admit(root,approved)
        with trials._LOCK:
            record=trials.read(root,arguments[1]);record['generated_trial_hardware']={
                'approval':approved or admission,'admission':fresh,'reviewed_before_approval':approved is not None,
                'execution_policy':'Existing trial checks memory/disk again before and during fitting; this snapshot records submission admission, not measured execution peaks.'}
            trials.write(root,record)
        return submit(function,*arguments)
    return trials.start(root,confirmed,save_and_submit,**options)
