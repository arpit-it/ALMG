"""Explicit five-step masked Metal diagnostic; model weights are never published."""
import json
import math
from pathlib import Path
import platform
import uuid

if __package__:
    from . import decoder_stream_batches as batches, recipe_contracts, decoder_bundle
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_batches as batches
    import recipe_contracts
    import decoder_bundle
    from run_manifest import digest,file_digest


def evaluate_split(root,window_id,reviewed,split,score):
    """Forward-only complete split evaluation, with bounded batches and token weighting."""
    if split not in ('validation','test'):raise ValueError('Evaluate a held-out split.')
    seen_windows=targets=correct=0;loss_sum=0.0;page_count=0
    for batch in batches.iter_batches(root,window_id,True,reviewed,split,16):
        if not batch['rows'] or batch['real_target_tokens']<=0:
            raise ValueError('Held-out evaluation encountered an empty batch.')
        page_loss,page_correct=score(batch)
        if (not math.isfinite(page_loss) or page_loss<0 or type(page_correct) is not int
                or not 0<=page_correct<=batch['real_target_tokens']):
            raise ValueError('Held-out evaluation produced invalid metrics.')
        seen_windows+=batch['rows'];targets+=batch['real_target_tokens'];page_count+=1
        loss_sum+=page_loss;correct+=page_correct
    if seen_windows!=reviewed['window_counts'][split]:
        raise ValueError('Held-out evaluation did not cover the saved split population.')
    return {'windows':seen_windows,'target_tokens':targets,'correct_target_tokens':correct,
            'loss':loss_sum/targets,'next_token_accuracy':correct/targets,
            'batches':page_count,'maximum_batch_windows':16,'scope':'all_saved_split_windows',
            'aggregation':'sum_masked_token_losses_and_correct_predictions_divided_by_real_targets',
            'source_occurrences_expanded':False,'optimizer_updates':0,
            'integrity_policy':'full_hashes_at_split_start_and_end_stat_guards_each_batch'}


