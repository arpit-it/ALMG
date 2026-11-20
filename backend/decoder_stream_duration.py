"""Stage-specific work estimates for the fixed manual SGD20 trial."""
import math


def estimate(records,completed_steps=0,prior=None):
    stages={};borrowed=False
    for key,value in (prior or {}).get('stage_seconds',{}).items():
        if key in ('5','10','15','20') and type(value) in (int,float) and math.isfinite(value) and value>0:
            stages[key]=value;borrowed=True
    for record in records:
        step=record['completed_steps'];observed=record['measurements'];value=observed['request_work_seconds']
        if (step in (5,10,15,20) and observed['includes_final_heldout_evaluation']==(step==20)
                and type(value) in (float,int) and math.isfinite(value) and value>0):stages[str(step)]=max(stages.get(str(step),0),value)
    remaining=[str(step) for step in (5,10,15,20) if step>completed_steps]
    return {'stage_seconds':stages,'completed_steps':completed_steps,'borrowed_admission_stages':borrowed,
            'estimated_twenty_update_request_work_seconds':sum(stages[str(step)] for step in (5,10,15,20)) if len(stages)==4 else None,
            'estimated_remaining_request_work_seconds':sum(stages[step] for step in remaining) if all(step in stages for step in remaining) else None,
            'includes_final_evaluation': '20' in stages,
            'policy':'Largest compatible measured request work at each of the 5/10/15/20-update checkpoints. Final stage includes full held-out evaluation. '
              'Includes admission, worker startup, updates and checkpoint IO; excludes initial model initialization, lock queue, measurement publication and manual pauses. '
              'A work estimate, not a wall-clock deadline or full-epoch prediction; hardware/load/history changes can invalidate it.'}
