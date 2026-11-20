"""One discarded CPU image comparison; never publishes model files."""
import json
from pathlib import Path
import os
import platform
import resource
import sys
import time


def main():
    import image_recipe
    import recipe_contracts
    from run_manifest import digest
    request=json.load(sys.stdin);started=time.perf_counter()
    rows=json.loads(Path(request['dataset_path']).read_text(encoding='utf-8'))
    if digest(rows)!=request['dataset_sha256']:raise ValueError('Prepared dataset changed before CPU trial.')
    model,_,metrics=recipe_contracts.execute('text_to_image',request['mode'],rows,request['settings'],
        trainers={'local shapes':image_recipe.train,'Commons captions':image_recipe.train_web},report=lambda message:None)
    del model
    print(json.dumps({'dataset_sha256':request['dataset_sha256'],'fit_and_validation_seconds':time.perf_counter()-started,
        'process_peak_rss_bytes':int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform=='darwin' else 1024),
        'process_id':os.getpid(),'training_device':'CPU','isolated_process':True,'weights_retained':False,
        'runtime':{'python':platform.python_version(),'system':platform.system(),'machine':platform.machine(),'numpy':image_recipe.np.__version__,'pillow':image_recipe.Image.__version__},
        'comparison_algorithm':metrics['algorithm'],'quality_target_met':metrics['passed'],
        'scope':'prepared_file_load_validation_and_discarded_image_fit_no_repair_no_idle_wait_no_model_persistence'},allow_nan=False))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'error':str(error)}));sys.exit(1)
