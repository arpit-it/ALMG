from copy import deepcopy
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
from backend import decoder_optimizer_state as codec,decoder_optimizer_fixture as fixture,decoder_architecture_plans as plans
from backend.planned_decoder import PlannedDecoder
from backend.run_manifest import digest,file_digest


def state(parameters):
    rng=np.random.default_rng(7)
    return {'step':5,'m':{name:rng.normal(0,.01,value.shape).astype(np.float32) for name,value in parameters.items()},
            'v':{name:rng.uniform(0,.01,value.shape).astype(np.float32) for name,value in parameters.items()}}


class OptimizerStateEncodingTest(unittest.TestCase):
    def test_compact_float32_bits_roundtrip_to_owned_writable_arrays(self):
        parameters={'x':np.zeros((2,3),np.float32)};original=state(parameters);original['m']['x'][0,0]=-0.
        config={**fixture.DEFAULT,'optimizer':'adamw','weight_decay':.01}
        encoded=codec.encode(original,parameters,config,compact=True);decoded=codec.decode(encoded,parameters,config,version=2)
        self.assertEqual(decoded['step'],5)
        for kind in ('m','v'):
            np.testing.assert_array_equal(decoded[kind]['x'].view(np.uint32),original[kind]['x'].view(np.uint32))
            self.assertTrue(decoded[kind]['x'].flags.owndata);self.assertTrue(decoded[kind]['x'].flags.writeable)
        self.assertEqual(encoded['m']['x']['dtype'],'<f4')

    def test_shape_dtype_size_encoding_missing_moments_and_nonfinite_values_rejected(self):
        parameters={'x':np.zeros((2,3),np.float32)};config={**fixture.DEFAULT,'optimizer':'adamw','weight_decay':.01}
        encoded=codec.encode(state(parameters),parameters,config,compact=True)
        for key,value in (('shape',[3,2]),('dtype','<f8'),('data_base64','A'*100000),('data_base64','!'*32)):
            changed=deepcopy(encoded);changed['m']['x'][key]=value
            with self.assertRaises(ValueError):codec.decode(changed,parameters,config,version=2)
        changed=deepcopy(encoded);changed['v']={}
        with self.assertRaises(ValueError):codec.decode(changed,parameters,config,version=2)
        for bad in (np.full((2,3),np.nan,np.float32),np.full((2,3),-1,np.float32)):
            changed=deepcopy(encoded);changed['v']['x']['data_base64']=base64.b64encode(bad.astype('<f4').tobytes()).decode()
            with self.assertRaises(ValueError):codec.decode(changed,parameters,config,version=2)
        with self.assertRaises(ValueError):codec.decode(encoded,parameters,config,version=1)

    def test_small_checkpoint_stays_v1_and_larger_v2_is_smaller_than_legacy(self):
        config={**fixture.DEFAULT,'optimizer':'adamw','weight_decay':.01}
        with TemporaryDirectory() as temporary:
            root=Path(temporary);small=PlannedDecoder({**plans.DEFAULT,'vocab_size':4})
            first=fixture.checkpoint(root/'small',small,state(small.parameters),config,'review');self.assertEqual(first['schema_version'],1)
            model=PlannedDecoder({**plans.DEFAULT,'layers':3,'hidden_size':32,'attention_heads':4,'head_dim':8,'feed_forward_size':64,'vocab_size':4})
            original=state(model.parameters);record=fixture.checkpoint(root/'compact',model,original,config,'review');self.assertEqual(record['schema_version'],2)
            payload=json.loads((root/'compact/optimizer.json').read_text());self.assertEqual(payload['format'],codec.FORMAT)
            legacy=codec.encode(original,model.parameters,config,compact=False)
            self.assertLess((root/'compact/optimizer.json').stat().st_size,len(json.dumps(legacy).encode())*.4)
            restored,loaded=fixture.restore(root/'compact',config,'review')
            for kind in ('m','v'):
                for name in original[kind]:np.testing.assert_array_equal(original[kind][name].view(np.uint32),loaded[kind][name].view(np.uint32))
            gradients={name:np.full_like(value,.01) for name,value in model.parameters.items()}
            expected,_,_=fixture.update(model.parameters,gradients,original,config);actual,_,_=fixture.update(restored.parameters,gradients,loaded,config)
            self.assertTrue(all(np.array_equal(actual[name],value) for name,value in expected.items()))
            # Genuine legacy layout with a larger model remains readable without conversion.
            folder=root/'legacy';folder.mkdir();model.save(folder/'model.json');(folder/'optimizer.json').write_text(json.dumps(legacy))
            old={**record,'format':'almg-optimizer-fixture-checkpoint-v1','schema_version':1,'files':{name:file_digest(folder/name) for name in ('model.json','optimizer.json')}}
            old['revision']=digest({k:v for k,v in old.items() if k!='revision'});(folder/'checkpoint.json').write_text(json.dumps(old))
            _,loaded_old=fixture.restore(folder,config,'review')
            self.assertTrue(all(np.array_equal(loaded_old['m'][name],value) for name,value in original['m'].items()))
            (root/'compact/optimizer.json').write_text('{}')
            with self.assertRaises(ValueError):fixture.restore(root/'compact',config,'review')

    def test_invalid_writer_state_rejected_before_creating_checkpoint(self):
        model=PlannedDecoder({**plans.DEFAULT,'vocab_size':4});config={**fixture.DEFAULT,'optimizer':'adamw','weight_decay':.01}
        original=state(model.parameters);original['m'][next(iter(original['m']))]=np.zeros((1,),np.float32)
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/'invalid'
            with self.assertRaises(ValueError):fixture.checkpoint(path,model,original,config,'review')
            self.assertFalse(path.exists())
