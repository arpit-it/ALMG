from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_trial_feasibility as feasibility,decoder_trials as trials,decoder_datasets,decoder_training


def documents():
    words=['amber','birch','cedar','dune']
    return [{'name':f'local-{i}.txt','text':' '.join(words[(i+j)%4] for j in range(8+i))} for i in range(6)]


class DecoderResumeFeasibilityTests(unittest.TestCase):
    def interrupted(self,root):
        record=trials.start(root,True,lambda *args:None)
        key=(str(root),record['id']);trials._ACTIVE.discard(key);trials._CANCEL.pop(key,None)
        record['status']='interrupted';trials.write(root,record);return record

    def test_readonly_no_checkpoint_review_and_stale_resume_never_submit(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.interrupted(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            review=feasibility.resume_review(root,record['id']);self.assertEqual(review['resume']['checkpoint'],{'completed_steps':0,'files':{}})
            self.assertEqual(review['resume']['previous_approval_sha256'],feasibility.digest(record['approval']))
            self.assertTrue(all(p.read_bytes()==value for p,value in before.items()))
            stale=deepcopy(review);stale['resume']['checkpoint']['completed_steps']=50
            with patch.object(trials,'start') as start:
                with self.assertRaises(ValueError):feasibility.resume(root,record['id'],False,lambda *args:None,review)
                with self.assertRaisesRegex(ValueError,'review changed'):feasibility.resume(root,record['id'],True,lambda *args:None,stale)
                start.assert_not_called()
            self.assertEqual(trials.read(root,record['id']),record)

    def test_changed_submission_feasibility_never_reaches_optimizer_queue(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.interrupted(root);review=feasibility.resume_review(root,record['id'])
            changed=feasibility.review(root);changed['implementation_sha256']='changed';changed['revision']=feasibility.digest({k:v for k,v in changed.items() if k!='revision'})
            with patch.object(feasibility,'admit',return_value=changed):
                queued=[]
                with self.assertRaisesRegex(ValueError,'changed before submission'):feasibility.resume(root,record['id'],True,lambda *args:queued.append(args),review)
            self.assertEqual(queued,[]);self.assertEqual(trials.read(root,record['id'])['status'],'interrupted')

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual interrupted/resumed Metal training')
    def test_actual_step50_checkpoint_is_bound_preserved_and_reused_after_resume_approval(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);dataset=decoder_datasets.prepare(root,documents(),True);queued=[]
            record=feasibility.start(root,True,lambda function,*args:queued.append((function,args)),feasibility.review(root,dataset),dataset=dataset)
            original=trials.decoder_dataset_training.run
            checkpoint=trials.folder(root,record['id'])/'artifacts/step-50'
            def interrupted(*args,stop=None,**kwargs):
                def boundary():
                    if (checkpoint/'manifest.json').exists():raise decoder_training.Cancelled('Fixture interruption after saved checkpoint.')
                    return stop() if stop else False
                return original(*args,stop=boundary,**kwargs)
            function,args=queued.pop()
            with patch.object(trials.decoder_dataset_training,'run',side_effect=interrupted):function(*args)
            saved=trials.read(root,record['id']);self.assertEqual(saved['status'],'interrupted');initial_profile=saved['local_dataset_trial_hardware']
            before={p:p.read_bytes() for p in checkpoint.iterdir()};review=feasibility.resume_review(root,record['id'])
            self.assertEqual(review['resume']['checkpoint']['completed_steps'],50)
            self.assertEqual(set(review['resume']['checkpoint']['files']),{'manifest.json','decoder.json','tokenizer.json'})
            feasibility.resume(root,record['id'],True,lambda function,*args:queued.append((function,args)),review)
            pending=trials.read(root,record['id']);self.assertEqual(pending['resume_hardware_reviews'][-1]['approval'],review)
            function,args=queued.pop();function(*args);complete=trials.read(root,record['id'])
            self.assertEqual(complete['status'],'complete',complete.get('error'));self.assertTrue(complete['result']['checkpoint']['reused_existing_checkpoint'])
            self.assertEqual(complete['local_dataset_trial_hardware'],initial_profile);self.assertTrue(all(p.read_bytes()==value for p,value in before.items()))
            self.assertEqual(len(complete['previous_approvals']),1)
            # Corrupting a saved checkpoint is detected without deserializing model tensors.
            path=checkpoint/'decoder.json';path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'Checkpoint'):feasibility._checkpoint(root,record['id'])
