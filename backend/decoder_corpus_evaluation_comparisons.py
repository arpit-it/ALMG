"""Read-only comparisons of verified historical evaluation snapshots."""
import math
from pathlib import Path
if __package__:
    from . import decoder_corpus_evaluations as evaluations
    from .run_manifest import digest,file_digest
else:
    import decoder_corpus_evaluations as evaluations
    from run_manifest import digest,file_digest


def _delta(candidate, baseline, *, nullable=False, maximum=None):
    for value in (candidate,baseline):
        if value is None and nullable:continue
        if type(value) not in (int,float) or not math.isfinite(value) or value<0 or (maximum is not None and value>maximum):
            raise ValueError('Saved comparison metrics must be valid finite observations.')
    return None if candidate is None or baseline is None else candidate-baseline


def _compare_reports(candidate, baseline):
    if candidate['evaluation_data_binding']!=baseline['evaluation_data_binding']:
        raise ValueError('Compare snapshots using identical reviewed data, windows and tokenizer.')
    for section in ('heldout','generation','overlap'):
        left=candidate[section];right=baseline[section]
        if left['protocol_revision']!=right['protocol_revision'] or left['implementation_sha256']!=right['implementation_sha256']:
            raise ValueError('Compare snapshots using identical evaluation protocols and scoring implementations.')
        if section!='overlap' and left['runtime']!=right['runtime']:
            raise ValueError('Compare snapshots using identical scoring runtimes.')
    heldout={};generation={};examples={}
    for split in ('validation','test'):
        left=candidate['heldout']['metrics'][split];right=baseline['heldout']['metrics'][split]
        if any(left[key]!=right[key] for key in ('window_count','target_tokens','dense_positions','padding_positions')):
            raise ValueError('Saved held-out metric coverage changed; re-evaluate both models.')
        heldout[split]={'cross_entropy_nats_per_target':_delta(left['cross_entropy_nats_per_target'],right['cross_entropy_nats_per_target']),
                        'perplexity':_delta(left['perplexity'],right['perplexity'],nullable=True),
                        'teacher_forced_token_accuracy':_delta(left['teacher_forced_token_accuracy'],right['teacher_forced_token_accuracy'],maximum=1)}
        examples[split]={'candidate_teacher_forced_failures':left['failure_examples'][:8],
                         'baseline_teacher_forced_failures':right['failure_examples'][:8]}
        left=candidate['generation']['metrics'][split];right=baseline['generation']['metrics'][split]
        if any(left[key]!=right[key] for key in ('window_count','reference_target_tokens','generated_tokens','generated_transitions')):
            raise ValueError('Saved generation metric coverage changed; re-evaluate both models.')
        generation[split]={key:_delta(left[key],right[key],nullable=key=='adjacent_repeat_rate',maximum=1)
                           for key in ('exact_continuation_match_rate','free_running_reference_token_match_rate','adjacent_repeat_rate')}
        examples[split].update(candidate_continuations=left['examples'][:8],baseline_continuations=right['examples'][:8])
    return heldout,generation,examples


def compare(root, candidate_id, baseline_id):
    candidate=evaluations.read(root,candidate_id);baseline=evaluations.read(root,baseline_id)
    left=candidate['report'];right=baseline['report']
    loss,generation,examples=_compare_reports(left,right)
    def source(item):
        return {'evaluation_id':item['record']['id'],'manifest_revision':item['record']['revision'],
                'report_revision':item['report']['revision'],'model_source':item['report']['source']}
    result={'format':'almg-saved-corpus-evaluation-comparison-v1','schema_version':1,
            'candidate':source(candidate),'baseline':source(baseline),
            'evaluation_data_binding':left['evaluation_data_binding'],
            'protocol_revisions':{key:left[key]['protocol_revision'] for key in ('heldout','generation','overlap')},
            'scoring_implementation_sha256':{key:left[key]['implementation_sha256'] for key in ('heldout','generation','overlap')},
            'scoring_runtimes':{key:left[key]['runtime'] for key in ('heldout','generation')},
            'candidate_minus_baseline':{'heldout':loss,'generation':generation},'examples':examples,
            'overlap_requires_review':left['overlap']['requires_overlap_review'] or right['overlap']['requires_overlap_review'],
            'training_approved':False,'release_approved':False,'language_quality_validated':False,
            'limitations':'Direct candidate-minus-baseline differences between stored trained-model results, not between their embedded initialization deltas. Protocols, data, scoring implementations, runtimes and metric coverage must match. Historical snapshot integrity is checked without reloading or re-evaluating models. Examples are bounded stored diagnostics, not exhaustive regression counts or semantic review. Lower loss/perplexity and higher exact/token match describe only these narrow metrics; repetition changes alone do not establish quality. Null differences retain unavailable metrics. Overlap findings remain review-needed. No current-model validation, training/release approval, general capability claim or artifact writes.',
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_corpus_evaluation_comparisons.py','decoder_corpus_evaluations.py')})}
    result['revision']=digest(result)
    return result
