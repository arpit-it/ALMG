"""Bounded Metal backward diagnostic; updated weights are discarded, never saved."""
import json
from pathlib import Path
import platform
from importlib.metadata import version
from tempfile import NamedTemporaryFile
import uuid
import subprocess
import sys
import numpy as np
if __package__:
    from . import decoder_architecture_initializations as initializations,decoder_architecture_feasibility as feasibility,decoder_diagnostic_measurements,training_resources
    from .planned_decoder import PlannedDecoder
    from .run_manifest import digest,file_digest
else:
    import decoder_architecture_initializations as initializations,decoder_architecture_feasibility as feasibility,decoder_diagnostic_measurements,training_resources
    from planned_decoder import PlannedDecoder
    from run_manifest import digest,file_digest


def metal_functions(config,mx):
    def norm(x):return (x-mx.mean(x,axis=-1,keepdims=True))/mx.sqrt(mx.var(x,axis=-1,keepdims=True)+1e-5)
    def logits(p,tokens):
        rows,length=tokens.shape;heads,dim=config['attention_heads'],config['head_dim']
        hidden=p['token_embedding'][tokens]+p['position_embedding'][:length]
        for layer in range(config['layers']):
            prefix=f'layers.{layer}.';x=norm(hidden)
            q,k,v=[(x@p[prefix+name]).reshape(rows,length,heads,dim).transpose(0,2,1,3) for name in ('query','key','value')]
            scores=(q@mx.swapaxes(k,-1,-2))/(dim**.5)
            causal=mx.triu(mx.full((length,length),-float('inf')),k=1)
            attended=(mx.softmax(scores+causal,axis=-1)@v).transpose(0,2,1,3).reshape(rows,length,config['hidden_size'])
            hidden=hidden+attended@p[prefix+'attention_output']
            hidden=hidden+mx.maximum(norm(hidden)@p[prefix+'feed_forward_in'],0)@p[prefix+'feed_forward_out']
        return norm(hidden)@p['head']
    def loss(p,x,y,mask):
        scores=logits(p,x);correct=mx.take_along_axis(scores,y[...,None],axis=-1).squeeze(-1)
        return mx.sum((mx.logsumexp(scores,axis=-1)-correct)*mask)/mx.sum(mask)
    return logits,loss,mx.grad(loss)


def cpu_loss(model,x,y,mask):
    scores=model.logits(x).astype(np.float64);maximum=scores.max(axis=-1)
    losses=maximum+np.log(np.exp(scores-maximum[...,None]).sum(axis=-1))-np.take_along_axis(scores,y[...,None],axis=-1).squeeze(-1)
    return float((losses*mask).sum()/mask.sum())


def _folder(root,plan_id):return Path(root)/'decoder-architecture-backward-checks'/plan_id


def run_isolated(root,plan_id,confirmed,reviewed,reviewed_feasibility=None):
    if confirmed is not True:raise ValueError('Confirm the isolated synthetic diagnostic before starting a worker.')
    feasibility.admit(root,plan_id,reviewed,reviewed_feasibility)
    payload={'root':str(Path(root).resolve()),'plan_id':plan_id,'confirmed':True,'reviewed':reviewed,'reviewed_feasibility':reviewed_feasibility}
    try:
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('decoder_diagnostic_worker.py'))],
                              input=json.dumps(payload,allow_nan=False),capture_output=True,text=True,timeout=120,check=False)
    except subprocess.TimeoutExpired as error:raise ValueError('Isolated diagnostic timed out; no report published.') from error
    try:report=json.loads(result.stdout)
    except (ValueError,TypeError) as error:raise ValueError('Isolated diagnostic returned an invalid record; no report published.') from error
    if not isinstance(report,dict):raise ValueError('Isolated diagnostic returned an invalid record; no report published.')
    if result.returncode:raise ValueError('Isolated diagnostic failed: '+str(report.get('error','worker exited')))
    if (report.get('format')!='almg-planned-decoder-backward-check-v4' or report.get('revision')!=digest({k:v for k,v in report.items() if k!='revision'})
            or report.get('plan_id')!=plan_id or report.get('initialization_revision')!=reviewed.get('revision')
            or report.get('diagnostic_measurements',{}).get('isolated_trial_peak_measured') is not True):raise ValueError('Isolated diagnostic binding failed; no report published.')
    if initializations.read(root,plan_id,reviewed['id'])!=reviewed:raise ValueError('Initialized model changed during the isolated diagnostic; no report published.')
    return _publish(root,report)


