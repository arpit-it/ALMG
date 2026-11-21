import base64
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
from backend import decoder_architecture_plans as plans
from backend.planned_decoder import PlannedDecoder


def larger():
    return PlannedDecoder({**plans.DEFAULT,'layers':3,'hidden_size':32,'attention_heads':4,'head_dim':8,'feed_forward_size':64,'context_length':16,'vocab_size':4})


class CompactPlannedDecoderTest(unittest.TestCase):
    def test_compact_bits_logits_and_legacy_file_preserved(self):
        model=larger();model.parameters['head'][0,0]=-0.
        legacy={'format':'almg-planned-decoder-v1','schema_version':1,'config':model.config,'parameters':{name:value.tolist() for name,value in model.parameters.items()}}
        with TemporaryDirectory() as temporary:
            root=Path(temporary);old=root/'legacy.json';old.write_text(json.dumps(legacy));before=old.read_bytes()
            model.save(root/'compact.json');saved=json.loads((root/'compact.json').read_text())
            self.assertEqual(saved['schema_version'],2)
            self.assertLess((root/'compact.json').stat().st_size,len(before)*.4)
            for path in (old,root/'compact.json'):
                restored=PlannedDecoder.load(path)
                for name,value in model.parameters.items():
                    np.testing.assert_array_equal(restored.parameters[name].view(np.uint32),value.view(np.uint32))
                    self.assertTrue(restored.parameters[name].flags.owndata)
                    self.assertTrue(restored.parameters[name].flags.writeable)
                np.testing.assert_array_equal(restored.logits([[0,1,2,3]]),model.logits([[0,1,2,3]]))
            self.assertEqual(old.read_bytes(),before)
            small=PlannedDecoder({**plans.DEFAULT,'vocab_size':4});self.assertEqual(small.artifact()['schema_version'],1)

    def test_malformed_compact_tensor_rejected(self):
        model=larger();artifact=model.artifact();name='head'
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/'model.json'
            for key,value in (('dtype','<f8'),('shape',[4,32]),('data_base64','A'*100000),('data_base64','!'*len(artifact['parameters'][name]['data_base64']))):
                changed=deepcopy(artifact);changed['parameters'][name][key]=value;path.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):PlannedDecoder.load(path)
            changed=deepcopy(artifact);changed['parameters'][name]['data_base64']=base64.b64encode(np.full(model.shapes[name],np.nan,dtype='<f4').tobytes()).decode();path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):PlannedDecoder.load(path)
            changed=deepcopy(artifact);changed['schema_version']=1;path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):PlannedDecoder.load(path)

    def test_invalid_writer_preserves_existing_destination(self):
        model=larger()
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/'model.json';model.save(path);before=path.read_bytes()
            model.parameters['head'][0,0]=np.nan
            with self.assertRaises(ValueError):model.save(path)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(list(Path(temporary).glob('.model-*')),[])
