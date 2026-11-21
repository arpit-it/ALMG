"""Lossless bounded float32 optimizer-state encoding; legacy JSON remains readable."""
import base64
import binascii
import numpy as np

FORMAT='almg-float32-optimizer-state-v2'


def _validate(state, parameters, config, *, allow_completed=False):
    if config.get('optimizer') not in ('sgd','adamw'):raise ValueError('Unsupported checkpoint optimizer.')
    last_step=config['steps'] if allow_completed else config['steps']-1
    if type(state.get('step')) is not int or not 0<state['step']<=last_step:raise ValueError('Invalid restored optimizer/scheduler counter.')
    expected=set(parameters) if config['optimizer']=='adamw' else set()
    for kind in ('m','v'):
        if not isinstance(state.get(kind),dict) or set(state[kind])!=expected:raise ValueError('Optimizer moments are missing or invalid.')
        for name,value in state[kind].items():
            if (not isinstance(value,np.ndarray) or value.dtype!=np.dtype(np.float32) or value.shape!=parameters[name].shape
                or not np.isfinite(value).all() or (kind=='v' and np.any(value<0))):raise ValueError('Optimizer moment dtype, shape or finite checks failed.')


def encode(state, parameters, config, *, compact, allow_completed=False):
    _validate(state,parameters,config,allow_completed=allow_completed)
    if not compact:return {'step':state['step'],**{kind:{name:value.tolist() for name,value in state[kind].items()} for kind in ('m','v')}}
    return {'format':FORMAT,'schema_version':2,'step':state['step'],
            **{kind:{name:{'dtype':'<f4','shape':list(value.shape),
                           'data_base64':base64.b64encode(np.ascontiguousarray(value,dtype='<f4').tobytes(order='C')).decode('ascii')}
                     for name,value in state[kind].items()} for kind in ('m','v')}}


def decode(saved, parameters, config, *, version, allow_completed=False):
    if not isinstance(saved,dict):raise ValueError('Invalid saved optimizer state.')
    state={'step':saved.get('step'),'m':{},'v':{}}
    expected=set(parameters) if config['optimizer']=='adamw' else set()
    if version==2:
        if set(saved)!={'format','schema_version','step','m','v'} or saved['format']!=FORMAT or type(saved['schema_version']) is not int or saved['schema_version']!=2:
            raise ValueError('Invalid compact optimizer state format.')
        for kind in ('m','v'):
            if not isinstance(saved[kind],dict) or set(saved[kind])!=expected:raise ValueError('Compact optimizer moments are missing or invalid.')
            for name,item in saved[kind].items():
                shape=list(parameters[name].shape);size=parameters[name].size*4
                if (not isinstance(item,dict) or set(item)!={'dtype','shape','data_base64'} or item['dtype']!='<f4'
                    or item['shape']!=shape or any(type(value) is not int for value in item['shape'])
                    or not isinstance(item['data_base64'],str) or len(item['data_base64'])!=4*((size+2)//3)):
                    raise ValueError('Compact optimizer tensor metadata or encoded size changed.')
                try:raw=base64.b64decode(item['data_base64'],validate=True)
                except (ValueError,binascii.Error):raise ValueError('Invalid compact optimizer tensor encoding.') from None
                if len(raw)!=size:raise ValueError('Compact optimizer tensor byte count changed.')
                state[kind][name]=np.frombuffer(raw,dtype='<f4').reshape(shape).astype(np.float32,copy=True)
    elif version==1:
        if 'format' in saved:raise ValueError('Checkpoint/state version mismatch.')
        try:
            with np.errstate(over='raise',invalid='raise'):
                for kind in ('m','v'):
                    if not isinstance(saved.get(kind),dict) or set(saved[kind])!=expected:raise ValueError('Legacy optimizer moments are missing or invalid.')
                    state[kind]={name:np.asarray(value,dtype=np.float32) for name,value in saved[kind].items()}
        except (TypeError,ValueError,FloatingPointError):raise ValueError('Invalid legacy optimizer moment values.') from None
    else:raise ValueError('Unsupported optimizer checkpoint version.')
    _validate(state,parameters,config,allow_completed=allow_completed)
    return state
