"""Fresh corpus worker; process-lifetime peaks belong only to this workflow."""
from time import perf_counter
STARTED=perf_counter()
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from . import decoder_corpus_optimizer as training


def main():
    request=json.load(sys.stdin);root=Path(request['root'])
    action=request.get('action','full')
    if action=='full':
        record=training.run(root,True,request['initialized'],request['corpus'],request['settings'],request['approved'],'fresh_process',request.get('request_id'));folder=training._folder(root,record['id'])
    elif action in ('continuation','partial_resume'):
        from . import decoder_corpus_continuations as continuations
        runner=continuations.run if action=='continuation' else continuations.run_partial
        record=runner(root,request['identifier'],True,request['approved'],request.get('request_id'),execution_mode='fresh_process');folder=continuations._folder(root,record['id'])
    else:raise ValueError('Unsupported isolated corpus worker action.')
    import mlx.core as mx
    mx.synchronize()
    record['isolated_workflow_measurements']={'format':'almg-isolated-corpus-optimizer-measurements-v1' if action=='full' else 'almg-isolated-corpus-continuation-measurements-v1','schema_version':1,
        'action':action,'scope':'fresh_process_reviewed_corpus_optimizer' if action=='full' else 'fresh_process_corpus_checkpoint_continuation','measured':True,'isolated_trial_peak_measured':True,'process_id':os.getpid(),
        'elapsed_seconds':perf_counter()-STARTED,'isolated_process_peak_rss_bytes':training.measurements.process_peak_rss(),
        'isolated_metal_peak_bytes':int(mx.get_peak_memory()),
        'limitations':'Fresh process includes imports, admission/history validation, model/corpus loading, both verification trajectories for fresh training or only the approved remaining recovery updates, checkpoint restore, all split evaluations and CPU generation. RSS/Metal peaks include worker/runtime overhead and can overlap in unified memory. Excludes parent admission, process launch, queue/approval waits and final publication. No shared counters reset; not a large-model feasibility or total wall-time guarantee.'}
    record['revision']=training.digest({k:v for k,v in record.items() if k!='revision'})
    with NamedTemporaryFile(mode='w',encoding='utf-8',dir=folder,prefix='.isolated-',delete=False) as output:
        json.dump(record,output,allow_nan=False,indent=2);temporary=Path(output.name)
    temporary.replace(folder/'record.json')
    print(json.dumps({'record_id':record['id'],'nonce':request['nonce'],'process_id':os.getpid()}))


if __name__=='__main__':main()
