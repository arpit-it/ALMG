"""Measured, bounded warm CPU inference for verified completed corpus models."""
import math
from pathlib import Path
import platform
import statistics
import time
import numpy as np
if __package__:
    from . import decoder_corpus_evaluation as heldout, decoder_corpus_optimizer as training
    from .run_manifest import digest, file_digest
else:
    import decoder_corpus_evaluation as heldout, decoder_corpus_optimizer as training
    from run_manifest import digest, file_digest

PROTOCOL={'format':'almg-corpus-inference-benchmark-protocol-v1','schema_version':1,
          'prompt':'first_validation_window_first_up_to_four_active_input_tokens',
          'generated_tokens_per_sample':8,'warmup_samples':1,'measured_samples':3,
          'batch_size':1,'decoding':'greedy_first_argmax','context':'model_context_suffix_without_kv_cache',
          'device':'CPU','clock':'perf_counter_ns',
          'timing_scope':'loaded_model_numpy_forward_greedy_selection_and_context_extension',
          'excluded':'source_validation_model_loading_tokenization_text_decoding_serialization_network'}


def _sample(model, prompt, clock):
    state=list(prompt);generated=[];start=clock();first=None
    for _ in range(PROTOCOL['generated_tokens_per_sample']):
        context=state[-model.config['context_length']:]
        scores=np.asarray(model.logits(np.asarray([context],dtype=np.int32)))
        if scores.shape!=(1,len(context),model.config['vocab_size']) or not np.isfinite(scores).all():
            raise ValueError('Invalid benchmark generation logits.')
        token=int(scores[0,-1].argmax());generated.append(token);state.append(token)
        if first is None:first=clock()
    end=clock()
    if not start<first<end:raise ValueError('Inference timing requires positive monotonic observations.')
    elapsed=end-start;first_ns=first-start
    return {'generated_token_ids':generated,'generated_tokens':len(generated),'elapsed_ns':elapsed,
            'first_token_ns':first_ns,'tokens_per_second':len(generated)*1e9/elapsed,
            'subsequent_tokens_per_second':(len(generated)-1)*1e9/(elapsed-first_ns)}


def benchmark(root, identifier):
    model,windows,_,source,corpus=heldout.evaluation_context(root,identifier)
    row=windows['validation'][0];active=sum(row['target_mask']);prompt=row['inputs'][:min(4,active)]
    if not prompt:raise ValueError('Benchmark requires a real held-out prompt.')
    warmup=_sample(model,prompt,time.perf_counter_ns)
    samples=[_sample(model,prompt,time.perf_counter_ns) for _ in range(PROTOCOL['measured_samples'])]
    if any(sample['generated_token_ids']!=warmup['generated_token_ids'] for sample in samples):
        raise ValueError('Benchmark greedy outputs changed between identical samples.')
    total_tokens=sum(sample['generated_tokens'] for sample in samples);total_ns=sum(sample['elapsed_ns'] for sample in samples)
    metrics={'generated_tokens':total_tokens,'elapsed_ns':total_ns,'tokens_per_second':total_tokens*1e9/total_ns,
             'first_token_ns_min':min(sample['first_token_ns'] for sample in samples),
             'first_token_ns_median':statistics.median(sample['first_token_ns'] for sample in samples),
             'first_token_ns_max':max(sample['first_token_ns'] for sample in samples)}
    if not all(math.isfinite(value) and value>0 for value in metrics.values()):raise ValueError('Invalid benchmark observations.')
    result={'format':'almg-corpus-inference-benchmark-v1','schema_version':1,
            'protocol':dict(PROTOCOL),'protocol_revision':digest(PROTOCOL),'source':source,
            'corpus_id':corpus['id'],'corpus_revision':corpus['revision'],'evaluation_data_binding':heldout.data_binding(corpus),
            'prompt_token_ids':prompt,'warmup':warmup,'samples':samples,'metrics':metrics,
            'model_size':{'parameter_count':sum(array.size for array in model.parameters.values()),
                          'parameter_tensor_bytes':sum(array.nbytes for array in model.parameters.values()),
                          'saved_model_artifact_bytes':(training._folder(root,identifier)/'trained-model.json').stat().st_size,
                          'peak_memory_bytes':None},
            'runtime':{'device':'CPU','numpy':np.__version__,'python':platform.python_version(),
                       'system':platform.system(),'machine':platform.machine(),
                       'clock_resolution_seconds':time.get_clock_info('perf_counter').resolution},
            'training_approved':False,'release_approved':False,'language_quality_validated':False,
            'limitations':'Observed warm CPU batch-one greedy inference only, after one complete warmup and with a growing context cropped to the model limit. Three measured samples are observations, not a confidence interval or future-speed guarantee. First-token timing excludes model loading, source validation, tokenization and network/UI streaming. No KV cache, Metal/GPU timing, cold-start measurement, energy measurement or allocator/process peak-memory measurement. Parameter tensor bytes exclude array/container overhead and temporary workspace; artifact bytes are serialized model storage only. No quality, training or release approval and no artifact writes.',
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_corpus_inference_benchmark.py','decoder_corpus_evaluation.py','planned_decoder.py','decoder_corpus_optimizer.py','decoder_corpus_inputs.py')})}
    result['revision']=digest(result)
    return result
