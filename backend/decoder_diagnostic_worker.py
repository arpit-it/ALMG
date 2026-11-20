"""One approved synthetic diagnostic per fresh local process; no publication here."""
import json
from pathlib import Path
import sys
import time


def main():
    import decoder_architecture_backward as backward
    import resource
    request=json.load(sys.stdin);started=time.perf_counter()
    report=backward.run(Path(request['root']),request['plan_id'],request['confirmed'],request['reviewed'],request.get('reviewed_feasibility'),publish=False)
    observed=report['diagnostic_measurements']
    peak=observed['process_peak_after_bytes'];estimated=observed['estimated_gpu_working_bytes']
    observed.update(scope='fresh_process_synthetic_diagnostic',isolated_trial_peak_measured=True,
                    isolated_process_id=__import__('os').getpid(),isolated_metal_peak_bytes=peak,
                    isolated_process_peak_rss_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform=='darwin' else 1024),
                    isolated_workflow_elapsed_seconds=time.perf_counter()-started,
                    observed_peak_exceeds_estimate=peak>estimated,
                    conservative_observed_gpu_budget_bytes=max(estimated,peak),
                    limitations='Fresh process runs only this synthetic diagnostic. Metal allocator peak excludes cached buffers and CPU memory. '
                      'Process peak RSS includes interpreter/imports, source loading and CPU numerical checks; it is not added to Metal peak because unified memory may overlap. '
                      'Workflow timing excludes interpreter/import startup. This is not a full dataset training peak or duration prediction.')
    report['revision']=backward.digest({k:v for k,v in report.items() if k!='revision'})
    print(json.dumps(report,allow_nan=False))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'error':str(error)}));sys.exit(1)
