"""Read-only held-out next-token evaluation of verified completed corpus models."""
import math
from pathlib import Path
import numpy as np
if __package__:
    from . import decoder_corpus_optimizer as training
    from .run_manifest import digest, file_digest
else:
    import decoder_corpus_optimizer as training
    from run_manifest import digest, file_digest

PROTOCOL = {'format':'almg-corpus-heldout-protocol-v1','schema_version':1,
            'task':'causal_next_token_pretraining','splits':['validation','test'],
            'loss':'masked_mean_cross_entropy_nats','perplexity':'exp_mean_cross_entropy',
            'padding':'exclude_mask_zero','runtime':'planned_decoder_numpy_cpu',
            'failure_examples':'first_eight_masked_argmax_mismatches_in_saved_window_order'}


def perplexity(loss):
    if type(loss) not in (int,float) or not math.isfinite(loss) or loss < 0:
        raise ValueError('Held-out loss must be finite and nonnegative.')
    try:
        return math.exp(loss), 'available'
    except OverflowError:
        return None, 'overflow_unavailable'


def score_split(model, windows, vocabulary):
    losses=[];correct=0;dense=0;failures=[]
    for index,row in enumerate(windows):
        inputs=np.asarray([row['inputs']],dtype=np.int32)
        targets=np.asarray(row['targets'],dtype=np.int32);active=np.asarray(row['target_mask'],dtype=bool)
        scores=np.asarray(model.logits(inputs),dtype=np.float64)
        if scores.shape != (1,len(targets),len(vocabulary)) or not np.isfinite(scores).all():
            raise ValueError('Invalid held-out model logits.')
        scores=scores[0];maximum=scores.max(axis=-1)
        values=maximum+np.log(np.exp(scores-maximum[:,None]).sum(axis=-1))-scores[np.arange(len(targets)),targets]
        real=values[active]
        if not np.isfinite(real).all() or np.any(real<0):raise ValueError('Invalid held-out target losses.')
        losses.extend(float(value) for value in real);dense+=len(targets)
        predicted=scores.argmax(axis=-1);correct+=int(np.sum((predicted==targets)&active))
        for position in np.flatnonzero(active & (predicted!=targets)):
            if len(failures)<8:
                expected=int(targets[position]);actual=int(predicted[position])
                failures.append({'window_index':index,'position':int(position),'expected_id':expected,'predicted_id':actual,
                                 'expected_token':vocabulary[expected],'predicted_token':vocabulary[actual]})
    if not losses:raise ValueError('Held-out splits require real target tokens.')
    loss=math.fsum(losses)/len(losses);ppl,status=perplexity(loss)
    return {'window_count':len(windows),'target_tokens':len(losses),'dense_positions':dense,
            'padding_positions':dense-len(losses),'cross_entropy_nats_per_target':loss,
            'perplexity':ppl,'perplexity_status':status,'teacher_forced_token_accuracy':correct/len(losses),
            'failure_examples':failures}


def evaluation_context(root, identifier, *, original_initialization=False):
    record=training.read(root,identifier)
    if record.get('status','completed')!='completed':raise ValueError('Evaluate a verified completed corpus model, not partial training.')
    origin=record['review']['source']
    initialized=training.hardware.initializations.read(root,origin['plan_id'],origin['initialization_id'])
    corpus=training.inputs.read(root,record['review']['corpus_id'])
    _,_,_,windows,tokenizer=training._source(root,initialized,corpus)
    if original_initialization:
        model_path=training.hardware.initializations._folder(root,origin['plan_id'])/initialized['id']/'model.json'
        source={'kind':'original_initialization','initialization_id':initialized['id'],
                'initialization_revision':initialized['revision'],'model_sha256':initialized['model_sha256'],
                'optimizer_updates':0}
    else:
        model_path=training._folder(root,identifier)/'trained-model.json'
        source={'record_id':record['id'],'record_revision':record['revision'],'model_sha256':record['files']['trained-model.json']}
    model=training.PlannedDecoder.load(model_path)
    return model,windows,tokenizer,source,corpus


def data_binding(corpus):
    binding={key:corpus['review'][key] for key in ('dataset_id','dataset_revision','dataset_sha256','sequence_length')}
    binding.update(windows_sha256=corpus['files']['windows.json'],tokenizer_sha256=corpus['files']['tokenizer.json'])
    return binding


def _evaluate_one(root, identifier, *, original_initialization=False):
    model,windows,tokenizer,source,corpus=evaluation_context(root,identifier,original_initialization=original_initialization)
    return {'format':'almg-corpus-heldout-evaluation-v1','schema_version':1,
            'protocol':dict(PROTOCOL,splits=list(PROTOCOL['splits'])),'protocol_revision':digest(PROTOCOL),
            'source':source,
            'corpus_id':corpus['id'],'corpus_revision':corpus['revision'],'evaluation_data_binding':data_binding(corpus),
            'metrics':{split:score_split(model,windows[split],tokenizer.vocabulary) for split in PROTOCOL['splits']},
            'runtime':{'numpy':np.__version__,'precision':'float32_model_logits_float64_loss_accumulation'},
            'training_approved':False,'release_approved':False,'language_quality_validated':False,
            'evaluation_stage':'pretraining_heldout_next_token_diagnostics',
            'limitations':'Saved held-out windows only, with zero-mask padding excluded. Teacher-forced token accuracy and deterministic mismatch examples are diagnostics, not free-running text quality, instruction following or general capability. Comparison requires identical protocol and reviewed data/tokenizer/window bindings. Perplexity overflow is unavailable rather than infinity. Evaluation neither modifies source artifacts nor approves training/release.',
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_corpus_evaluation.py','planned_decoder.py','decoder_corpus_optimizer.py','decoder_corpus_inputs.py')})}


def compare(candidate, baseline):
    if candidate['protocol_revision']!=baseline['protocol_revision'] or candidate['evaluation_data_binding']!=baseline['evaluation_data_binding']:
        raise ValueError('Compare models using the same held-out protocol, corpus windows and tokenizer.')
    deltas={}
    for split in PROTOCOL['splits']:
        left=candidate['metrics'][split];right=baseline['metrics'][split]
        deltas[split]={'cross_entropy_nats_per_target':left['cross_entropy_nats_per_target']-right['cross_entropy_nats_per_target'],
                       'perplexity':None if left['perplexity'] is None or right['perplexity'] is None else left['perplexity']-right['perplexity']}
    return {'baseline_source':baseline['source'],'baseline_metrics':baseline['metrics'],'candidate_minus_baseline':deltas}


def evaluate(root, identifier, baseline_id=None, *, baseline_initialization=False):
    if type(baseline_initialization) is not bool:
        raise ValueError('baseline_initialization must be a boolean.')
    if baseline_initialization and baseline_id is not None:
        raise ValueError('Choose either a saved model baseline or the original initialization.')
    result=_evaluate_one(root,identifier)
    if baseline_initialization:
        result['comparison']=compare(result,_evaluate_one(root,identifier,original_initialization=True))
    else:
        result['comparison']=None if baseline_id is None else compare(result,_evaluate_one(root,baseline_id))
    result['revision']=digest(result)
    return result
