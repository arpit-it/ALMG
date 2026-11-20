from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_corpus_continuations as continuation
from test_decoder_corpus_optimizer import corpus


class CorpusContinuationTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real corpus Metal training')
    def test_separate_confirmation_remaining_work_restore_and_private_lineage(self):
        training = continuation.training
        with TemporaryDirectory() as temporary:
            root=Path(temporary); initialized,saved,settings=corpus(root)
            for kind,precision in (('sgd','float32'),('adamw','mixed_float16')):
                c={**settings,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'batch_size':2,
                   'gradient_accumulation_steps':2,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.}
                parent=training.run(root,True,initialized,saved,c,training.review(root,initialized,saved,c))
                before={path:path.read_bytes() for path in root.rglob('*') if path.is_file()}
                approved=continuation.review(root,parent['id'])
                self.assertEqual(approved['restore_step'],10);self.assertEqual(approved['estimates']['optimizer_updates'],10)
                self.assertEqual(approved['source']['optimizer_sha256'],parent['files']['step-10/optimizer.json'])
                with self.assertRaises(ValueError):continuation.run(root,parent['id'],False,approved)
                changed=deepcopy(approved);changed['source']['record_revision']='changed'
                with self.assertRaises(ValueError):continuation.run(root,parent['id'],True,changed)
                blocked_profile={**approved['hardware'],'available_memory_bytes':1}
                with patch.object(training.hardware,'hardware',return_value=blocked_profile):
                    with self.assertRaises(ValueError):continuation.run(root,parent['id'],True,approved)
                self.assertEqual({path:path.read_bytes() for path in root.rglob('*') if path.is_file()},before)
                record=continuation.run(root,parent['id'],True,approved)
                self.assertEqual(record['restored_step'],10);self.assertEqual(record['completed_steps'],20)
                self.assertEqual(record['scheduler_completed_steps'],20)
                self.assertEqual([entry['step'] for entry in record['step_log']],list(range(11,21)))
                for entry,original in zip(record['step_log'],parent['step_log'][10:]):
                    self.assertEqual(entry['window_indices'],original['window_indices'])
                    self.assertEqual(entry['learning_rate'],original['learning_rate'])
                    self.assertEqual(entry['target_tokens'],original['target_tokens'])
                self.assertLessEqual(record['reference_parameter_max_error'],1e-7)
                self.assertEqual(record['generated_token_ids'],parent['generated_token_ids'])
                self.assertEqual(record['generated_text'],parent['generated_text'])
                self.assertLess(record['final_losses']['train'],record['initial_losses']['train'])
                self.assertEqual(continuation.read(root,record['id']),record)
                self.assertEqual(continuation.history(root,parent['id']),[record])
                self.assertTrue(all(path.read_bytes()==content for path,content in before.items()))
                self.assertFalse(record['release_approved']);self.assertFalse(record['source_modified'])
                folder=continuation._folder(root,record['id']);state=json.loads((folder/'optimizer.json').read_text())
                self.assertEqual(state['step'],20)
                if kind=='adamw':self.assertTrue(state['m'] and state['v'])
                altered=deepcopy(record);altered['step_log'][0]['learning_rate']*=2
                altered['revision']=training.digest({k:v for k,v in altered.items() if k!='revision'})
                (folder/'record.json').write_text(json.dumps(altered))
                with self.assertRaises(ValueError):continuation.read(root,record['id'])
                (folder/'record.json').write_text(json.dumps(record))
                original_state=(folder/'optimizer.json').read_bytes()
                state['step']=19;(folder/'optimizer.json').write_text(json.dumps(state))
                with self.assertRaises(ValueError):continuation.read(root,record['id'])
                (folder/'optimizer.json').write_bytes(original_state)
                checkpoint=training._folder(root,parent['id'])/'step-10'/'optimizer.json'
                original_checkpoint=checkpoint.read_bytes();checkpoint.write_bytes(original_checkpoint+b' ')
                with self.assertRaises(ValueError):continuation.review(root,parent['id'])
                checkpoint.write_bytes(original_checkpoint)

    def test_no_confirmation_never_reads_or_creates_a_source(self):
        with TemporaryDirectory() as temporary,patch.object(continuation,'review') as review:
            with self.assertRaises(ValueError):continuation.run(Path(temporary),'not-a-source',False,None)
            review.assert_not_called();self.assertEqual(list(Path(temporary).iterdir()),[])
