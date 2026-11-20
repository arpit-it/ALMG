from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_isolated as isolated, decoder_corpus_continuations as continuation
from test_decoder_corpus_optimizer import corpus


class CorpusRecoveryIsolationTest(unittest.TestCase):
    def test_no_confirmation_never_starts_a_recovery_worker(self):
        with patch.object(isolated.subprocess,'Popen') as spawn:
            with self.assertRaises(ValueError):isolated.run_continuation(Path('/unused'),'a'*32,False,None)
            with self.assertRaises(ValueError):isolated.run_partial(Path('/unused'),'a'*32,False,None)
            spawn.assert_not_called()

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires isolated corpus recovery on Metal')
    def test_midpoint_and_partial_measurements_stay_scoped_and_canceled_samples_excluded(self):
        training=continuation.training
        with TemporaryDirectory() as temporary:
            root=Path(temporary);initialized,saved,settings=corpus(root)
            for kind,precision in (('sgd','float32'),('adamw','mixed_float16')):
                c={**settings,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'batch_size':2,'gradient_accumulation_steps':2,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.}
                parent=training.run(root,True,initialized,saved,c,training.review(root,initialized,saved,c))
                original=training.optimizer.update;token=uuid.uuid4().hex
                def cancel_first(*args):
                    result=original(*args);continuation.cancellation.request(root,parent['id'],token,True);return result
                with patch.object(training.optimizer,'update',side_effect=cancel_first):partial=continuation.run(root,parent['id'],True,continuation.review(root,parent['id']),token)
                before={path:path.read_bytes() for path in root.rglob('*') if path.is_file()}
                approved=isolated.review_continuation(root,parent['id']);self.assertIsNone(approved['estimates']['corpus_continuation_work_estimate'])
                normal=isolated.run_continuation(root,parent['id'],True,approved)
                observed=normal['isolated_workflow_measurements'];self.assertNotEqual(observed['process_id'],os.getpid());self.assertEqual(observed['action'],'continuation')
                self.assertGreater(observed['isolated_process_peak_rss_bytes'],0);self.assertGreater(observed['isolated_metal_peak_bytes'],0)
                refreshed=isolated.review_continuation(root,parent['id'])['estimates']
                self.assertEqual(refreshed['corpus_continuation_work_estimate']['estimated_seconds'],observed['elapsed_seconds']*1.25)
                approved_partial=isolated.review_partial(root,partial['id']);self.assertIsNone(approved_partial['estimates']['corpus_continuation_work_estimate'])
                resumed=isolated.run_partial(root,partial['id'],True,approved_partial)
                self.assertEqual(resumed['restored_step'],11);self.assertEqual(resumed['completed_steps'],20);self.assertLessEqual(resumed['reference_parameter_max_error'],1e-7)
                self.assertEqual(resumed['isolated_workflow_measurements']['action'],'partial_resume')
                est=isolated.review_partial(root,partial['id'])['estimates']
                self.assertEqual(est['corpus_continuation_work_estimate']['source_records'][0]['record_id'],resumed['id'])
                self.assertGreaterEqual(est['required_available_memory_bytes'],est['calculated_memory_reserve_bytes'])
                self.assertGreaterEqual(est['required_available_memory_bytes'],est['isolated_continuation_memory']['calculated_memory_floor_bytes'])
                early=uuid.uuid4().hex;continuation.cancellation.request(root,partial['id'],early,True,'partial')
                canceled=isolated.run_partial(root,partial['id'],True,isolated.review_partial(root,partial['id']),early)
                self.assertEqual(canceled['status'],'canceled');self.assertEqual(canceled['completed_steps'],11)
                self.assertGreaterEqual(canceled['isolated_workflow_measurements']['isolated_metal_peak_bytes'],0)
                self.assertEqual(isolated.review_partial(root,partial['id'])['estimates']['corpus_continuation_work_estimate']['sample_count'],1)
                self.assertEqual(continuation.read(root,resumed['id']),resumed);self.assertEqual(continuation.read(root,canceled['id']),canceled)
                self.assertTrue(all(path.read_bytes()==data for path,data in before.items()))
                profile={**approved_partial['hardware'],'available_memory_bytes':est['calculated_memory_reserve_bytes']+512*1024}
                with patch.object(training.hardware,'hardware',return_value=profile),patch.object(continuation.measured_feedback,'feedback',return_value=({'calculated_memory_floor_bytes':profile['available_memory_bytes']+1024*1024},None)):
                    blocked=isolated.review_partial(root,partial['id']);self.assertFalse(blocked['feasible'])
                    with patch.object(isolated,'review_partial',return_value=blocked),patch.object(isolated.subprocess,'Popen') as spawn:
                        with self.assertRaises(ValueError):isolated.run_partial(root,partial['id'],True,blocked)
                        spawn.assert_not_called()
