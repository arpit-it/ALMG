import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_optimizer as training, decoder_corpus_training_resume as resume, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


@unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires recorded-training Metal recovery')
class TrainingResumeTest(unittest.TestCase):
    def test_resume_each_checkpoint_boundary_recancel_and_finish_without_reference_retraining(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,settings=corpus(root);original=training.optimizer.update
            for kind,precision in (('sgd','float32'),('adamw','mixed_float16')):
                c={**settings,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'batch_size':2,'gradient_accumulation_steps':2,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.}
                for target in (20,21,30,31):
                    approved=training.review(root,source,saved,c);token=uuid.uuid4().hex;calls=0
                    def stop_source(*args):
                        nonlocal calls
                        result=original(*args);calls+=1
                        if calls==target:training.run_cancellation.request(root,approved,token,True)
                        return result
                    with patch.object(training.optimizer,'update',side_effect=stop_source):parent=training.run(root,True,source,saved,c,approved,request_id=token)
                    self.assertEqual(parent['cancellation_phase'],'checkpointed_training');self.assertEqual(parent['completed_steps'],target-20)
                    before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                    approved=resume.review(root,parent['id'],'shared_backend');token=uuid.uuid4().hex
                    self.assertEqual(approved['estimates']['reference_optimizer_updates'],0)
                    self.assertEqual(approved['estimates']['recorded_training_optimizer_updates'],20-parent['completed_steps'])
                    def stop(*args):
                        result=original(*args);training.run_cancellation.request(root,approved,token,True);return result
                    with patch.object(training.optimizer,'update',side_effect=stop):partial=resume.run(root,parent['id'],True,approved,token,'shared_backend')
                    self.assertEqual(partial['completed_steps'],parent['completed_steps']+1);self.assertEqual(partial['training_updates_executed'],1)
                    self.assertEqual(partial['reference_updates_executed'],0)
                    approved=resume.review(root,partial['id'],'shared_backend');steps=[]
                    def count(*args):steps.append(args[2]['step']);return original(*args)
                    with patch.object(training.optimizer,'update',side_effect=count):record=resume.run(root,partial['id'],True,approved,uuid.uuid4().hex,'shared_backend')
                    self.assertEqual(steps,list(range(partial['completed_steps'],20)))
                    self.assertEqual(record['training_resume_depth'],2);self.assertEqual(record['training_updates_executed'],20-partial['completed_steps'])
                    self.assertEqual(record['reference_step_log'],parent['reference_step_log']);self.assertEqual(record['reference_updates_executed'],0)
                    self.assertLessEqual(record['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(record['checkpoint_optimizer_max_error'],1e-7)
                    self.assertLess(record['final_losses']['train'],record['initial_losses']['train'])
                    self.assertEqual(training.read(root,record['id']),record)
                    self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
                    if parent['completed_steps']>=10:
                        for name in ('model.json','optimizer.json'):self.assertEqual(record['files']['step-10/'+name],parent['files']['step-10/'+name])
                    with self.assertRaises(ValueError):resume.review(root,record['id'])
                    with self.assertRaises(ValueError):resume.run(root,partial['id'],False,approved,uuid.uuid4().hex,'shared_backend')
                    stale={**approved,'training_resume_from':{**approved['training_resume_from'],'completed_steps':0}};stale['revision']=training.digest({k:v for k,v in stale.items() if k!='revision'})
                    with self.assertRaises(ValueError):resume.run(root,partial['id'],True,stale,uuid.uuid4().hex,'shared_backend')
                    path=training._folder(root,partial['id'])/'record.json';original_record=path.read_bytes();data=json.loads(original_record);data['review']['training_resume_from']['record_id']=partial['id'];data['review']['revision']=training.digest({k:v for k,v in data['review'].items() if k!='revision'});data['revision']=training.digest({k:v for k,v in data.items() if k!='revision'});path.write_text(json.dumps(data))
                    with self.assertRaisesRegex(ValueError,'Cyclic'):training.read(root,partial['id'])
                    path.write_bytes(original_record)

    def test_isolated_training_resume_and_zero_update_recancel_never_calibrate_full_runs(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=corpus(root);approved=training.review(root,source,saved,c);token=uuid.uuid4().hex;original=training.optimizer.update;calls=0
            def stop(*args):
                nonlocal calls
                result=original(*args);calls+=1
                if calls==31:training.run_cancellation.request(root,approved,token,True)
                return result
            with patch.object(training.optimizer,'update',side_effect=stop):parent=training.run(root,True,source,saved,c,approved,request_id=token)
            reviewed=isolated.review_training_resume(root,parent['id']);new_token=uuid.uuid4().hex
            training.run_cancellation.request(root,reviewed,new_token,True)
            partial=isolated.run_training_resume(root,parent['id'],True,reviewed,new_token)
            self.assertEqual(partial['completed_steps'],11);self.assertEqual(partial['training_updates_executed'],0)
            record=isolated.run_training_resume(root,partial['id'],True,isolated.review_training_resume(root,partial['id']),uuid.uuid4().hex)
            self.assertEqual(record['training_steps_carried'],11);self.assertEqual(record['training_updates_executed'],9)
            self.assertEqual(record['isolated_workflow_measurements']['scope'],'fresh_process_corpus_training_resume')
            self.assertNotEqual(record['isolated_workflow_measurements']['process_id'],os.getpid())
            self.assertIsNone(isolated.review(root,source,saved,c)['estimates']['corpus_work_estimate'])
            self.assertEqual(training.read(root,record['id']),record)