def run(root,window_id,confirmed,reviewed,reviewed_batch,cursor=None):
    if confirmed is not True:raise ValueError('Confirm the five-step masked optimizer diagnostic; no model is saved.')
    train=batches.read_batch(root,window_id,True,reviewed,cursor,'train',4)
    if not isinstance(reviewed_batch,dict) or reviewed_batch!=train:raise ValueError('The inspected training batch changed. Reopen it before the diagnostic.')
    if not train['rows']:raise ValueError('Select a nonempty training batch.')
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise ValueError('This diagnostic requires Apple silicon and local Metal access.')
    import mlx.core as mx
    import numpy as np
    if not mx.metal.is_available():raise ValueError('Metal is unavailable for the optimizer diagnostic.')
    model=recipe_contracts.initialize_recipe('decoder_from_scratch',{'vocab_size':256,'seed':7})
    before={name:np.array(value).copy() for name,value in model.parameters.items()}
    with mx.stream(mx.gpu):
        parameters={name:mx.array(value) for name,value in model.parameters.items()}
        x=mx.array(train['inputs']);y=mx.array(train['targets']);mask=mx.array(train['loss_mask'],dtype=mx.float32)
        def norm(values):
            return (values-mx.mean(values,axis=-1,keepdims=True))/mx.sqrt(mx.var(values,axis=-1,keepdims=True)+1e-5)
        def logits(p,tokens):
            hidden=p['token_embedding'][tokens]+p['position_embedding'][:tokens.shape[1]];normalized=norm(hidden)
            scores=(normalized@p['query'])@mx.swapaxes(normalized@p['key'],-1,-2)/(model.config['width']**.5)
            causal=mx.triu(mx.full((tokens.shape[1],tokens.shape[1]),-float('inf')),k=1)
            attention=mx.softmax(scores+causal,axis=-1)
            hidden=hidden+(attention@(normalized@p['value']))@p['attention_output']
            hidden=hidden+mx.maximum(norm(hidden)@p['feed_forward_in'],0)@p['feed_forward_out']
            return norm(hidden)@p['head']
        def loss(p,inputs,targets,weights):
            scores=logits(p,inputs)
            correct=mx.take_along_axis(scores,targets[...,None],axis=-1).squeeze(-1)
            return mx.sum((mx.logsumexp(scores,axis=-1)-correct)*weights)/mx.sum(weights)
        gradient=mx.grad(loss)
        initial=float(loss(parameters,x,y,mask).item())
        altered=mx.where(mask==0,(y+127)%256,y)
        padding_loss_error=abs(float(loss(parameters,x,altered,mask).item())-initial)
        original_gradient=gradient(parameters,x,y,mask);altered_gradient=gradient(parameters,x,altered,mask)
        padding_gradient_error=max(float(mx.max(mx.abs(original_gradient[name]-altered_gradient[name])).item()) for name in parameters)
        for _ in range(5):
            gradients=gradient(parameters,x,y,mask)
            parameters={name:value-.05*gradients[name] for name,value in parameters.items()};mx.eval(parameters)
        final=float(loss(parameters,x,y,mask).item())
        model.parameters={name:np.array(value) for name,value in parameters.items()}
        cpu_error=float(np.max(np.abs(model.logits(train['inputs'])-np.array(logits(parameters,x)))))
        changed=[name for name,value in model.parameters.items() if not np.array_equal(value,before[name])]
        if (not np.isfinite([initial,final,cpu_error,padding_loss_error,padding_gradient_error]).all()
                or not all(np.isfinite(value).all() for value in model.parameters.values())
                or final>=initial or len(changed)!=len(parameters) or cpu_error>=1e-5
                or padding_loss_error>1e-6 or padding_gradient_error>1e-6):
            raise ValueError('Masked optimizer diagnostic failed numerical checks; no report/model was published.')
        def score(batch):
            px=mx.array(batch['inputs']);py=mx.array(batch['targets']);pm=mx.array(batch['loss_mask'],dtype=mx.float32)
            scores=logits(parameters,px)
            correct_scores=mx.take_along_axis(scores,py[...,None],axis=-1).squeeze(-1)
            return (float(mx.sum((mx.logsumexp(scores,axis=-1)-correct_scores)*pm).item()),
                    int(mx.sum((mx.argmax(scores,axis=-1)==py)*pm).item()))
        evaluation={split:evaluate_split(root,window_id,reviewed,split,score) for split in ('validation','test')}

    # Recheck the exact source batch after GPU execution before writing evidence.
    if batches.read_batch(root,window_id,True,reviewed,cursor,'train',4)!=train:
        raise ValueError('Source bindings changed during the diagnostic; no report published.')
    report={'format':'almg-stream-masked-optimizer-check-v1','schema_version':1,'id':uuid.uuid4().hex,
            'windows_id':window_id,'windows_revision':reviewed['revision'],'training_batch_sha256':digest(train),
            'training_cursor':cursor,'training_provenance':train['provenance'],
            'steps':5,'learning_rate':.05,'seed':7,'model_config':model.config,
            'weight_origin':'newly_initialized','pretrained_weights_loaded':False,
            'trainable_parameters':sum(value.size for value in model.parameters.values()),
            'changed_parameter_tensors':changed,'parameter_tensors':len(parameters),
            'initial_batch_loss':initial,'final_batch_loss':final,'cpu_inference_max_error':cpu_error,
            'padded_positions':sum(16-length for length in train['sequence_lengths']),
            'masked_target_loss_error':padding_loss_error,'masked_target_gradient_error':padding_gradient_error,
            'evaluation':evaluation,'device':'Metal GPU','mlx_version':decoder_bundle.version('mlx'),
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in
                ('decoder_stream_optimization.py','decoder_stream_batches.py','decoder_recipe.py','decoder_tokenizer.py')}),
            'model_saved':False,'training_approved':False,'release_approved':False,
            'limitations':'Five-step numerical diagnostic on one batch. All saved held-out windows are evaluated without optimizer updates. Five updates on one training batch do not establish usable model quality or release readiness.'}
    report['revision']=digest(report)
    folder=Path(root)/'decoder-stream-optimization-checks'/window_id;folder.mkdir(parents=True,exist_ok=True)
    temporary=folder/(uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
        temporary.rename(folder/(report['id']+'.json'))
    finally:temporary.unlink(missing_ok=True)
    return report

def list_reports(root,window_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm local diagnostic report review.')
    batches.windows._folder(root,window_id)
    folder=Path(root)/'decoder-stream-optimization-checks'/window_id;reports=[]
    for path in sorted(folder.glob('*.json')) if folder.exists() else []:
        try:
            if path.stat().st_size>256*1024:continue
            report=json.loads(path.read_text(encoding='utf-8'))
            if (report.get('format')!='almg-stream-masked-optimizer-check-v1' or type(report.get('schema_version')) is not int
                    or report['schema_version']!=1 or report.get('id')!=path.stem or report.get('windows_id')!=window_id
                    or report.get('revision')!=digest({k:v for k,v in report.items() if k!='revision'})
                    or any(report.get(key) is not False for key in ('model_saved','training_approved','release_approved'))):
                continue
            reports.append(report)
        except (OSError,ValueError,TypeError):continue
    return reports[-20:]
