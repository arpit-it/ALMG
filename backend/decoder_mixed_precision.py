"""Bounded FP16 matrix products with FP32 master gradients and stable reductions."""
import math
import numpy as np


def unscale(gradients,scale):
    if type(scale) not in (int,float) or not math.isfinite(scale) or scale<=0:raise ValueError('Use a finite positive loss scale.')
    result={}
    for name,value in gradients.items():
        array=np.asarray(value)
        if array.dtype!=np.float32 or not np.isfinite(array).all():raise ValueError('Master gradients must be finite FP32 values before unscaling.')
        result[name]=(array/scale).astype(np.float32)
        if not np.isfinite(result[name]).all():raise ValueError('Unscaled gradients must remain finite.')
    return result


def functions(config,mx,loss_scale):
    def norm(values):
        x=values.astype(mx.float32)
        return ((x-mx.mean(x,axis=-1,keepdims=True))/mx.sqrt(mx.var(x,axis=-1,keepdims=True)+1e-5)).astype(mx.float16)
    def logits(master,tokens):
        p={name:value.astype(mx.float16) for name,value in master.items()};rows,length=tokens.shape;heads,dim=config['attention_heads'],config['head_dim']
        hidden=p['token_embedding'][tokens]+p['position_embedding'][:length]
        for layer in range(config['layers']):
            prefix=f'layers.{layer}.';x=norm(hidden)
            q,k,v=[(x@p[prefix+name]).reshape(rows,length,heads,dim).transpose(0,2,1,3) for name in ('query','key','value')]
            scores=(q@mx.swapaxes(k,-1,-2)).astype(mx.float32)/(dim**.5)
            causal=mx.triu(mx.full((length,length),-float('inf')),k=1)
            probabilities=mx.softmax(scores+causal,axis=-1).astype(mx.float16)
            attended=(probabilities@v).transpose(0,2,1,3).reshape(rows,length,config['hidden_size'])
            hidden=hidden+attended@p[prefix+'attention_output']
            hidden=hidden+mx.maximum(norm(hidden)@p[prefix+'feed_forward_in'],0)@p[prefix+'feed_forward_out']
        return (norm(hidden)@p['head']).astype(mx.float32)
    def loss(p,x,y,mask):
        scores=logits(p,x);correct=mx.take_along_axis(scores,y[...,None],axis=-1).squeeze(-1)
        return mx.sum((mx.logsumexp(scores,axis=-1)-correct)*mask)/mx.sum(mask)
    def scaled_loss(p,x,y,mask):return loss(p,x,y,mask)*loss_scale
    return logits,loss,mx.grad(scaled_loss)
