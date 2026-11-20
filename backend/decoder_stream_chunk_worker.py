"""Execute one approved streamed chunk in a dedicated local Metal process."""
import json
import os
from pathlib import Path
import resource
import sys
import time


def main():
    import decoder_stream_training as training
    import decoder_stream_training_feasibility as feasibility
    import mlx.core as mx
    request=json.load(sys.stdin);root=Path(request['root']);started=time.perf_counter()
    before=training.read(root,request['run_id'])
    if before['revision']!=request['expected_revision'] or before['status']=='complete':raise ValueError('Streamed checkpoint changed before worker execution; reopen the trial.')
    admission=feasibility.review(root,before['windows_id'],True,before['review'])
    if not admission['feasible']:raise ValueError('Worker resources do not cover the streamed trial reserves.')
    state=training.step(root,before['id'],True,before['revision']);mx.synchronize()
    if state['completed_steps']-before['completed_steps']!=5:raise ValueError('Worker did not execute exactly five updates; reopen saved trial state.')
    print(json.dumps({'state':state,'admission':admission,'measurements':{
        'process_id':os.getpid(),'isolated_process':True,'elapsed_seconds':time.perf_counter()-started,
        'metal_peak_bytes':int(mx.get_peak_memory()),
        'process_peak_rss_bytes':int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform=='darwin' else 1024),
        'updates':5,'includes_final_heldout_evaluation':state['status']=='complete',
        'limitations':'Fresh-process Metal allocator peak excludes cached buffers. Process RSS includes imports, CPU source validation, model loading and checkpoint saving; CPU/GPU memory may overlap and is not summed as a measured total. '
          'Elapsed work includes source validation, five updates and checkpoint IO; the final chunk also evaluates held-out splits. Interpreter/import startup and user pauses are excluded.'}},allow_nan=False))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'error':str(error)}));sys.exit(1)
