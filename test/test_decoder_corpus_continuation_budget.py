import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid
from backend import decoder_corpus_budget as budget, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class ContinuationBudgetTest(unittest.TestCase):
    def test_remaining_masked_targets_begin_at_restored_window_offset(self):
        windows=[{'inputs':[0]*4,'targets':[0]*4,'target_mask':mask} for mask in ([1,1,0,0],[1,0,0,0],[1,1,1,0])]
        config={'steps':10,'batch_size':2,'sequence_length':4,'gradient_accumulation_steps':2}
        result=budget.exposure(windows,config,10,restore_step=5,reference_comparison=False)
        self.assertEqual(result['optimizer_updates'],5);self.assertEqual(result['original_optimizer_updates'],10);self.assertEqual(result['restore_step'],5)
        self.assertEqual(result['recorded_training_target_tokens'],19);self.assertEqual(result['dense_training_token_positions'],40);self.assertEqual(result['padding_target_positions'],21)
        self.assertEqual(result['comparison_reference_target_tokens'],0);self.assertEqual(result['full_workflow_optimizer_target_tokens'],19)
        self.assertEqual(result['initial_window_offset'],1);self.assertEqual(result['final_window_offset'],2)
        self.assertEqual(result['complete_window_passes'],3);self.assertEqual(result['remaining_window_draws'],1)
        zero=budget.exposure(windows,config,10,restore_step=10,reference_comparison=False);self.assertEqual(zero['optimizer_updates'],0);self.assertEqual(zero['recorded_training_target_tokens'],0)

    def test_invalid_restore_counters_are_rejected(self):
        windows=[{'inputs':[0]*4,'targets':[0]*4,'target_mask':[1]*4}];config={'steps':10,'batch_size':1,'sequence_length':4,'gradient_accumulation_steps':1}
        for counter in (True,-1,11,1.5):
            with self.assertRaises(ValueError):budget.exposure(windows,config,10,restore_step=counter,reference_comparison=False)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual continuation and calibration')
    def test_proposal_matches_actual_continued_targets_preserves_source_and_updates_duration(self):
        for kind in ('sgd','adamw'):
            with self.subTest(optimizer=kind),TemporaryDirectory() as temporary:
                root=Path(temporary);source,saved,base=corpus(root);config={**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                parent=isolated.run(root,True,source,saved,config,isolated.review(root,source,saved,config),uuid.uuid4().hex)
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()};proposal=budget.review_continuation(root,parent['id'])
                self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()});self.assertFalse(proposal['training_approved']);self.assertFalse(proposal['release_approved'])
                exposure=proposal['exposure'];self.assertEqual(exposure['restore_step'],10);self.assertEqual(exposure['optimizer_updates'],10);self.assertEqual(exposure['comparison_reference_target_tokens'],0)
                expected=sum(entry['target_tokens'] for entry in parent['step_log'][10:]);self.assertEqual(exposure['recorded_training_target_tokens'],expected)
                with self.assertRaises(ValueError):isolated.run_continuation(root,parent['id'],True,proposal,uuid.uuid4().hex)
                with self.assertRaises(ValueError):isolated.run_continuation(root,parent['id'],False,proposal['resource_review'],uuid.uuid4().hex)
                self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                result=isolated.run_continuation(root,parent['id'],True,proposal['resource_review'],uuid.uuid4().hex)
                self.assertEqual(sum(entry['target_tokens'] for entry in result['step_log']),expected);self.assertEqual(result['completed_steps'],20);self.assertLessEqual(result['reference_parameter_max_error'],1e-7)
                updated=budget.review_continuation(root,parent['id']);work=updated['workflow_duration_estimate'];self.assertIsNotNone(work);self.assertFalse(work['measured']);self.assertTrue(any(item['record_id']==result['id'] for item in work['source_records']))
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
