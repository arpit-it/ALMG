from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_corpus_budget as budget, decoder_corpus_optimizer as training
from test_decoder_corpus_optimizer import corpus


class CorpusBudgetTest(unittest.TestCase):
    def test_real_targets_padding_and_repeated_passes_are_separate(self):
        windows=[{'inputs':[0]*4,'targets':[0]*4,'target_mask':mask} for mask in ([1,1,0,0],[1,0,0,0],[1,1,1,0])]
        result=budget.exposure(windows,{'steps':10,'batch_size':2,'sequence_length':4,'gradient_accumulation_steps':2},10)
        self.assertEqual(result['recorded_training_target_tokens'],39);self.assertEqual(result['dense_training_token_positions'],80);self.assertEqual(result['padding_target_positions'],41)
        self.assertEqual(result['training_window_draws'],20);self.assertEqual(result['complete_window_passes'],6);self.assertEqual(result['remaining_window_draws'],2)
        self.assertEqual(result['training_tokens_per_parameter'],3.9);self.assertEqual(result['full_workflow_optimizer_target_tokens'],78);self.assertFalse(result['measured'])

    def test_review_is_read_only_and_does_not_invent_measured_values_or_approval(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,config=corpus(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(budget.isolated,'run') as run,patch.object(training,'run') as direct:
                result=budget.review(root,source,saved,config);run.assert_not_called();direct.assert_not_called()
            self.assertFalse(result['training_approved']);self.assertFalse(result['release_approved']);self.assertEqual(result['config'],config)
            self.assertEqual(result['exposure']['parameter_count'],704);self.assertEqual(result['exposure']['optimizer_updates'],20)
            self.assertEqual(result['required_available_memory_bytes'],result['resource_review']['estimates']['required_available_memory_bytes'])
            self.assertIsNone(result['optimizer_only_tokens_per_second']);self.assertIsNone(result['estimated_energy_wh']);self.assertIsNone(result['quality_token_requirement'])
            self.assertEqual(result['revision'],training.digest({k:v for k,v in result.items() if k!='revision'}))
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_resource_blockers_remain_blockers_and_unknown_order_is_not_imputed(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,config=corpus(root)
            profile={'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},'available_memory_bytes':1,'free_disk_bytes':1,'errors':[]}
            with patch.object(training.hardware,'hardware',return_value=profile):result=budget.review(root,source,saved,config)
            self.assertFalse(result['feasible']);self.assertTrue(result['blockers']);self.assertFalse(result['training_approved'])
            with patch.object(budget.isolated,'review') as resources:
                with self.assertRaises(ValueError):budget.review(root,source,saved,{**config,'schema_version':10,'data_order':'seeded_shuffle_v1','data_seed':17})
                resources.assert_not_called()
