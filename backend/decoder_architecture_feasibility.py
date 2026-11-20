"""Observed hardware and conservative admission estimates for synthetic backward checks."""
from datetime import datetime,timezone
from importlib.metadata import version,PackageNotFoundError
import json
from pathlib import Path
import platform
import shutil
import subprocess
if __package__:
    from . import decoder_architecture_plans as plans,decoder_architecture_initializations as initializations,training_resources
    from .run_manifest import digest,file_digest
else:
    import decoder_architecture_plans as plans,decoder_architecture_initializations as initializations,training_resources
    from run_manifest import digest,file_digest
MIB=1024*1024


def hardware(root):
    system,machine=platform.system(),platform.machine();info={'system':system,'machine':machine,'total_memory_bytes':None,
        'available_memory_bytes':None,'free_disk_bytes':None,'metal_available':False,'metal_device':None,'mlx_version':None,
        'cpu_forward_supported':True,'cpu_backward_fallback':False,'cuda_status':'not_probed_this_workflow_does_not_support_cuda','errors':[]}
    try:info['available_memory_bytes']=training_resources.available_memory()
    except (OSError,ValueError,AttributeError,subprocess.SubprocessError) as error:info['errors'].append('Available memory could not be measured: '+str(error))
    try:
        parent=Path(root)
        while not parent.exists() and parent!=parent.parent:parent=parent.parent
        info['free_disk_bytes']=shutil.disk_usage(parent).free
    except OSError as error:info['errors'].append('Free disk could not be measured: '+str(error))
    if system=='Darwin' and machine=='arm64':
        try:
            info['total_memory_bytes']=int(subprocess.check_output(['/usr/sbin/sysctl','-n','hw.memsize'],text=True,timeout=3).strip())
            import mlx.core as mx
            info['mlx_version']=version('mlx');info['metal_available']=bool(mx.metal.is_available())
            if info['metal_available']:info['metal_device']=dict(mx.device_info())
        except (ImportError,PackageNotFoundError,OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:info['errors'].append('Metal runtime/device discovery failed: '+str(error))
    info['observed_at']=datetime.now(timezone.utc).isoformat()
    return info


def _source(root,plan_id,reviewed):
    if not isinstance(reviewed,dict):raise ValueError('Reopen the exact initialized architecture before feasibility review.')
    identifier=reviewed.get('id')
    if not isinstance(identifier,str) or len(identifier)!=32 or any(value not in '0123456789abcdef' for value in identifier):raise ValueError('Invalid initialized architecture ID.')
    plan=plans.read(root,plan_id);folder=initializations._folder(root,plan_id)/identifier;path=folder/'record.json'
    if path.stat().st_size>128000 or (folder/'model.json').stat().st_size>64*1024*1024:raise ValueError('Initialized artifact exceeds its size limit.')
    current=json.loads(path.read_text(encoding='utf-8'))
    if (current!=reviewed or current.get('revision')!=digest({k:v for k,v in current.items() if k!='revision'})
            or current.get('plan_id')!=plan_id or current.get('plan_revision')!=plan['revision'] or current.get('config')!=plan['review']['config']
            or current.get('model_sha256')!=file_digest(folder/'model.json') or current.get('training_approved') is not False or current.get('release_approved') is not False):raise ValueError('Initialized architecture binding changed.')
    return plan,current,(folder/'model.json').stat().st_size


def estimate(config,json_bytes):
    layout=plans.review(config);p=layout['estimates']['weight_bytes'];rows=min(2,config['batch_size']);length=min(8,config['context_length']);d=config['hidden_size'];f=config['feed_forward_size'];layers=config['layers'];heads=config['attention_heads']
    activations=4*rows*layers*(8*length*d+2*length*f+2*heads*length*length)
    gpu=p*4+activations;cpu=json_bytes*6+p*4+activations*2
    return {'precision':'float32','parameter_bytes':p,'gradient_bytes':p,'optimizer_state_bytes':0,'temporary_parameter_copy_bytes':p*2,
            'activation_layout_bytes':activations,'estimated_gpu_working_bytes':gpu,'estimated_cpu_load_and_reference_bytes':cpu,
            'required_available_memory_bytes':max(256*MIB+gpu+cpu,256*MIB+p*64,256*MIB+json_bytes*16),
            'required_free_disk_bytes':max(64*MIB+512*1024,64*MIB+p*32,64*MIB+json_bytes*8),
            'synthetic_batch_shape':[rows,length],'dataset_storage_bytes':0,'dataset_storage_scope':'synthetic_ids_only_no_dataset_import',
            'measured':False,'peak_memory_measured':False,'duration_estimate_seconds':None,
            'assumptions':'FP32 Metal weights/gradients and two transient parameter copies; SGD has no moment buffers. Bounded synthetic probe only. CPU JSON/reference budget and existing reload/execution reserves included. Kernel/allocator/framework overhead is not measured; admission is not a runtime memory guarantee.'}


def _fits(hardware_info,estimates):
    memory=hardware_info.get('available_memory_bytes');disk=hardware_info.get('free_disk_bytes');device=hardware_info.get('metal_device') or {};working=device.get('max_recommended_working_set_size')
    return (type(memory) is int and memory>=estimates['required_available_memory_bytes'] and type(disk) is int and disk>=estimates['required_free_disk_bytes']
            and (type(working) is not int or estimates['estimated_gpu_working_bytes']<=working))


def review(root,plan_id,confirmed,reviewed,precision='float32',device='metal'):
    if confirmed is not True:raise ValueError('Confirm local hardware inspection for this initialized model.')
    plan,current,json_bytes=_source(root,plan_id,reviewed);profile=hardware(root);estimates=estimate(current['config'],json_bytes);reasons=[]
    if device!='metal':reasons.append('This backward diagnostic supports Metal only; CPU forward inspection is separate and CUDA is not implemented here.')
    if precision!='float32':reasons.append('This backward diagnostic supports float32 only; other precision modes have not been validated.')
    if not profile['metal_available'] or profile['system']!='Darwin' or profile['machine']!='arm64':reasons.append('Apple silicon with an available MLX Metal runtime is required.')
    if not _fits(profile,estimates):reasons.append('Available memory, free disk or the Metal working-set recommendation does not cover the conservative diagnostic reserves.')
    reasons.extend(profile['errors']);recommendation=None
    if reasons and profile['metal_available'] and device=='metal' and precision=='float32':
        config=dict(current['config']);original_bytes=estimates['parameter_bytes']
        for _ in range(24):
            if config['layers']>1:config['layers']=max(1,config['layers']//2)
            elif config['feed_forward_size']>config['hidden_size']:config['feed_forward_size']=max(config['hidden_size'],config['feed_forward_size']//2)
            elif config['hidden_size']>8:
                config['hidden_size']=max(8,config['hidden_size']//2)
                while config['hidden_size']%config['attention_heads'] or config['hidden_size']//config['attention_heads']<2:config['attention_heads']=max(1,config['attention_heads']//2)
                config['head_dim']=config['hidden_size']//config['attention_heads'];config['feed_forward_size']=max(config['hidden_size'],config['feed_forward_size']//2)
            elif config['context_length']>2:config['context_length']=max(2,config['context_length']//2)
            elif config['batch_size']>1:config['batch_size']=1
            else:break
            candidate_bytes=plans.review(config)['estimates']['weight_bytes'];candidate=estimate(config,max(1,(json_bytes*candidate_bytes+original_bytes-1)//original_bytes))
            if _fits(profile,candidate):recommendation={'config':dict(config),'estimates':candidate,'status':'estimated_fit_requires_new_plan_initialization_and_review'};break
    report={'format':'almg-architecture-feasibility-v1','schema_version':1,
            'source':{'plan_id':plan_id,'plan_revision':plan['revision'],'initialization_id':current['id'],'initialization_revision':current['revision'],'model_sha256':current['model_sha256']},
            'scope':'bounded_synthetic_backward_diagnostic_only_not_full_training','device':device,'precision':precision,'hardware':profile,'estimates':estimates,
            'feasible':not reasons,'blockers':reasons,'recommendation':recommendation,'training_approved':False,'release_approved':False,
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_architecture_feasibility.py','decoder_architecture_plans.py','training_resources.py')})}
    report['revision']=digest(report)
    return report


def admit(root,plan_id,reviewed,approved=None):
    precision=approved.get('precision','float32') if isinstance(approved,dict) else 'float32';device=approved.get('device','metal') if isinstance(approved,dict) else 'metal'
    fresh=review(root,plan_id,True,reviewed,precision,device)
    if approved is not None:
        if (not isinstance(approved,dict) or approved.get('feasible') is not True or approved.get('revision')!=digest({k:v for k,v in approved.items() if k!='revision'})
                or any(approved.get(key)!=fresh[key] for key in ('format','schema_version','source','scope','device','precision','estimates','implementation_sha256'))):raise ValueError('Hardware/configuration review changed; reopen feasibility before approving.')
    if not fresh['feasible']:raise training_resources.ResourceUnavailable('Backward check blocked: '+' '.join(fresh['blockers']))
    return fresh
