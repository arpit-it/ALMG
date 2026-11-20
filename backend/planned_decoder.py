"""Versioned seeded multilayer/multihead CPU decoder; separate from legacy recipes."""
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
import numpy as np
if __package__:
    from . import decoder_architecture_plans as plans
else:
    import decoder_architecture_plans as plans


class PlannedDecoder:
    def __init__(self,config,initialize=True):
        self.config=plans._validated(config);self.shapes=plans.review(self.config)['parameter_shapes']
        if initialize:
            rng=np.random.default_rng(self.config['seed'])
            self.parameters={name:rng.normal(0,.02,shape).astype(np.float32) for name,shape in self.shapes.items()}
        else:self.parameters={}

    def logits(self,tokens):
        x=np.asarray(tokens);c=self.config
        if (x.ndim!=2 or x.dtype.kind not in 'iu' or not 1<=x.shape[0]<=c['batch_size'] or not 1<=x.shape[1]<=c['context_length']
                or np.any(x<0) or np.any(x>=c['vocab_size'])):raise ValueError('Use a bounded batch of valid IDs within the approved architecture context.')
        p=self.parameters;batch,length=x.shape;heads,dim=c['attention_heads'],c['head_dim']
        def norm(values):return (values-values.mean(axis=-1,keepdims=True))/np.sqrt(values.var(axis=-1,keepdims=True)+1e-5)
        hidden=p['token_embedding'][x]+p['position_embedding'][:length]
        for layer in range(c['layers']):
            prefix=f'layers.{layer}.';normalized=norm(hidden)
            q,k,v=[(normalized@p[prefix+name]).reshape(batch,length,heads,dim).transpose(0,2,1,3) for name in ('query','key','value')]
            scores=(q@k.swapaxes(-1,-2))/np.sqrt(dim)
            scores=np.where(np.triu(np.ones((length,length),dtype=bool),1),-np.inf,scores)
            probabilities=np.exp(scores-scores.max(axis=-1,keepdims=True));probabilities/=probabilities.sum(axis=-1,keepdims=True)
            attended=(probabilities@v).transpose(0,2,1,3).reshape(batch,length,c['hidden_size'])
            hidden=hidden+attended@p[prefix+'attention_output']
            hidden=hidden+np.maximum(norm(hidden)@p[prefix+'feed_forward_in'],0)@p[prefix+'feed_forward_out']
        output=norm(hidden)@p['head']
        if not np.isfinite(output).all():raise ValueError('Planned decoder produced nonfinite forward scores.')
        return output

    def artifact(self):
        if set(self.parameters)!=set(self.shapes):raise ValueError('Planned decoder parameter names changed.')
        values={}
        for name,shape in self.shapes.items():
            array=np.asarray(self.parameters[name])
            if array.shape!=tuple(shape) or array.dtype!=np.float32 or not np.isfinite(array).all():raise ValueError('Planned decoder tensor shape/dtype/finite checks failed.')
            values[name]=array.tolist()
        return {'format':'almg-planned-decoder-v1','schema_version':1,'config':self.config,'parameters':values}

    def save(self,path):
        path=Path(path);text=json.dumps(self.artifact(),allow_nan=False,separators=(',',':'))
        if len(text.encode())>64*1024*1024:raise ValueError('Planned decoder exceeds its 64 MiB artifact limit.')
        temporary=None
        try:
            with NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.model-',suffix='.tmp',delete=False) as stream:
                temporary=Path(stream.name);stream.write(text)
            temporary.replace(path)
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)

    @classmethod
    def load(cls,path):
        with Path(path).open('rb') as stream:raw=stream.read(64*1024*1024+1)
        if len(raw)>64*1024*1024:raise ValueError('Planned decoder exceeds its artifact limit.')
        value=json.loads(raw)
        if (not isinstance(value,dict) or set(value)!={'format','schema_version','config','parameters'} or value.get('format')!='almg-planned-decoder-v1'
                or type(value.get('schema_version')) is not int or value['schema_version']!=1):raise ValueError('Unsupported planned decoder artifact.')
        model=cls(value['config'],initialize=False)
        if not isinstance(value['parameters'],dict) or set(value['parameters'])!=set(model.shapes):raise ValueError('Planned decoder parameter names changed.')
        for name,shape in model.shapes.items():
            array=np.asarray(value['parameters'][name])
            if array.dtype.kind not in 'fi' or array.shape!=tuple(shape) or not np.isfinite(array).all() or np.any(np.abs(array)>np.finfo(np.float32).max):raise ValueError('Invalid planned decoder tensor.')
            model.parameters[name]=array.astype(np.float32)
        return model
