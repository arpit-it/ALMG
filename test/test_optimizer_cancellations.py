import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np
from backend import decoder_optimizer_cancellations as cancellation,decoder_optimizer_continuations as continuations,decoder_optimizer_fixture as fixture,decoder_optimizer_isolated as isolated,decoder_architecture_plans as plans,decoder_architecture_initializations as initializations


class OptimizerCancellationTests(unittest.TestCase):
    def test_intents_need_consent_and_bind_request_token_source_and_revision(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source='a'*32;token='b'*32
            with self.assertRaises(ValueError):cancellation.request(root,source,token,False)
            self.assertEqual(list(root.rglob('*')),[])
            with patch.object(fixture,'read',return_value={'revision':'source-revision'}):
                record=cancellation.request(root,source,token,True);self.assertEqual(cancellation.request(root,source,token,True),record)
            self.assertTrue(cancellation.requested(root,source,'source-revision',token))
            self.assertFalse(cancellation.requested(root,source,'source-revision','c'*32))
            with self.assertRaises(ValueError):cancellation.requested(root,'d'*32,'source-revision',token)
            with self.assertRaises(ValueError):cancellation.requested(root,source,'changed',token)
            with self.assertRaises(ValueError):cancellation.validate('../outside')
            cancellation._path(root,token).write_text('{}')
            with self.assertRaises(ValueError):cancellation.requested(root,source,'source-revision',token)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real checkpoint cancellation and optimizer-state recovery')
    def test_mid_update_cancel_saves_state_that_can_numerically_finish_the_original_budget(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);plan=plans.save(root,True,plans.review(dict(plans.DEFAULT)));source=initializations.run(root,plan['id'],True,plan)
            c={**fixture.DEFAULT,'schema_version':5,'optimizer':'adamw','weight_decay':.01,'compute_precision':'mixed_float16','loss_scale':128.,'gradient_accumulation_steps':2,'batch_size':2,'sequence_length':8,'steps':20}
            parent=fixture.run(root,plan['id'],True,source,c,fixture.review(root,plan['id'],source,c));before={p:fixture.file_digest(p) for p in root.rglob('*') if p.is_file()};token='a'*32;update=fixture.update
            def cancel_after_update(*args):
                result=update(*args)
                if result[1]['step']==12:cancellation.request(root,parent['id'],token,True)
                return result
            approved=continuations.review(root,parent['id'])
            with patch.object(fixture,'update',side_effect=cancel_after_update):record=continuations.run(root,parent['id'],True,approved,token)
            self.assertEqual(record['format'],'almg-optimizer-continuation-v2');self.assertEqual(record['status'],'canceled');self.assertEqual(record['completed_steps'],12)
            self.assertEqual(record['scheduler_completed_steps'],12);self.assertEqual([entry['step'] for entry in record['step_log']],[11,12])
            self.assertIsNone(record['source_final_parameter_max_error']);self.assertFalse(record['release_approved']);self.assertEqual(continuations.read(root,record['id']),record)
            self.assertIsNone(continuations.review(root,parent['id'])['estimates']['optimizer_work_estimate'])
            folder=continuations._folder(root,record['id']);model=fixture.PlannedDecoder.load(folder/'trained-model.json');saved=json.loads((folder/'optimizer.json').read_text());state={'step':saved['step'],**{kind:{name:np.asarray(value,dtype=np.float32) for name,value in saved[kind].items()} for kind in ('m','v')}}
            sequence=np.arange(18).reshape(2,9)%model.config['vocab_size'];x=sequence[:,:-1];y=sequence[:,1:];mask=np.ones_like(y,dtype=np.float32)
            import mlx.core as mx
            with mx.stream(mx.gpu):
                _,_,gradient=fixture.mixed_precision.functions(model.config,mx,128.)
                while state['step']<20:
                    pieces=[]
                    for a,b,m in zip(np.array_split(x,2),np.array_split(y,2),np.array_split(mask,2)):
                        g=gradient({name:mx.array(value) for name,value in model.parameters.items()},mx.array(a),mx.array(b),mx.array(m));mx.eval(g)
                        pieces.append((fixture.mixed_precision.unscale({name:np.array(value) for name,value in g.items()},128.),int(m.sum())))
                    model.parameters,state,_=update(model.parameters,fixture.accumulate(pieces),state,c)
            expected=fixture.PlannedDecoder.load(fixture._folder(root,parent['id'])/'trained-model.json')
            self.assertTrue(all(np.array_equal(model.parameters[name],value) for name,value in expected.parameters.items()))
            self.assertTrue(all(fixture.file_digest(p)==sha for p,sha in before.items()))
            queued='b'*32;cancellation.request(root,parent['id'],queued,True)
            stopped=isolated.run_continuation(root,parent['id'],True,continuations.review(root,parent['id']),queued)
            self.assertEqual(stopped['status'],'canceled');self.assertEqual(stopped['completed_steps'],10);self.assertEqual(stopped['step_log'],[])
            self.assertNotEqual(stopped['isolated_workflow_measurements']['process_id'],os.getpid());self.assertEqual(continuations.read(root,stopped['id']),stopped)
            self.assertIsNone(continuations.review(root,parent['id'])['estimates']['optimizer_work_estimate'])
