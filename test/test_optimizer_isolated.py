import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_optimizer_continuations as continuations,decoder_optimizer_isolated as isolated,decoder_optimizer_fixture as fixture,decoder_architecture_plans as plans,decoder_architecture_initializations as initializations


class IsolatedOptimizerTests(unittest.TestCase):
    def test_no_consent_cannot_spawn_a_worker(self):
        with patch.object(isolated.subprocess,'Popen') as spawn:
            with self.assertRaises(ValueError):isolated.run(Path('/unused'),'a'*32,False,None,None,None)
            with self.assertRaises(ValueError):isolated.run_continuation(Path('/unused'),'a'*32,False,None)
            spawn.assert_not_called()

    def test_peak_floor_above_calculated_reserve_blocks_training_before_worker_launch(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);plan=plans.save(root,True,plans.review(dict(plans.DEFAULT)));source=initializations.run(root,plan['id'],True,plan)
            profile={'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},'available_memory_bytes':8*1024**3,'free_disk_bytes':8*1024**3,'errors':[]}
            with patch.object(fixture.hardware,'hardware',return_value=profile):
                base=fixture.review(root,plan['id'],source,dict(fixture.DEFAULT))['estimates']['required_available_memory_bytes']
                profile['available_memory_bytes']=base+512*1024;floor=base+1024*1024
                with patch.object(fixture.work_estimates,'memory_calibration',return_value={'calculated_memory_floor_bytes':floor}):
                    reviewed=fixture.review(root,plan['id'],source,dict(fixture.DEFAULT))
                    self.assertEqual(reviewed['estimates']['calculated_memory_reserve_bytes'],base)
                    self.assertEqual(reviewed['estimates']['required_available_memory_bytes'],floor);self.assertFalse(reviewed['feasible'])
                    self.assertTrue(any('isolated optimizer calibration' in reason for reason in reviewed['blockers']))
                    with patch.object(isolated.subprocess,'Popen') as spawn:
                        with self.assertRaises(ValueError):isolated.run(root,plan['id'],True,source,dict(fixture.DEFAULT),reviewed)
                        spawn.assert_not_called()
            self.assertFalse((root/'decoder-optimizer-fixtures').exists())

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires fresh-process Metal optimizer execution')
    def test_fresh_worker_peaks_update_review_without_reducing_reserves_or_changing_sources(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);plan=plans.save(root,True,plans.review(dict(plans.DEFAULT)));source=initializations.run(root,plan['id'],True,plan)
            before={p:fixture.file_digest(p) for p in root.rglob('*') if p.is_file()}
            for optimizer in ('sgd','adamw'):
                c={**fixture.DEFAULT,'optimizer':optimizer,'weight_decay':.01 if optimizer=='adamw' else 0.}
                approved=fixture.review(root,plan['id'],source,c);self.assertIsNone(approved['estimates']['isolated_optimizer_memory'])
                with patch.object(isolated.subprocess,'Popen') as spawn,patch.object(fixture.hardware,'hardware',return_value=approved['hardware']):
                    with self.assertRaises(ValueError):isolated.run(root,plan['id'],True,source,{**c,'learning_rate':.02},approved)
                    spawn.assert_not_called()
                report=isolated.run(root,plan['id'],True,source,c,approved);observed=report['isolated_workflow_measurements']
                self.assertNotEqual(observed['process_id'],os.getpid());self.assertTrue(observed['isolated_trial_peak_measured'])
                self.assertGreater(observed['elapsed_seconds'],0.);self.assertGreater(observed['isolated_process_peak_rss_bytes'],0);self.assertGreater(observed['isolated_metal_peak_bytes'],0)
                self.assertEqual(fixture.read(root,report['id']),report);self.assertLess(report['final_train_loss'],report['initial_train_loss'])
                refreshed=fixture.review(root,plan['id'],source,c);est=refreshed['estimates'];calibration=est['isolated_optimizer_memory']
                self.assertEqual(calibration['source_records'][0]['record_id'],report['id'])
                self.assertGreaterEqual(est['required_available_memory_bytes'],approved['estimates']['required_available_memory_bytes'])
                self.assertGreaterEqual(est['required_available_memory_bytes'],calibration['calculated_memory_floor_bytes'])
                self.assertEqual(est['optimizer_work_estimate']['estimated_seconds'],observed['elapsed_seconds']*1.25)
            self.assertTrue(all(fixture.file_digest(p)==sha for p,sha in before.items()))

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires isolated checkpoint continuation')
    def test_isolated_continuation_keeps_original_state_and_calibrates_only_remaining_work(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);plan=plans.save(root,True,plans.review(dict(plans.DEFAULT)));source=initializations.run(root,plan['id'],True,plan)
            for optimizer in ('sgd','adamw'):
                c={**fixture.DEFAULT,'optimizer':optimizer,'weight_decay':.01 if optimizer=='adamw' else 0.}
                parent=isolated.run(root,plan['id'],True,source,c,fixture.review(root,plan['id'],source,c))
                before={p:fixture.file_digest(p) for p in root.rglob('*') if p.is_file()};approved=continuations.review(root,parent['id'])
                self.assertIsNone(approved['estimates']['optimizer_work_estimate'])
                result=isolated.run_continuation(root,parent['id'],True,approved);observed=result['isolated_workflow_measurements']
                self.assertNotEqual(observed['process_id'],os.getpid());self.assertEqual(observed['scope'],'fresh_process_optimizer_checkpoint_continuation')
                self.assertTrue(observed['isolated_trial_peak_measured']);self.assertEqual(result['restored_steps'],5);self.assertEqual(result['completed_steps'],10)
                self.assertEqual(result['source_final_parameter_max_error'],0.);self.assertEqual(continuations.read(root,result['id']),result)
                refreshed=continuations.review(root,parent['id']);est=refreshed['estimates'];self.assertEqual(est['optimizer_updates'],5)
                self.assertEqual(est['optimizer_work_estimate']['estimated_seconds'],observed['elapsed_seconds']*1.25)
                self.assertEqual(est['isolated_optimizer_memory']['source_records'][0]['record_id'],result['id'])
                self.assertGreaterEqual(est['required_available_memory_bytes'],approved['estimates']['required_available_memory_bytes'])
                self.assertTrue(all(fixture.file_digest(p)==sha for p,sha in before.items()))
                profile={**approved['hardware'],'available_memory_bytes':approved['estimates']['required_available_memory_bytes']+512*1024}
                with patch.object(fixture.hardware,'hardware',return_value=profile),patch.object(continuations.measured_feedback,'feedback',return_value=({'calculated_memory_floor_bytes':profile['available_memory_bytes']+1024*1024},None)):
                    blocked=continuations.review(root,parent['id']);self.assertFalse(blocked['feasible'])
                    with patch.object(isolated.subprocess,'Popen') as spawn,patch.object(continuations,'review',return_value=blocked):
                        with self.assertRaises(ValueError):isolated.run_continuation(root,parent['id'],True,blocked)
                        spawn.assert_not_called()
