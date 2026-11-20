import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np
from backend.planned_decoder import PlannedDecoder
from backend import decoder_architecture_plans as plans,decoder_architecture_initializations as checks
from backend.decoder_recipe import Decoder
from backend.run_manifest import digest,file_digest


def config():return {**plans.DEFAULT,'layers':2,'hidden_size':16,'attention_heads':2,'head_dim':8,'feed_forward_size':32,'context_length':32,'vocab_size':128}


def reference(model,tokens):
    p=model.parameters;c=model.config
    def norm(x):return (x-x.mean(axis=-1,keepdims=True))/np.sqrt(x.var(axis=-1,keepdims=True)+1e-5)
    hidden=p['token_embedding'][tokens]+p['position_embedding'][:tokens.shape[1]]
    for layer in range(c['layers']):
        prefix=f'layers.{layer}.';x=norm(hidden);heads=[]
        for head in range(c['attention_heads']):
            start=head*c['head_dim'];end=start+c['head_dim']
            q=(x@p[prefix+'query'])[...,start:end];k=(x@p[prefix+'key'])[...,start:end];v=(x@p[prefix+'value'])[...,start:end]
            scores=(q@k.swapaxes(-1,-2))/np.sqrt(c['head_dim'])
            scores=np.where(np.triu(np.ones(scores.shape[-2:],dtype=bool),1),-np.inf,scores)
            attention=np.exp(scores-scores.max(axis=-1,keepdims=True));attention/=attention.sum(axis=-1,keepdims=True)
            heads.append(attention@v)
        hidden=hidden+np.concatenate(heads,axis=-1)@p[prefix+'attention_output']
        hidden=hidden+np.maximum(norm(hidden)@p[prefix+'feed_forward_in'],0)@p[prefix+'feed_forward_out']
    return norm(hidden)@p['head']


class PlannedDecoderTests(unittest.TestCase):
    def test_multihead_multilayer_reference_causality_seed_and_strict_inputs(self):
        model=PlannedDecoder(config());tokens=np.arange(16).reshape(2,8)
        np.testing.assert_allclose(model.logits(tokens),reference(model,tokens),atol=1e-7,rtol=1e-6)
        changed=tokens.copy();changed[:,4:]+=17
        np.testing.assert_array_equal(model.logits(tokens)[:,:4],model.logits(changed)[:,:4])
        same=PlannedDecoder(config());other=PlannedDecoder({**config(),'seed':8})
        self.assertTrue(all(np.array_equal(value,same.parameters[name]) for name,value in model.parameters.items()))
        self.assertTrue(any(not np.array_equal(value,other.parameters[name]) for name,value in model.parameters.items()))
        for invalid in ([[True]],[[128]],[[0]*33],np.zeros((5,2),dtype=int)):
            with self.assertRaises(ValueError):model.logits(invalid)
        with patch('numpy.random.default_rng') as rng:
            with self.assertRaises(ValueError):PlannedDecoder({**config(),'attention_heads':3})
            rng.assert_not_called()

    def test_single_head_reference_legacy_math_and_new_artifact_reload(self):
        old=Decoder({'vocab_size':64,'width':8,'context_length':16,'seed':7});model=PlannedDecoder(dict(plans.DEFAULT))
        for name,value in old.parameters.items():model.parameters[name if name in ('token_embedding','position_embedding','head') else 'layers.0.'+name]=value.copy()
        np.testing.assert_allclose(model.logits([[0,1,2,3]]),old.logits([[0,1,2,3]]),atol=1e-7,rtol=1e-6)
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/'model.json';model.save(path);loaded=PlannedDecoder.load(path)
            np.testing.assert_array_equal(model.logits([[0,1]]),loaded.logits([[0,1]]))
            with self.assertRaises(ValueError):Decoder.load(path)
            value=json.loads(path.read_text());value['parameters']['head']=[[True]];path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):PlannedDecoder.load(path)

    def test_explicit_approval_resources_and_stale_plan_reject_before_allocation(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);plan=plans.save(root,True,plans.review(config()))
            with patch.object(checks,'PlannedDecoder') as constructor:
                with self.assertRaises(ValueError):checks.run(root,plan['id'],False,plan)
                with self.assertRaises(ValueError):checks.run(root,plan['id'],True,{})
                with patch.object(checks.training_resources,'check_size',side_effect=ValueError('low resources')):
                    with self.assertRaises(ValueError):checks.run(root,plan['id'],True,plan)
                constructor.assert_not_called()
            self.assertFalse((root/'decoder-architecture-initializations').exists())

    def test_exact_roundtrip_seeded_initialization_guard_and_failed_publication(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);plan=plans.save(root,True,plans.review(config()));before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            first=checks.run(root,plan['id'],True,plan);second=checks.run(root,plan['id'],True,plan)
            self.assertEqual(first['actual_parameter_count'],8704);self.assertEqual(first['actual_weight_bytes'],34816)
            self.assertEqual(first['model_sha256'],second['model_sha256']);self.assertEqual(first['reload_cpu_max_error'],0)
            self.assertEqual(checks.read(root,plan['id'],first['id']),first);self.assertFalse(first['backward_checked'])
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            with patch.object(Path,'rename',side_effect=OSError('publication failed')):
                with self.assertRaises(OSError):checks.run(root,plan['id'],True,plan)
            self.assertEqual(len(checks.list_records(root,plan['id'],True)),2)
            folder=checks._folder(root,plan['id'])/first['id'];model=json.loads((folder/'model.json').read_text());model['parameters']['head'][0][0]+=1
            (folder/'model.json').write_text(json.dumps(model));first['model_sha256']=file_digest(folder/'model.json');first['revision']=digest({k:v for k,v in first.items() if k!='revision'});(folder/'record.json').write_text(json.dumps(first))
            with self.assertRaisesRegex(ValueError,'seeded plan'):checks.read(root,plan['id'],first['id'])
            self.assertEqual(len(checks.list_records(root,plan['id'],True)),1)
