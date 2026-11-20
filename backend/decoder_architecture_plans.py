"""Validated decoder layout/memory plans; no model allocation or execution."""
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import uuid
if __package__:
    from .run_manifest import digest,file_digest
else:
    from run_manifest import digest,file_digest
FORMAT='almg-decoder-architecture-plan-v1'
DEFAULT={'layers':1,'hidden_size':8,'attention_heads':1,'head_dim':8,'feed_forward_size':16,
         'context_length':16,'vocab_size':64,'seed':7,'batch_size':4,
         'position_embedding':'learned_absolute','normalization':'layer_norm_no_affine','activation':'relu','initialization':'normal_0.02'}
LIMITS={'layers':(1,8),'hidden_size':(8,128),'attention_heads':(1,8),'head_dim':(2,64),'feed_forward_size':(8,512),
        'context_length':(2,256),'vocab_size':(4,512),'seed':(0,2**32-1),'batch_size':(1,16)}


def _validated(config):
    if not isinstance(config,dict) or set(config)!=set(DEFAULT):raise ValueError('Provide every versioned architecture field; unknown fields are rejected.')
    for key,(low,high) in LIMITS.items():
        if type(config[key]) is not int or not low<=config[key]<=high:raise ValueError(f'{key} must be an integer between {low} and {high}.')
    if config['hidden_size']!=config['attention_heads']*config['head_dim']:raise ValueError('hidden_size must equal attention_heads × head_dim.')
    if config['feed_forward_size']<config['hidden_size']:raise ValueError('feed_forward_size must be at least hidden_size.')
    for key in ('position_embedding','normalization','activation','initialization'):
        if config[key]!=DEFAULT[key]:raise ValueError(f'Unsupported {key}; this plan version supports {DEFAULT[key]}.')
    return dict(config)


def review(config):
    c=_validated(config);v,t,d,f=c['vocab_size'],c['context_length'],c['hidden_size'],c['feed_forward_size']
    shapes={'token_embedding':[v,d],'position_embedding':[t,d],'head':[d,v]}
    for layer in range(c['layers']):
        shapes.update({f'layers.{layer}.{name}':shape for name,shape in {
            'query':[d,d],'key':[d,d],'value':[d,d],'attention_output':[d,d],'feed_forward_in':[d,f],'feed_forward_out':[f,d]}.items()})
    count=sum(math.prod(shape) for shape in shapes.values());weight_bytes=count*4
    # Explicit layout estimate: retained hidden/FF intermediates plus attention scores/probabilities.
    activation_bytes=4*c['batch_size']*c['layers']*(8*t*d+2*t*f+2*c['attention_heads']*t*t)
    value={'format':FORMAT,'schema_version':1,'config':c,'parameter_shapes':shapes,'calculated_parameter_count':count,
           'estimates':{'precision':'float32','weight_bytes':weight_bytes,'gradient_bytes':weight_bytes,'adam_moment_bytes':weight_bytes*2,
                        'activation_layout_bytes':activation_bytes,'training_layout_bytes':weight_bytes*4+activation_bytes,
                        'measured':False,'assumptions':'Bias-free dense matrices, untied head/embeddings, parameter-free layer norm. FP32 weights/gradients and two Adam moments. Retained activation layout estimate excludes kernel workspace, allocator overhead and runtime/framework memory; not a feasibility guarantee.'},
           'scope':'architecture_layout_plan_only','weights_allocated':False,'execution_available':False,'training_approved':False,'release_approved':False,
           'implementation_sha256':file_digest(Path(__file__))}
    value['revision']=digest(value)
    return value


def save(root,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm saving this architecture plan; no model or training is created.')
    if not isinstance(reviewed,dict) or review(reviewed.get('config'))!=reviewed:raise ValueError('Architecture review changed; review the exact configuration again.')
    record={'format':'almg-saved-decoder-architecture-plan-v1','schema_version':1,'id':uuid.uuid4().hex,
            'created_at':datetime.now(timezone.utc).isoformat(),'review':reviewed}
    record['revision']=digest(record);parent=Path(root)/'decoder-architecture-plans';parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='.plan-',dir=parent) as temporary:
        staged=Path(temporary)/record['id'];staged.mkdir()
        (staged/'plan.json').write_text(json.dumps(record,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8');staged.rename(parent/record['id'])
    return record


def read(root,identifier):
    if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('Invalid architecture plan ID.')
    path=Path(root)/'decoder-architecture-plans'/identifier/'plan.json'
    if path.stat().st_size>128000:raise ValueError('Architecture plan exceeds its record limit.')
    record=json.loads(path.read_text(encoding='utf-8'));value=record['review']
    if (record.get('format')!='almg-saved-decoder-architecture-plan-v1' or type(record.get('schema_version')) is not int or record['schema_version']!=1
            or record.get('id')!=identifier or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})
            or value.get('revision')!=digest({k:v for k,v in value.items() if k!='revision'})):raise ValueError('Architecture plan integrity changed.')
    expected=review(value['config'])
    if any(value.get(key)!=part for key,part in expected.items() if key not in ('revision','implementation_sha256')):raise ValueError('Architecture layout or estimate changed.')
    return record


def list_plans(root,confirmed):
    if confirmed is not True:raise ValueError('Confirm review of saved architecture plans.')
    parent=Path(root)/'decoder-architecture-plans';records=[]
    for directory in parent.iterdir() if parent.exists() else []:
        if not re.fullmatch('[a-f0-9]{32}',directory.name):continue
        try:records.append(read(root,directory.name))
        except (OSError,ValueError,KeyError,TypeError,AttributeError):continue
    return sorted(records,key=lambda record:record['created_at'],reverse=True)[:20]
