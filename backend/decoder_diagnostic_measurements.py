"""Synchronized observations, without resetting shared Metal memory counters."""
from time import perf_counter


class DiagnosticMeasurements:
    def __init__(self,mx,clock=perf_counter):
        self.mx=mx;self.clock=clock;mx.synchronize()
        self.baseline=int(mx.get_active_memory());self.previous_peak=int(mx.get_peak_memory())
        self.started=clock();self.samples=[]

    def sample(self,phase):
        self.mx.synchronize()
        self.samples.append({'phase':phase,'active_metal_bytes':int(self.mx.get_active_memory())})

    def finish(self,estimated_gpu_bytes):
        self.sample('finished')
        elapsed=self.clock()-self.started;peak=int(self.mx.get_peak_memory())
        observed=max([self.baseline]+[sample['active_metal_bytes'] for sample in self.samples])
        incremental=max(0,observed-self.baseline)
        return {'scope':'synthetic_diagnostic_in_shared_backend_process',
                'elapsed_seconds':elapsed,'baseline_active_metal_bytes':self.baseline,
                'sampled_active_metal_max_bytes':observed,'sampled_incremental_metal_bytes':incremental,
                'process_peak_before_bytes':self.previous_peak,'process_peak_after_bytes':peak,
                'samples':self.samples,'estimated_gpu_working_bytes':estimated_gpu_bytes,
                'observed_increment_exceeds_estimate':incremental>estimated_gpu_bytes,
                'conservative_observed_gpu_budget_bytes':max(estimated_gpu_bytes,incremental),
                'full_training_duration_seconds':None,'isolated_trial_peak_measured':False,
                'limitations':'Active memory sampled after synchronization excludes cached buffers and CPU memory. '
                  'Process peak counters may include earlier or concurrent workflows; counters are never reset. '
                  'Samples can miss transient peaks. Elapsed time includes CPU numerical checks and is not optimizer throughput. '
                  'Comparison is diagnostic feedback only, not an admission guarantee or full-training prediction.'}
