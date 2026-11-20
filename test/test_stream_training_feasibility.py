from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_stream_training_feasibility as feasibility,decoder_stream_training as training
from backend.decoder_recipe import Decoder
import test_stream_training as training_tests


def hardware():
    return {'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{'max_recommended_working_set_size':8*1024**3},
            'available_memory_bytes':8*1024**3,'free_disk_bytes':8*1024**3,'errors':[]}


class StreamTrainingFeasibilityTests(unittest.TestCase):
    def test_review_is_readonly_estimates_match_model_and_no_weights_before_approval(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=training_tests.StreamTrainingTests().setup_stream(root);review=training.review(root,record['id'])
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(feasibility.hardware,'hardware',return_value=hardware()),patch.object(training.recipe_contracts,'initialize_recipe') as initialize:
                result=feasibility.review(root,record['id'],True,review);initialize.assert_not_called()
            model=Decoder({'vocab_size':record['vocabulary_size'],'seed':7})
            self.assertEqual(result['estimates']['parameter_count'],sum(value.size for value in model.parameters.values()))
            self.assertEqual(result['estimates']['parameter_bytes'],sum(value.nbytes for value in model.parameters.values()))
            self.assertEqual(result['estimates']['checkpoint_count'],5);self.assertGreater(result['estimates']['existing_source_index_window_storage_bytes'],0)
            self.assertFalse(result['estimates']['measured']);self.assertIsNone(result['estimates']['duration_estimate_seconds'])
            self.assertTrue(result['feasible']);self.assertEqual(set(before),{p for p in root.rglob('*') if p.is_file()})
            self.assertTrue(all(p.read_bytes()==v for p,v in before.items()))

    def test_unsupported_stale_and_resource_changes_cannot_initialize(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=training_tests.StreamTrainingTests().setup_stream(root);review=training.review(root,record['id'])
            with patch.object(feasibility.hardware,'hardware',return_value=hardware()):
                approved=feasibility.review(root,record['id'],True,review)
                unsupported=feasibility.review(root,record['id'],True,review,'float16')
                self.assertFalse(unsupported['feasible'])
                with patch.object(training,'begin') as begin:
                    for consent,report in ((False,approved),(True,None),(True,unsupported),(True,{**approved,'windows_revision':'changed'})):
                        with self.assertRaises(ValueError):feasibility.begin(root,record['id'],consent,review,report)
                    begin.assert_not_called()
            low=hardware();low['available_memory_bytes']=1
            with patch.object(feasibility.hardware,'hardware',return_value=low),patch.object(training,'begin') as begin:
                with self.assertRaisesRegex(ValueError,'blocked'):feasibility.begin(root,record['id'],True,review,approved)
                begin.assert_not_called()
            with patch.object(feasibility.hardware,'hardware',return_value=hardware()),patch.object(training,'begin',return_value={'fixture':'started'}) as begin:
                self.assertEqual(feasibility.begin(root,record['id'],True,review,approved),{'fixture':'started'});begin.assert_called_once_with(root,record['id'],True,review)
