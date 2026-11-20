import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated, decoder_corpus_continuations
from test_decoder_corpus_optimizer import corpus


class FreshCorpusCancellationTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real reference/training update cancellation')
    def test_cancel_each_phase_retains_actual_state_and_completed_reference_checkpoints(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,settings=corpus(root)
            original=training.optimizer.update
            for kind,precision in (('sgd','float32'),('adamw','mixed_float16')):
                c={**settings,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'batch_size':2,'gradient_accumulation_steps':2,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.}
                for target,phase,step in ((1,'reference_verification',1),(21,'checkpointed_training',1),(31,'checkpointed_training',11)):
                    approved=training.review(root,source,saved,c);token=uuid.uuid4().hex;calls=0
                    before={path:path.read_bytes() for path in root.rglob('*') if path.is_file()}
                    def stop_at_update(*args):
                        nonlocal calls
                        result=original(*args);calls+=1
                        if calls==target:training.run_cancellation.request(root,approved,token,True)
                        return result
                    with patch.object(training.optimizer,'update',side_effect=stop_at_update):record=training.run(root,True,source,saved,c,approved,request_id=token)
                    self.assertEqual(record['status'],'canceled');self.assertEqual(record['cancellation_phase'],phase)
                    self.assertEqual(record['completed_steps'],step);self.assertEqual(record['scheduler_completed_steps'],step)
                    self.assertFalse(record['reference_verified']);self.assertFalse(record['release_approved'])
                    self.assertEqual(record['checkpoint_restored_steps'],10 if step==11 else 0)
                    if phase=='checkpointed_training':
                        self.assertEqual(record['reference_completed_steps'],20)
                        self.assertIn('reference-model.json',record['files']);self.assertIn('reference-optimizer.json',record['files'])
                    self.assertEqual(training.read(root,record['id']),record)
                    self.assertTrue(all(path.read_bytes()==data for path,data in before.items()))
                    with self.assertRaises(ValueError):decoder_corpus_continuations.review(root,record['id'])
                    receipt=training.run_cancellation.request(root,approved,token,True)
                    self.assertEqual(training.run_cancellation.request(root,approved,token,True),receipt)
                    changed=training.review(root,source,saved,{**c,'steps':10})
                    with self.assertRaises(ValueError):training.run_cancellation.request(root,changed,token,True)
                    path=training._folder(root,record['id'])/'optimizer.json';original_state=path.read_bytes();data=json.loads(path.read_text());data['step']+=1;path.write_text(json.dumps(data))
                    with self.assertRaises(ValueError):training.read(root,record['id'])
                    path.write_bytes(original_state)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires a fresh-process cancellation boundary')
    def test_preexisting_intent_retains_initial_phase_and_never_calibrates_feedback(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=corpus(root);approved=isolated.review(root,source,saved,c);token=uuid.uuid4().hex
            training.run_cancellation.request(root,approved,token,True)
            record=isolated.run(root,True,source,saved,c,approved,token)
            self.assertEqual(record['status'],'canceled');self.assertEqual(record['completed_steps'],0)
            self.assertEqual(record['step_log'],[]);self.assertEqual(record['cancellation_phase'],'reference_verification')
            self.assertIsNone(isolated.review(root,source,saved,c)['estimates']['corpus_work_estimate'])
            self.assertEqual(training.read(root,record['id']),record)

    def test_cancel_requires_consent_review_binding_and_safe_token(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            with self.assertRaises(ValueError):training.run_cancellation.request(root,None,'../bad',False)
            with self.assertRaises(ValueError):training.run_cancellation.validate('../bad')
            self.assertFalse(training.run_cancellation.requested(root,None,None));self.assertEqual(list(root.iterdir()),[])

    def test_cancel_api_accepts_frozen_review_without_launch_initialization_body(self):
        import io
        from unittest.mock import Mock
        from backend import studio
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=corpus(root);approved=isolated.review(root,source,saved,c);token=uuid.uuid4().hex
            body=json.dumps({'confirmed':True,'reviewed_feasibility':approved,'request_id':token}).encode()
            handler=Mock(path=f"/decoder-architecture-plans/{source['plan_id']}/corpus-optimizer-cancel",headers={'Content-Length':str(len(body))},rfile=io.BytesIO(body));handler.authorized.return_value=True
            with patch.object(studio,'ROOT',root),patch.object(studio.inference.WORKER,'submit') as submit:
                studio.Handler.do_POST(handler);submit.assert_not_called()
            self.assertTrue(handler.respond.call_args.args[0]['cancel_requested'])
            wrong=Mock(path='/decoder-architecture-plans/'+'e'*32+'/corpus-optimizer-cancel',headers={'Content-Length':str(len(body))},rfile=io.BytesIO(body));wrong.authorized.return_value=True
            with patch.object(studio,'ROOT',root):studio.Handler.do_POST(wrong)
            self.assertIn('another architecture',wrong.respond.call_args.args[0]['error'])
