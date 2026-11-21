"""A fresh read-only CPU benchmark worker with process-lifetime peak RSS."""
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import uuid
if __package__:
    from .run_manifest import digest, file_digest
else:
    from run_manifest import digest, file_digest

PROTOCOL={'format':'almg-corpus-inference-profile-protocol-v1','schema_version':1,
          'execution':'one_fresh_read_only_cpu_benchmark_process',
          'measurement':'resource.getrusage(RUSAGE_SELF).ru_maxrss',
          'scope':'worker_lifetime_through_completed_benchmark_report_before_json_transport',
          'rss_units':'Darwin_bytes_Linux_KiB_normalized_to_bytes',
          'includes':'interpreter_imports_source_validation_model_loading_warmup_and_measured_inference',
          'incremental_model_or_allocator_peak':False}


def _rss_bytes(value, system):
    if type(value) is not int or value<=0:raise ValueError('Process peak RSS must be a positive integer.')
    if system=='Darwin':return value
    if system=='Linux':return value*1024
    raise ValueError('Process RSS profiling supports macOS and Linux only.')


def _worker(request):
    if __package__:
        from . import decoder_corpus_inference_benchmark as benchmark
    else:
        import decoder_corpus_inference_benchmark as benchmark
    import resource
    system=platform.system()
    baseline=_rss_bytes(int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),system)
    report=benchmark.benchmark(Path(request['root']),request['identifier'])
    peak=_rss_bytes(int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),system)
    if peak<baseline:raise ValueError('Process peak RSS decreased during inference profiling.')
    result={'format':'almg-corpus-inference-profile-v1','schema_version':1,
            'protocol':dict(PROTOCOL),'protocol_revision':digest(PROTOCOL),'source':report['source'],
            'worker_process_id':os.getpid(),'benchmark':report,
            'memory':{'measured':True,'baseline_after_imports_peak_rss_bytes':baseline,
                      'process_peak_rss_bytes':peak,'incremental_model_peak_memory_bytes':None,
                      'allocator_peak_memory_bytes':None,'system':system},
            'training_approved':False,'release_approved':False,'language_quality_validated':False,
            'limitations':'Process-lifetime RSS high-water mark for a fresh CPU worker through completion of the benchmark report. Includes interpreter/imports, source validation, model loading, warmup and measured inference; platform startup accounting can contribute. It is not incremental model memory, an isolated inference-only allocator peak, Metal/GPU memory, parent app/UI memory or an admission limit. Do not add RSS to tensor/Metal bytes because allocations may overlap. Benchmark token timings retain their narrower warm loaded-model scope. No training/release/quality approval and no artifact writes.',
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_corpus_inference_profile.py','decoder_corpus_inference_benchmark.py','decoder_corpus_evaluation.py','planned_decoder.py')})}
    result['revision']=digest(result)
    return {'nonce':request['nonce'],'process_id':os.getpid(),'report':result}


def _validated_response(response, nonce, process_id, identifier):
    try:
        report=response['report'];benchmark=report['benchmark'];memory=report['memory']
        valid=(response['nonce']==nonce and response['process_id']==process_id and process_id!=os.getpid()
               and report['format']=='almg-corpus-inference-profile-v1' and report['schema_version']==1
               and report['worker_process_id']==process_id and report['protocol']==PROTOCOL
               and report['protocol_revision']==digest(PROTOCOL)
               and report['revision']==digest({k:v for k,v in report.items() if k!='revision'})
               and benchmark['format']=='almg-corpus-inference-benchmark-v1'
               and benchmark['revision']==digest({k:v for k,v in benchmark.items() if k!='revision'})
               and benchmark['source']==report['source'] and report['source']['record_id']==identifier
               and benchmark['runtime']['device']=='CPU' and memory['measured'] is True and memory['system']==platform.system()
               and type(memory['process_peak_rss_bytes']) is int and type(memory['baseline_after_imports_peak_rss_bytes']) is int
               and memory['process_peak_rss_bytes']>=memory['baseline_after_imports_peak_rss_bytes']>0
               and memory['incremental_model_peak_memory_bytes'] is None and memory['allocator_peak_memory_bytes'] is None
               and all(report[field] is False for field in ('training_approved','release_approved','language_quality_validated')))
    except (KeyError,TypeError,ValueError):valid=False
    if not valid:raise ValueError('Inference profile worker result binding failed.')
    return report


def profile(root, identifier):
    if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):
        raise ValueError('Select a saved completed corpus model ID.')
    if platform.system() not in ('Darwin','Linux'):raise ValueError('Process RSS profiling supports macOS and Linux only.')
    nonce=uuid.uuid4().hex
    payload=json.dumps({'root':str(Path(root).resolve()),'identifier':identifier,'nonce':nonce})
    process=subprocess.Popen([sys.executable,'-B','-m','backend.decoder_corpus_inference_profile','--worker'],
                             cwd=str(Path(__file__).resolve().parent.parent),stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:stdout,stderr=process.communicate(payload,timeout=60)
    except subprocess.TimeoutExpired:
        process.kill();process.communicate()
        raise ValueError('Inference profile worker timed out; source artifacts were retained.')
    if len(stdout)>262144:raise ValueError('Inference profile worker response exceeds its bounded size.')
    try:response=json.loads(stdout)
    except (ValueError,TypeError):raise ValueError('Inference profile worker returned an invalid response.') from None
    if not isinstance(response,dict):raise ValueError('Inference profile worker returned an invalid response.')
    if process.returncode:raise ValueError('Inference profile worker failed: '+str(response.get('error','No valid benchmark report.'))[:600])
    return _validated_response(response,nonce,process.pid,identifier)


if __name__=='__main__':
    try:
        if sys.argv[1:]!=['--worker']:raise ValueError('Use the bounded inference-profile worker entry point.')
        print(json.dumps(_worker(json.load(sys.stdin)),allow_nan=False))
    except Exception as error:
        print(json.dumps({'error':str(error)}));sys.exit(1)