def run(root,plan_id,confirmed,reviewed,reviewed_feasibility=None,publish=True):
    if confirmed is not True:raise ValueError('Confirm five synthetic Metal optimizer steps; updated weights will be discarded and no training/release is approved.')
    if not isinstance(reviewed,dict):raise ValueError('Reopen the exact saved initialized architecture.')
    admission=feasibility.admit(root,plan_id,reviewed,reviewed_feasibility)
    current=initializations.read(root,plan_id,reviewed.get('id'))
    if current!=reviewed:raise ValueError('Initialized architecture review changed.')
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise ValueError('This bounded backward check requires Apple silicon Metal.')
    import mlx.core as mx
    if not mx.metal.is_available():raise ValueError('Metal is unavailable.')
    resources=training_resources.check_size(max(current['actual_weight_bytes']*8,65536),Path(root))
    model=PlannedDecoder.load(initializations._folder(root,plan_id)/current['id']/'model.json');c=model.config
    rows=min(2,c['batch_size']);length=min(8,c['context_length'])
    sequence=np.arange(rows*(length+1)).reshape(rows,length+1)%c['vocab_size'];x=sequence[:,:-1];y=sequence[:,1:];mask=np.ones_like(y,dtype=np.float32)
    padding=min(2,length-1 if rows>1 else length-2)
    if padding:mask[-1,-padding:]=0
    altered=y.copy();altered[mask==0]=(altered[mask==0]+1)%c['vocab_size']
    with mx.stream(mx.gpu):
        measurements=decoder_diagnostic_measurements.DiagnosticMeasurements(mx)
        p={name:mx.array(value) for name,value in model.parameters.items()};logits,loss,gradient=metal_functions(c,mx)
        tx=mx.array(x);ty=mx.array(y);tm=mx.array(mask);ta=mx.array(altered)
        initial=float(loss(p,tx,ty,tm).item());grads=gradient(p,tx,ty,tm);mx.eval(grads)
        measurements.sample('initial_backward')
        cpu_error=float(np.max(np.abs(model.logits(x)-np.array(logits(p,tx)))))
        norms={name:float(np.linalg.norm(np.array(value))) for name,value in grads.items()}
        if set(grads)!=set(p) or any(not np.isfinite(np.array(value)).all() for value in grads.values()) or any(value<=0 or not np.isfinite(value) for value in norms.values()):raise ValueError('Backward gradients are missing, nonfinite or vacuous; no report saved.')
        padding_loss_error=abs(initial-float(loss(p,tx,ta,tm).item()));other=gradient(p,tx,ta,tm);mx.eval(other)
        padding_gradient_error=max(float(np.max(np.abs(np.array(grads[name])-np.array(other[name])))) for name in p)
        probes=[]
        for name in ('head','layers.0.query',f"layers.{c['layers']-1}.feed_forward_in"):
            array=model.parameters[name];analytic=np.array(grads[name]);index=np.unravel_index(np.argmax(np.abs(analytic)),analytic.shape);original=array[index].copy()
            try:
                array[index]=original+.001;plus=float(array[index]);upper=cpu_loss(model,x,y,mask)
                array[index]=original-.001;minus=float(array[index]);lower=cpu_loss(model,x,y,mask)
            finally:array[index]=original
            numeric=(upper-lower)/(plus-minus);automatic=float(analytic[index]);error=abs(numeric-automatic);limit=1e-6+.02*max(abs(numeric),abs(automatic))
            if not np.isfinite([numeric,automatic,error]).all() or error>limit:raise ValueError('Independent CPU finite-difference gradient check failed; no report saved.')
            probes.append({'parameter':name,'index':[int(value) for value in index],'autodiff':automatic,'cpu_finite_difference':numeric,'absolute_error':error,'tolerance':limit,'epsilon':.001})
        for step in range(5):
            values=gradient(p,tx,ty,tm)
            if any(not np.isfinite(np.array(value)).all() for value in values.values()):raise ValueError('Nonfinite optimizer gradient; no report saved.')
            p={name:p[name]-.05*values[name] for name in p};mx.eval(p)
            measurements.sample(f'optimizer_step_{step+1}')
        final=float(loss(p,tx,ty,tm).item());updated={name:np.array(value) for name,value in p.items()}
        changed=[name for name,value in model.parameters.items() if not np.array_equal(value,updated[name])]
        if any(not np.isfinite(value).all() for value in updated.values()):raise ValueError('Nonfinite diagnostic parameters; no report saved.')
        model.parameters=updated;final_cpu_error=float(np.max(np.abs(model.logits(x)-np.array(logits(p,tx)))))
        if (not np.isfinite([initial,final,cpu_error,final_cpu_error,padding_loss_error,padding_gradient_error]).all()
                or final>=initial or len(changed)!=len(p) or max(cpu_error,final_cpu_error)>=1e-5 or padding_loss_error>1e-6 or padding_gradient_error>1e-6):raise ValueError('Planned-model backward numerical checks failed; no report saved.')
        observed=measurements.finish(admission['estimates']['estimated_gpu_working_bytes'])
    if initializations.read(root,plan_id,current['id'])!=current:raise ValueError('Initialized model changed during the backward check; no report saved.')
    report={'format':'almg-planned-decoder-backward-check-v4','schema_version':4,'id':uuid.uuid4().hex,'plan_id':plan_id,'initialization_id':current['id'],
            'initialization_revision':current['revision'],'model_sha256':current['model_sha256'],'config':c,'steps':5,'learning_rate':.05,
            'batch_shape':list(x.shape),'real_target_tokens':int(mask.sum()),'padding_check_applicable':bool(padding),'padded_targets_changed':int(np.sum(altered!=y)),
            'initial_loss':initial,'final_loss':final,'cpu_metal_max_error_before':cpu_error,'cpu_metal_max_error_after':final_cpu_error,
            'padding_loss_error':padding_loss_error,'padding_gradient_error':padding_gradient_error,'gradient_norms':norms,'finite_difference_probes':probes,
            'parameter_tensors':len(p),'changed_parameter_tensors':changed,'backward_checked':True,'updated_weights_saved':False,
            'source_initialization_unchanged':True,'training_approved':False,'release_approved':False,'resources':resources,
            'hardware_feasibility':admission,'approved_feasibility_revision':reviewed_feasibility['revision'] if isinstance(reviewed_feasibility,dict) else None,
            'diagnostic_measurements':observed,
            'runtime':{'device':'Metal GPU','mlx':version('mlx'),'numpy':np.__version__},
            'scope':'five_step_synthetic_numerical_diagnostic_only_no_model_quality_claim',
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_architecture_backward.py','decoder_architecture_feasibility.py','decoder_diagnostic_measurements.py','decoder_diagnostic_worker.py','planned_decoder.py')})}
    report['revision']=digest(report)
    return _publish(root,report) if publish else report


def _publish(root,report):
    parent=_folder(root,report['plan_id']);parent.mkdir(parents=True,exist_ok=True);temporary=None
    try:
        with NamedTemporaryFile(mode='w',encoding='utf-8',dir=parent,prefix='.check-',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name);stream.write(json.dumps(report,allow_nan=False,indent=2))
        temporary.replace(parent/(report['id']+'.json'))
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return report


def list_reports(root,plan_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm review of private backward diagnostic reports.')
    initializations.plans.read(root,plan_id);reports=[]
    for path in sorted(_folder(root,plan_id).glob('*.json')):
        try:
            if path.stat().st_size>128000:continue
            report=json.loads(path.read_text(encoding='utf-8'));source=initializations.read(root,plan_id,report['initialization_id'])
            version={'almg-planned-decoder-backward-check-v1':1,'almg-planned-decoder-backward-check-v2':2,'almg-planned-decoder-backward-check-v3':3,'almg-planned-decoder-backward-check-v4':4}.get(report.get('format'))
            if (version is None or type(report.get('schema_version')) is not int or report['schema_version']!=version
                    or report.get('id')!=path.stem or report.get('plan_id')!=plan_id or report.get('revision')!=digest({k:v for k,v in report.items() if k!='revision'})
                    or report.get('initialization_revision')!=source['revision'] or report.get('model_sha256')!=source['model_sha256']
                    or report.get('backward_checked') is not True or any(report.get(key) is not False for key in ('updated_weights_saved','training_approved','release_approved'))):continue
            if version>=2:
                profile=report['hardware_feasibility']
                if (profile.get('revision')!=digest({k:v for k,v in profile.items() if k!='revision'}) or profile.get('feasible') is not True
                        or profile.get('source',{}).get('initialization_revision')!=source['revision'] or profile['source'].get('model_sha256')!=source['model_sha256']):continue
            reports.append(report)
        except (OSError,ValueError,TypeError,KeyError):continue
    return reports[-20:]
