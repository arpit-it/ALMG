"""Synchronized optimizer observations; shared memory counters are never reset."""
import os
import platform
from time import perf_counter


def process_peak_rss():
    import resource
    value=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if platform.system()=='Darwin' else value*1024


class OptimizerMeasurements:
    def __init__(self,mx,clock=perf_counter,rss=process_peak_rss):
        self.mx=mx;self.clock=clock;self.rss=rss;self.samples=[]
        mx.synchronize();self.started=clock()
        self.baseline=int(mx.get_active_memory());self.previous_peak=int(mx.get_peak_memory());self.baseline_rss=rss()

    def sample(self,phase):
        self.mx.synchronize()
        self.samples.append({'phase':phase,'elapsed_seconds':self.clock()-self.started,
            'active_metal_bytes':int(self.mx.get_active_memory()),'process_peak_rss_bytes':self.rss()})

    def finish(self):
        self.sample('finished')
        observed=max([self.baseline]+[sample['active_metal_bytes'] for sample in self.samples])
        return {'format':'almg-optimizer-workflow-measurements-v1','schema_version':1,'measured':True,
            'scope':'bounded_optimizer_fixture_in_shared_backend','process_id':os.getpid(),
            'elapsed_seconds':self.samples[-1]['elapsed_seconds'],'baseline_active_metal_bytes':self.baseline,
            'sampled_active_metal_max_bytes':observed,'sampled_incremental_metal_bytes':max(0,observed-self.baseline),
            'shared_metal_peak_before_bytes':self.previous_peak,'shared_metal_peak_after_bytes':int(self.mx.get_peak_memory()),
            'baseline_process_peak_rss_bytes':self.baseline_rss,
            'process_peak_rss_bytes':max([self.baseline_rss]+[sample['process_peak_rss_bytes'] for sample in self.samples]),
            'phase_samples':self.samples,'isolated_trial_peak_measured':False,'full_training_duration_seconds':None,
            'limitations':'Shared backend process: RSS is the process-lifetime high-water mark, not isolated trial memory. '
              'Metal active memory is sampled after synchronization; samples can miss transient peaks and exclude cached buffers. '
              'Shared Metal peak counters can include earlier/concurrent work and are never reset. '
              'Elapsed time includes source loading, initial checks, both uninterrupted and checkpointed training trajectories, '
              'checkpoint I/O, final evaluation and CPU generation. Excludes admission, queue/approval waits and report publication; '
              'synchronization/sampling adds overhead. Not per-step throughput, isolated peak, total wall-time or future-duration prediction.'}
