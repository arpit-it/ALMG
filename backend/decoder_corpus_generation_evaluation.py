"""Bounded read-only free-running continuations from saved held-out windows."""
from pathlib import Path
import numpy as np
if __package__:
    from . import decoder_corpus_evaluation as heldout
    from .run_manifest import digest, file_digest
else:
    import decoder_corpus_evaluation as heldout
    from run_manifest import digest, file_digest

PROTOCOL = {'format':'almg-corpus-generation-protocol-v1','schema_version':1,
            'splits':['validation','test'],'max_windows_per_split':8,'prompt_tokens':1,
            'max_new_tokens':4,'decoding':'greedy_first_argmax_without_teacher_forcing',
            'reference':'active_target_prefix_in_saved_window_order',
            'length':'minimum_of_four_and_real_reference_targets','context':'model_context_suffix',
            'runtime':'planned_decoder_numpy_cpu','early_stopping':'none'}


def score_split(model, windows, tokenizer):
    examples=[];matches=0;targets=0;repeats=0;transitions=0
    vocabulary=tokenizer.vocabulary
    for index,row in enumerate(windows[:PROTOCOL['max_windows_per_split']]):
        mask=row['target_mask'];count=sum(mask)
        if not count:continue
        if mask != [1]*count+[0]*(len(mask)-count):
            raise ValueError('Generation references require right-padded target masks.')
        reference=row['targets'][:min(PROTOCOL['max_new_tokens'],count)]
        prompt=row['inputs'][:PROTOCOL['prompt_tokens']];state=list(prompt);generated=[]
        for _ in reference:
            context=state[-model.config['context_length']:]
            scores=np.asarray(model.logits(np.asarray([context],dtype=np.int32)))
            if scores.shape!=(1,len(context),len(vocabulary)) or not np.isfinite(scores).all():
                raise ValueError('Invalid free-running generation logits.')
            token=int(np.argmax(scores[0,-1]));generated.append(token);state.append(token)
        matching=sum(a==b for a,b in zip(generated,reference));prefix=0
        for a,b in zip(generated,reference):
            if a!=b:break
            prefix+=1
        adjacent=sum(a==b for a,b in zip(generated,generated[1:]))
        matches+=matching;targets+=len(reference);repeats+=adjacent;transitions+=max(0,len(generated)-1)
        examples.append({'window_index':index,'prompt_token_ids':prompt,'reference_token_ids':reference,
                         'generated_token_ids':generated,'prompt_text':tokenizer.decode(prompt),
                         'reference_text':tokenizer.decode(reference),'generated_text':tokenizer.decode(generated),
                         'exact_match':generated==reference,'matching_prefix_tokens':prefix,
                         'adjacent_repeat_count':adjacent})
    if not examples:raise ValueError('Generation evaluation requires real held-out reference targets.')
    exact=sum(row['exact_match'] for row in examples)
    return {'window_count':len(examples),'reference_target_tokens':targets,'generated_tokens':targets,
            'exact_continuation_matches':exact,'exact_continuation_match_rate':exact/len(examples),
            'free_running_reference_token_match_rate':matches/targets,
            'adjacent_repeat_count':repeats,'generated_transitions':transitions,
            'adjacent_repeat_rate':repeats/transitions if transitions else None,'examples':examples}


def _one(root, identifier, *, original_initialization=False):
    model,windows,tokenizer,source,corpus=heldout.evaluation_context(root,identifier,original_initialization=original_initialization)
    return {'format':'almg-corpus-generation-evaluation-v1','schema_version':1,
            'protocol':dict(PROTOCOL,splits=list(PROTOCOL['splits'])),'protocol_revision':digest(PROTOCOL),
            'source':source,'corpus_id':corpus['id'],'corpus_revision':corpus['revision'],
            'evaluation_data_binding':heldout.data_binding(corpus),
            'metrics':{split:score_split(model,windows[split],tokenizer) for split in PROTOCOL['splits']},
            'runtime':{'numpy':np.__version__,'precision':'float32_model_logits'},
            'training_approved':False,'release_approved':False,'language_quality_validated':False,
            'evaluation_stage':'pretraining_free_running_continuation_diagnostics',
            'limitations':'First eight saved windows per held-out split, one-token prompts and at most four generated tokens per window. Generated tokens, never reference targets, extend the prompt. Exact reference matches and adjacent repeats are narrow diagnostics, not language quality, assistant capability, semantic correctness or memorization/leakage certification. Reference target counts determine bounded generation length; no EOS behavior or latency/throughput is measured. No training or release approval and no artifact writes.',
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_corpus_generation_evaluation.py','decoder_corpus_evaluation.py','planned_decoder.py','decoder_corpus_optimizer.py','decoder_corpus_inputs.py','decoder_tokenizer.py')})}


def compare(candidate, baseline):
    if candidate['protocol_revision']!=baseline['protocol_revision'] or candidate['evaluation_data_binding']!=baseline['evaluation_data_binding']:
        raise ValueError('Compare generation using the same protocol, corpus windows and tokenizer.')
    deltas={}
    for split in PROTOCOL['splits']:
        left=candidate['metrics'][split];right=baseline['metrics'][split]
        deltas[split]={key:None if left[key] is None or right[key] is None else left[key]-right[key]
                       for key in ('exact_continuation_match_rate','free_running_reference_token_match_rate','adjacent_repeat_rate')}
    return {'baseline_source':baseline['source'],'baseline_metrics':baseline['metrics'],'candidate_minus_baseline':deltas}


def evaluate(root, identifier, baseline_id=None, *, baseline_initialization=False):
    if type(baseline_initialization) is not bool:raise ValueError('baseline_initialization must be a boolean.')
    if baseline_initialization and baseline_id is not None:raise ValueError('Choose either a saved model baseline or the original initialization.')
    result=_one(root,identifier)
    baseline=_one(root,identifier,original_initialization=True) if baseline_initialization else (_one(root,baseline_id) if baseline_id is not None else None)
    result['comparison']=None if baseline is None else compare(result,baseline)
    result['revision']=digest(result)
    return result
