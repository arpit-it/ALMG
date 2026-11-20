from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_continuations as continuation
from test_decoder_corpus_optimizer import corpus


class CorpusPartialResumeTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real Metal checkpoint resumption')
    def test_chained_cancel_resume_restores_retained_state_and_original_schedule(self):
        training=continuation.training
        with TemporaryDirectory() as temporary:
            root=Path(temporary);initialized,saved,settings=corpus(root)
            for kind,precision in (('sgd','float32'),('adamw','mixed_float16')):
                c={**settings,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'batch_size':2,
                   'gradient_accumulation_steps':2,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.}
                parent=training.run(root,True,initialized,saved,c,training.review(root,initialized,saved,c))
                token=uuid.uuid4().hex;original=training.optimizer.update
                def stop_after_update(*args):
                    result=original(*args);continuation.cancellation.request(root,parent['id'],token,True);return result
                with patch.object(training.optimizer,'update',side_effect=stop_after_update):
                    partial=continuation.run(root,parent['id'],True,continuation.review(root,parent['id']),token)
                self.assertEqual(partial['completed_steps'],11)
                approved=continuation.review_partial(root,partial['id'])
                self.assertEqual(approved['restore_step'],11);self.assertEqual(approved['estimates']['optimizer_updates'],9)
                self.assertEqual(approved['resume_from']['optimizer_sha256'],partial['files']['optimizer.json'])
                before={path:path.read_bytes() for path in root.rglob('*') if path.is_file()}
                with self.assertRaises(ValueError):continuation.run_partial(root,partial['id'],False,approved)
                changed=deepcopy(approved);changed['resume_from']['record_revision']='changed'
                with self.assertRaises(ValueError):continuation.run_partial(root,partial['id'],True,changed)
                new_token=uuid.uuid4().hex
                def cancel_resumed(*args):
                    result=original(*args);continuation.cancellation.request(root,partial['id'],new_token,True,'partial');return result
                with patch.object(training.optimizer,'update',side_effect=cancel_resumed):
                    again=continuation.run_partial(root,partial['id'],True,approved,new_token)
                self.assertEqual(again['schema_version'],3);self.assertEqual(again['status'],'canceled')
                self.assertEqual(again['restored_step'],11);self.assertEqual(again['completed_steps'],12)
                self.assertEqual(again['lineage_depth'],2)
                with self.assertRaises(ValueError):continuation.cancellation.request(root,parent['id'],new_token,True)
                final=continuation.run_partial(root,again['id'],True,continuation.review_partial(root,again['id']))
                self.assertEqual(final['restored_step'],12);self.assertEqual(final['completed_steps'],20)
                self.assertEqual(final['scheduler_completed_steps'],20);self.assertEqual(final['lineage_depth'],3)
                self.assertEqual([entry['step'] for entry in final['step_log']],list(range(13,21)))
                self.assertEqual([entry['learning_rate'] for entry in final['step_log']],[entry['learning_rate'] for entry in parent['step_log'][12:]])
                self.assertLessEqual(final['reference_parameter_max_error'],1e-7)
                self.assertEqual(final['generated_token_ids'],parent['generated_token_ids'])
                self.assertEqual(continuation.read(root,final['id']),final)
                self.assertTrue(all(path.read_bytes()==content for path,content in before.items()))
                with self.assertRaises(ValueError):continuation.review_partial(root,final['id'])
                record=deepcopy(again);record['review']['resume_from']['record_id']=again['id']
                record['review']['revision']=training.digest({k:v for k,v in record['review'].items() if k!='revision'})
                record['revision']=training.digest({k:v for k,v in record.items() if k!='revision'})
                path=continuation._folder(root,again['id'])/'record.json';original_record=path.read_bytes();path.write_text(json.dumps(record))
                with self.assertRaises(ValueError):continuation.read(root,again['id'])
                path.write_bytes(original_record)
                with self.assertRaises(ValueError):continuation.read(root,final['id'],set(str(index) for index in range(16)))
