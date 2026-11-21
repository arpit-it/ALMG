"""Read-only scoring of completed corpus models on reviewed evaluation-only text."""
import json
from pathlib import Path
import numpy as np
if __package__:
    from . import decoder_corpus_benchmarks as benchmarks, decoder_corpus_evaluation as heldout, decoder_corpus_generation_evaluation as generation, decoder_corpus_leakage_audit as overlap, decoder_corpus_document_overlap as document_overlap
    from .decoder_tokenizer import Tokenizer
    from .run_manifest import digest,file_digest
else:
    import decoder_corpus_benchmarks as benchmarks, decoder_corpus_evaluation as heldout, decoder_corpus_generation_evaluation as generation, decoder_corpus_leakage_audit as overlap, decoder_corpus_document_overlap as document_overlap
    from decoder_tokenizer import Tokenizer
    from run_manifest import digest,file_digest

PROTOCOL={'format':'almg-corpus-benchmark-evaluation-protocol-v2','schema_version':2,
          'task':'causal_next_token_pretraining','loss_population':'all_saved_benchmark_windows',
          'generation_population':'first_eight_saved_benchmark_windows',
          'loss_kernel_protocol_revision':digest(heldout.PROTOCOL),'generation_kernel_protocol_revision':digest(generation.PROTOCOL),
          'overlap_protocol_revision':digest(overlap.PROTOCOL),'document_overlap_protocol_revision':digest(document_overlap.PROTOCOL),'training_or_tokenizer_updates':False}


def _one(root, record, windows, tokenizer, identifier, *, original_initialization=False):
    model,existing,current_tokenizer,source,corpus=heldout.evaluation_context(root,identifier,original_initialization=original_initialization)
    if (heldout.data_binding(corpus)!=record['review']['training_data_binding']
        or current_tokenizer.fingerprint()!=record['review']['tokenizer_sha256']
        or corpus['review']['sequence_length']!=record['review']['sequence_length']):
        raise ValueError('Benchmark requires its reviewed training data, sequence length and fixed tokenizer.')
    findings={split:overlap.audit_pair(windows,existing[split],tokenizer) for split in ('train','validation','test')}
    if any(item['overlap_detected'] for item in findings.values()):raise ValueError('Current corpus overlap checks block benchmark scoring; review separate evaluation text.')
    document_findings={split:document_overlap.audit_pair(windows,existing[split],tokenizer) for split in ('train','validation','test')}
    if any(item['overlap_detected'] for item in document_findings.values()):raise ValueError('Document-level overlap, including cross-window spans, blocks benchmark scoring; provide separate evaluation text.')
    result={'format':'almg-corpus-benchmark-evaluation-v2','schema_version':2,
            'protocol':dict(PROTOCOL),'protocol_revision':digest(PROTOCOL),'source':source,
            'benchmark_binding':{'id':record['id'],'revision':record['revision'],'review_revision':record['review']['revision'],
                                 'files':dict(record['files']),'training_data_binding':record['review']['training_data_binding']},
            'sources':record['review']['sources'],'current_overlap_checks':findings,'current_document_overlap_checks':document_findings,
            'metrics':{'heldout':heldout.score_split(model,windows,tokenizer.vocabulary),
                       'generation':generation.score_split(model,windows,tokenizer)},
            'runtime':{'numpy':np.__version__,'device':'CPU','precision':'float32_model_logits_float64_loss_accumulation'},
            'training_approved':False,'release_approved':False,'language_quality_validated':False,'independent_evaluation_certified':False,
            'limitations':'Scores only the explicitly saved evaluation-only benchmark snapshot with its fixed tokenizer. Loss uses all at most 32 windows; free-running generation uses at most eight windows and four tokens per window. Candidate and baseline use the same benchmark, current protocols and runtime. Training data/tokenizer bindings and window/document/four-token corpus overlap checks, including cross-window spans, must still pass. User provenance declarations and narrow overlap checks do not certify global/semantic independence or general model/assistant capability. No training/tokenizer updates, release approval, benchmark mutation or artifact writes.',
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_corpus_benchmark_evaluation.py','decoder_corpus_benchmarks.py','decoder_corpus_evaluation.py','decoder_corpus_generation_evaluation.py','decoder_corpus_leakage_audit.py','decoder_corpus_document_overlap.py','planned_decoder.py')})}
    return result


def compare(candidate, baseline):
    if any(candidate[key]!=baseline[key] for key in ('benchmark_binding','protocol_revision','runtime','implementation_sha256')):
        raise ValueError('Compare models using the same benchmark, scoring protocol and runtime.')
    deltas={}
    for section,keys in (('heldout',('cross_entropy_nats_per_target','perplexity','teacher_forced_token_accuracy')),
                         ('generation',('exact_continuation_match_rate','free_running_reference_token_match_rate','adjacent_repeat_rate'))):
        left=candidate['metrics'][section];right=baseline['metrics'][section]
        deltas[section]={key:None if left[key] is None or right[key] is None else left[key]-right[key] for key in keys}
    return {'baseline_source':baseline['source'],'baseline_metrics':baseline['metrics'],'candidate_minus_baseline':deltas}


def evaluate(root, benchmark_id, candidate_id, baseline_id=None, *, baseline_initialization=False):
    if type(baseline_initialization) is not bool:raise ValueError('baseline_initialization must be a boolean.')
    if baseline_initialization and baseline_id is not None:raise ValueError('Choose either a saved model baseline or the original initialization.')
    record=benchmarks.read(root,benchmark_id);folder=Path(root)/'decoder-corpus-benchmarks'/record['id']
    windows=json.loads((folder/'windows.json').read_text(encoding='utf-8'))
    tokenizer=Tokenizer.restore(json.loads((folder/'tokenizer.json').read_text(encoding='utf-8')))
    if digest(windows)!=record['review']['windows_sha256'] or tokenizer.fingerprint()!=record['review']['tokenizer_sha256']:
        raise ValueError('Benchmark inputs changed during evaluation; reopen the snapshot.')
    result=_one(root,record,windows,tokenizer,candidate_id)
    baseline=_one(root,record,windows,tokenizer,candidate_id,original_initialization=True) if baseline_initialization else (_one(root,record,windows,tokenizer,baseline_id) if baseline_id is not None else None)
    result['comparison']=None if baseline is None else compare(result,baseline)
    result['revision']=digest(result)
    return result
