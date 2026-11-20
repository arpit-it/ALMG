"""Summary-only streamed dataset approach plans; no execution or training approval."""
import json
import re
from pathlib import Path
import uuid

if __package__:
    from . import decoder_stream_batches as batches,recipe_contracts
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_batches as batches
    import recipe_contracts
    from run_manifest import digest,file_digest


def _folder(root,plan_id):
    batches.windows._folder(root,plan_id)
    return Path(root)/'decoder-stream-plans'/plan_id


def _write(path,record):
    temporary=path.with_name(uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)


def propose(root,window_id,confirmed,reviewed,goal,planner,planner_identity=None):
    if confirmed is not True:raise ValueError('Confirm local streamed approach planning; this cannot start training.')
    if not isinstance(goal,str) or not 1<=len(goal.strip())<=3000:raise ValueError('Describe the planning goal in 1 to 3000 characters.')
    record=batches._validated(root,window_id,reviewed)
    catalog=recipe_contracts.planning_catalog('decoder_trial');available={item['id']:item for item in catalog}
    summary={key:record[key] for key in ('id','revision','index_id','index_revision','tokenizer_id','tokenizer_revision',
                                       'overlap_id','overlap_revision','total_records','window_counts','target_tokens')}
    implementation=file_digest(Path(__file__))
    system=('Recommend one approach: from_scratch, fine_tuning, distillation, or retrieval. '
        'Return recipe (a registered ID), approach and a short reason. This is a summary-only streamed dataset plan: '
        'full streamed trial execution, scheduling and checkpoint recovery are unavailable. Do not claim execution or training approval. '
        'The overlap gate is lexical and does not prove cleanliness, source permission or model quality. No source text or token arrays are provided.')
    context={'goal':goal.strip(),'dataset_summary':summary,'registered_recipes':catalog,'streamed_execution_available':False}
    request_sha256=digest({'system':system,'data':context})
    catalog_sha256=digest(catalog)
    result=planner(system,context)
    if not isinstance(result,dict) or not isinstance(result.get('recipe'),str) or result['recipe'] not in available:raise ValueError('The planner selected an unavailable registered recipe.')
    if result.get('approach') not in ('from_scratch','fine_tuning','distillation','retrieval'):raise ValueError('The planner returned an unsupported approach.')
    if not isinstance(result.get('reason'),str) or not 1<=len(result['reason'].strip())<=600:raise ValueError('The planner must provide a short explanation.')
    if (batches._validated(root,window_id,reviewed)!=record or recipe_contracts.planning_catalog('decoder_trial')!=catalog
            or file_digest(Path(__file__))!=implementation
            or digest({'system':system,'data':context})!=request_sha256):raise ValueError('Streamed planning evidence changed. Request a fresh plan.')
    identity=planner_identity() if planner_identity else {'provider':'unspecified'}
    if not isinstance(identity,dict):raise ValueError('The planner identity is unavailable; no plan published.')
    if identity.get('provider')=='local_qwen' and (
            identity.get('loaded') is not True or not isinstance(identity.get('model'),str) or not identity['model'].strip()
            or not isinstance(identity.get('verified_weights_revision'),str)
            or re.fullmatch('[a-f0-9]{64}',identity['verified_weights_revision']) is None):
        raise ValueError('Local Qwen must report its loaded, verified weights revision; no plan published.')
    plan={'format':'almg-stream-approach-plan-v1','schema_version':1,'id':uuid.uuid4().hex,
          'windows_id':window_id,'windows_revision':record['revision'],'goal':goal.strip(),
          'recipe':result['recipe'],'recipe_contract':available[result['recipe']],
          'approach':result['approach'],'reason':result['reason'].strip(),'dataset_summary':summary,
          'planner':identity,'planner_request':{'version':1,'summary_only':True,'sha256':request_sha256,
              'recipe_catalog_sha256':catalog_sha256,'validated_result_sha256':digest(result)},
          'implementation_sha256':implementation,'executable':False,'training_approved':False,'release_approved':False,
          'limitations':'Approach planning only. Full streamed training, scheduling and checkpoint recovery are unavailable. Acknowledgment is not execution consent.'}
    plan['revision']=digest(plan);folder=_folder(root,plan['id']);folder.mkdir(parents=True)
    _write(folder/'plan.json',plan);return plan


def read(root,plan_id):
    path=_folder(root,plan_id)/'plan.json'
    try:
        if path.stat().st_size>256000:raise ValueError('Saved streamed plan exceeds its bound.')
        plan=json.loads(path.read_text(encoding='utf-8'))
        if (plan.get('format')!='almg-stream-approach-plan-v1' or type(plan.get('schema_version')) is not int
                or plan['schema_version']!=1 or plan.get('id')!=plan_id
                or plan.get('revision')!=digest({k:v for k,v in plan.items() if k!='revision'})
                or any(plan.get(key) is not False for key in ('executable','training_approved','release_approved'))):
            raise ValueError('Saved streamed plan integrity check failed.')
        return plan
    except (OSError,TypeError,KeyError,AttributeError) as error:raise ValueError('Saved streamed plan is unavailable.') from error


def acknowledge(root,plan_id,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm acknowledgment of this approach plan; training remains unavailable.')
    plan=read(root,plan_id)
    if not isinstance(reviewed,dict) or reviewed!=plan:raise ValueError('The streamed plan changed. Reopen the saved plan.')
    record=batches.windows.read(root,plan['windows_id'])
    batches._validated(root,plan['windows_id'],record)
    if record['revision']!=plan['windows_revision']:raise ValueError('The source-window revision changed. Request a fresh plan.')
    receipt={'format':'almg-stream-plan-acknowledgment-v1','schema_version':1,'plan_id':plan_id,
             'plan_revision':plan['revision'],'windows_revision':plan['windows_revision'],
             'approach':plan['approach'],'acknowledged':True,'executable':False,'training_approved':False,'release_approved':False}
    receipt['revision']=digest(receipt);_write(_folder(root,plan_id)/'acknowledgment.json',receipt);return receipt


def list_plans(root,window_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm local streamed plan review.')
    batches.windows._folder(root,window_id)
    parent=Path(root)/'decoder-stream-plans';plans=[]
    for folder in sorted(parent.iterdir()) if parent.exists() else []:
        if folder.name.startswith('.'):continue
        try:
            plan=read(root,folder.name)
            if plan['windows_id']==window_id:plans.append(plan)
        except ValueError:continue
    return plans[-20:]
