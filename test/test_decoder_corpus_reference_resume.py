import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_optimizer as training, decoder_corpus_reference_resume as resume, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


@unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires retained-reference Metal execution')
class ReferenceResumeTest(unittest.TestCase):
    def test_resume_recancel_and_complete_both_optimizers_without_replaying_carried_updates(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,settings=corpus(root);original=training.optimizer.update
            for kind,precision in (('sgd','float32'),('adamw','mixed_float16')):
                c={**settings,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'batch_size':2,'gradient_accumulation_steps':2,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.}
                approved=training.review(root,source,saved,c);token=uuid.uuid4().hex
                def stop(*args):
                    result=original(*args)
                    training.run_cancellation.request(root,approved,token,True)
                    return result
                with patch.object(training.optimizer,'update',side_effect=stop):parent=training.run(root,True,source,saved,c,approved,request_id=token)
                self.assertEqual(parent['completed_steps'],1)
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                approved=resume.review(root,parent['id'],'shared_backend');token=uuid.uuid4().hex
                self.assertEqual(approved['estimates']['reference_optimizer_updates'],19)
                self.assertEqual(approved['estimates']['recorded_training_optimizer_updates'],20)
                with patch.object(training.optimizer,'update',side_effect=stop):partial=resume.run(root,parent['id'],True,approved,token,'shared_backend')
                self.assertEqual(partial['completed_steps'],2);self.assertEqual(partial['reference_updates_executed'],1)
                self.assertEqual(partial['reference_steps_carried'],1)
                approved=resume.review(root,partial['id'],'shared_backend');token=uuid.uuid4().hex;steps=[]
                def count(*args):
                    steps.append(args[2]['step']);return original(*args)
                with patch.object(training.optimizer,'update',side_effect=count):record=resume.run(root,partial['id'],True,approved,token,'shared_backend')
                self.assertEqual(steps,list(range(2,20))+list(range(20)))
                self.assertEqual(record['reference_resume_depth'],2);self.assertEqual(record['reference_updates_executed'],18)
                self.assertLessEqual(record['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(record['checkpoint_optimizer_max_error'],1e-7)
                self.assertLess(record['final_losses']['train'],record['initial_losses']['train'])
                self.assertEqual(training.read(root,record['id']),record)
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
                with self.assertRaises(ValueError):resume.review(root,record['id'])
                with self.assertRaises(ValueError):resume.run(root,partial['id'],False,approved,uuid.uuid4().hex,'shared_backend')
                stale={**approved,'reference_resume_from':{**approved['reference_resume_from'],'completed_steps':1}}
                stale['revision']=training.digest({k:v for k,v in stale.items() if k!='revision'})
                with self.assertRaises(ValueError):resume.run(root,partial['id'],True,stale,uuid.uuid4().hex,'shared_backend')
                path=training._folder(root,partial['id'])/'record.json';data=json.loads(path.read_text());data['review']['reference_resume_from']['record_id']=partial['id'];data['review']['revision']=training.digest({k:v for k,v in data['review'].items() if k!='revision'});data['revision']=training.digest({k:v for k,v in data.items() if k!='revision'});original_record=path.read_bytes();path.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,'Cyclic'):training.read(root,partial['id'])
                path.write_bytes(original_record)

    def test_isolated_reference_resume_has_distinct_measurements_and_cannot_calibrate_full_runs(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=corpus(root);review=isolated.review(root,source,saved,c);token=uuid.uuid4().hex
            training.run_cancellation.request(root,review,token,True)
            parent=isolated.run(root,True,source,saved,c,review,token)
            approved=isolated.review_reference_resume(root,parent['id'])
            record=isolated.run_reference_resume(root,parent['id'],True,approved,uuid.uuid4().hex)
            self.assertEqual(record['reference_steps_carried'],0);self.assertEqual(record['reference_updates_executed'],20)
            self.assertEqual(record['isolated_workflow_measurements']['scope'],'fresh_process_corpus_reference_resume')
            self.assertNotEqual(record['isolated_workflow_measurements']['process_id'],os.getpid())
            self.assertIsNone(isolated.review(root,source,saved,c)['estimates']['corpus_work_estimate'])
            self.assertEqual(training.read(root,record['id']),record)
