"""Explicit fresh initialization, causal CPU forward check and immutable persistence."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import uuid
import numpy as np
if __package__:
    from . import decoder_architecture_plans as plans,training_resources
    from .planned_decoder import PlannedDecoder
    from .run_manifest import digest,file_digest
else:
    import decoder_architecture_plans as plans,training_resources
    from planned_decoder import PlannedDecoder
    from run_manifest import digest,file_digest


def _folder(root,plan_id):
    plans.read(root,plan_id)
    return Path(root)/'decoder-architecture-initializations'/plan_id


def run(root,plan_id,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm fresh weights and a private CPU forward/persistence check; no training is approved.')
    current=plans.read(root,plan_id)
    if current!=reviewed:raise ValueError('Reopen the exact saved architecture plan before initialization.')
    resources=training_resources.check_size(max(current['review']['estimates']['weight_bytes']*8,65536),Path(root))
    model=PlannedDecoder(current['review']['config']);c=model.config
    rows=min(2,c['batch_size']);length=min(8,c['context_length'])
    tokens=(np.arange(rows*length).reshape(rows,length)%c['vocab_size']).tolist();scores=model.logits(tokens)
    altered=np.array(tokens);cut=max(1,length//2);altered[:,cut:]=(altered[:,cut:]+1)%c['vocab_size']
    causal_error=float(np.max(np.abs(scores[:,:cut]-model.logits(altered.tolist())[:,:cut])))
    if causal_error>1e-6:raise ValueError('Causal prefix forward check failed; no initialization published.')
    count=sum(array.size for array in model.parameters.values());weight_bytes=sum(array.nbytes for array in model.parameters.values())
    if count!=current['review']['calculated_parameter_count'] or weight_bytes!=current['review']['estimates']['weight_bytes']:raise ValueError('Allocated tensor layout differs from its reviewed plan.')
    parent=_folder(root,plan_id);parent.mkdir(parents=True,exist_ok=True);identifier=uuid.uuid4().hex
    with TemporaryDirectory(prefix='.initialization-',dir=parent) as temporary:
        staged=Path(temporary)/identifier;staged.mkdir();model.save(staged/'model.json');loaded=PlannedDecoder.load(staged/'model.json')
        if any(not np.array_equal(value,loaded.parameters[name]) for name,value in model.parameters.items()):raise ValueError('Fresh model parameters changed on reload.')
        error=float(np.max(np.abs(scores-loaded.logits(tokens))))
        if error!=0:raise ValueError('CPU forward output changed on reload.')
        record={'format':'almg-planned-decoder-initialization-v1','schema_version':1,'id':identifier,'plan_id':plan_id,'plan_revision':current['revision'],
                'config':c,'actual_parameter_count':count,'actual_weight_bytes':weight_bytes,'tensor_count':len(model.parameters),'probe_token_ids':tokens,
                'forward_shape':list(scores.shape),'causal_prefix_max_error':causal_error,'reload_cpu_max_error':error,'all_parameters_equal_after_reload':True,
                'weight_origin':'new_seeded_normal_0.02','pretrained_weights_loaded':False,'optimizer_updates':0,'backward_checked':False,'training_approved':False,'release_approved':False,
                'scope':'fresh_initialization_cpu_forward_and_persistence_only','resources':resources,'planned_estimates':current['review']['estimates'],
                'runtime':{'device':'CPU','numpy':np.__version__},'model_sha256':file_digest(staged/'model.json'),
                'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('planned_decoder.py','decoder_architecture_initializations.py','decoder_architecture_plans.py')})}
        record['revision']=digest(record)
        (staged/'record.json').write_text(json.dumps(record,allow_nan=False,indent=2),encoding='utf-8')
        if plans.read(root,plan_id)!=current:raise ValueError('Architecture plan changed during initialization.')
        staged.rename(parent/identifier)
    return record


def read(root,plan_id,identifier):
    if not isinstance(identifier,str) or len(identifier)!=32 or any(value not in '0123456789abcdef' for value in identifier):raise ValueError('Invalid initialization ID.')
    current=plans.read(root,plan_id);folder=_folder(root,plan_id)/identifier;path=folder/'record.json'
    if path.stat().st_size>128000:raise ValueError('Initialization record exceeds its size limit.')
    record=json.loads(path.read_text(encoding='utf-8'))
    if (record.get('format')!='almg-planned-decoder-initialization-v1' or type(record.get('schema_version')) is not int or record['schema_version']!=1
            or record.get('id')!=identifier or record.get('plan_id')!=plan_id or record.get('plan_revision')!=current['revision']
            or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'}) or record.get('model_sha256')!=file_digest(folder/'model.json')
            or type(record.get('optimizer_updates')) is not int or record['optimizer_updates']!=0
            or record.get('scope')!='fresh_initialization_cpu_forward_and_persistence_only' or record.get('weight_origin')!='new_seeded_normal_0.02'
            or any(record.get(key) is not False for key in ('pretrained_weights_loaded','backward_checked','training_approved','release_approved'))):raise ValueError('Initialization record integrity or scope changed.')
    training_resources.check_size(max((folder/'model.json').stat().st_size*2,65536),Path(root))
    model=PlannedDecoder.load(folder/'model.json');fresh=PlannedDecoder(current['review']['config'])
    if (model.config!=current['review']['config'] or record.get('config')!=model.config
            or any(not np.array_equal(value,model.parameters[name]) for name,value in fresh.parameters.items())
            or record.get('actual_parameter_count')!=sum(value.size for value in model.parameters.values())
            or record.get('actual_weight_bytes')!=sum(value.nbytes for value in model.parameters.values())):raise ValueError('Initialization-only parameters no longer match the seeded plan.')
    return record


def list_records(root,plan_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm review of private initialized weights and CPU checks.')
    parent=_folder(root,plan_id);records=[]
    for directory in sorted(parent.iterdir()) if parent.exists() else []:
        if len(directory.name)!=32:continue
        try:records.append(read(root,plan_id,directory.name))
        except (OSError,ValueError,KeyError,TypeError):continue
    return records[-20:]
