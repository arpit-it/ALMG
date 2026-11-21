"""Read-only comparison of compatible historical benchmark scoring snapshots."""
from pathlib import Path
if __package__:
    from . import decoder_corpus_benchmark_results as results, decoder_corpus_benchmark_evaluation as scoring
    from .run_manifest import digest,file_digest
else:
    import decoder_corpus_benchmark_results as results, decoder_corpus_benchmark_evaluation as scoring
    from run_manifest import digest,file_digest


def compare(root, candidate_id, baseline_id):
    candidate=results.read(root,candidate_id);baseline=results.read(root,baseline_id)
    left=candidate['report'];right=baseline['report']
    comparison=scoring.compare(left,right)
    for section,keys in (('heldout',('window_count','target_tokens','dense_positions','padding_positions')),
                         ('generation',('window_count','reference_target_tokens','generated_tokens','generated_transitions'))):
        if any(left['metrics'][section][key]!=right['metrics'][section][key] for key in keys):
            raise ValueError('Saved benchmark metric coverage changed; re-evaluate both models using the same benchmark protocol.')
    def source(item):
        return {'evaluation_id':item['record']['id'],'manifest_revision':item['record']['revision'],
                'report_revision':item['report']['revision'],'model_source':item['report']['source']}
    report={'format':'almg-saved-benchmark-evaluation-comparison-v1','schema_version':1,
            'candidate':source(candidate),'baseline':source(baseline),'benchmark_binding':left['benchmark_binding'],
            'protocol':left['protocol'],'protocol_revision':left['protocol_revision'],'runtime':left['runtime'],
            'scoring_implementation_sha256':left['implementation_sha256'],
            'candidate_metrics':left['metrics'],'comparison':comparison,'sources':left['sources'],
            'training_approved':False,'release_approved':False,'language_quality_validated':False,'independent_evaluation_certified':False,
            'limitations':'Direct candidate-minus-baseline comparison of stored trained-model benchmark metrics, not their embedded initialization/baseline deltas. Benchmark binding, protocol, scoring implementation, runtime and metric coverage must match. Both snapshots are integrity-checked without loading or re-evaluating current models. Stored loss failures and generated examples are bounded diagnostics, not exhaustive regression counts or semantic quality review. Historical declarations and narrow overlap checks do not certify global/semantic independence or general capability. No current-model validation, artifact writes or training/release approval.',
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_corpus_benchmark_comparisons.py','decoder_corpus_benchmark_results.py','decoder_corpus_benchmark_evaluation.py')})}
    report['revision']=digest(report)
    return report
