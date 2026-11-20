"""One optimizer run per process; publish measured process peaks atomically."""
from time import perf_counter
STARTED=perf_counter()
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from . import decoder_optimizer_fixture as fixture
from .decoder_optimizer_measurements import process_peak_rss


def main():
    request=json.load(sys.stdin);root=Path(request['root'])
    continuing=request.get('action','fixture')=='continuation'
    if continuing:
        from . import decoder_optimizer_continuations as continuations
        record=continuations.run(root,request['identifier'],True,request['approved']);folder=continuations._folder(root,record['id'])
    else:
        record=fixture.run(root,request['plan_id'],True,request['initialized'],request['settings'],request['approved']);folder=fixture._folder(root,record['id'])
    import mlx.core as mx
    mx.synchronize()
    record['isolated_workflow_measurements']={'format':'almg-isolated-optimizer-continuation-measurements-v1' if continuing else 'almg-isolated-optimizer-measurements-v1','schema_version':1,
        'scope':'fresh_process_optimizer_checkpoint_continuation' if continuing else 'fresh_process_bounded_optimizer_fixture','measured':True,'isolated_trial_peak_measured':True,'process_id':os.getpid(),
        'elapsed_seconds':perf_counter()-STARTED,'isolated_process_peak_rss_bytes':process_peak_rss(),'isolated_metal_peak_bytes':int(mx.get_peak_memory()),
        'limitations':'Fresh worker process includes imports, admission, model loading, the approved remaining checkpoint updates (or both fixture trajectories), checkpoint work and CPU inference. Memory peaks include worker/runtime overhead. Excludes process launch, queue/approval waits and final measurement publication; not total wall time or a general large-model forecast. Shared host/device load may vary; no shared counters are reset.'}
    record['revision']=fixture.digest({key:value for key,value in record.items() if key!='revision'})
    with NamedTemporaryFile(mode='w',encoding='utf-8',dir=folder,prefix='.measured-',suffix='.tmp',delete=False) as output:
        json.dump(record,output,allow_nan=False,indent=2);temporary=Path(output.name)
    temporary.replace(folder/'record.json')
    print(json.dumps({'record_id':record['id'],'nonce':request['nonce'],'process_id':os.getpid()}))


if __name__=='__main__':main()
