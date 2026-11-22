from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated, decoder_architecture_plans as plans
from test_decoder_corpus_four_rows import four_rows
from test_decoder_corpus_sixteen_tokens import saved_sixteen,settings


class CorpusActivationReserveTest(unittest.TestCase):
    def test_selected_geometry_counts_quadratic_attention_and_never_lowers_base(self):
        model={**plans.DEFAULT,'layers':1,'hidden_size':8,'attention_heads':1,'head_dim':8,'feed_forward_size':16,'context_length':16,'vocab_size':4,'batch_size':4}
        base=training.hardware.estimate(model,1000);self.assertEqual(base['activation_layout_bytes'],7168)
        expanded=deepcopy(base);training._activation_reserve(model,{'batch_size':2,'sequence_length':16},expanded)
        self.assertEqual(expanded['corpus_activation_layout_bytes'],16384)
        self.assertEqual(expanded['additional_activation_layout_bytes'],9216)
        self.assertEqual(expanded['estimated_gpu_working_bytes'],base['estimated_gpu_working_bytes']+9216)
        self.assertEqual(expanded['estimated_cpu_load_and_reference_bytes'],base['estimated_cpu_load_and_reference_bytes']+18432)
        self.assertEqual(expanded['required_available_memory_bytes'],base['required_available_memory_bytes']+27648)
        smaller=deepcopy(base);training._activation_reserve(model,{'batch_size':1,'sequence_length':4},smaller)
        self.assertEqual(smaller['corpus_activation_layout_bytes'],1664)
        for key in ('activation_layout_bytes','estimated_gpu_working_bytes','estimated_cpu_load_and_reference_bytes','required_available_memory_bytes','required_free_disk_bytes'):
            self.assertEqual(smaller[key],base[key])

    def test_full_verification_rows_are_reserved_even_for_one_row_microbatches(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,corpus,c=four_rows(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            profile={'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},'available_memory_bytes':8*1024**3,'free_disk_bytes':8*1024**3,'errors':[]}
            with patch.object(training.hardware,'hardware',return_value=profile):
                for accumulation in (1,2,4):
                    review=isolated.review(root,source,corpus,{**c,'gradient_accumulation_steps':accumulation});e=review['estimates']
                    self.assertTrue(review['feasible']);self.assertEqual(e['corpus_verification_batch_shape'],[4,8])
                    self.assertEqual(e['corpus_activation_layout_bytes'],14336);self.assertEqual(e['microbatch_rows'],4//accumulation)
                    self.assertEqual(e['additional_activation_layout_bytes'],7168)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real longer-sequence and four-row training')
    def test_expanded_geometries_train_restore_and_continue(self):
        with TemporaryDirectory() as temporary:
            for label in ('long','rows'):
                root=Path(temporary)/label
                if label=='long':source,corpus=saved_sixteen(root);c=settings('adamw')
                else:
                    source,corpus,c=four_rows(root);c={**c,'gradient_accumulation_steps':4}
                reviewed=isolated.review(root,source,corpus,c);e=reviewed['estimates']
                self.assertGreater(e['additional_activation_layout_bytes'],0)
                run=isolated.run(root,True,source,corpus,c,reviewed,uuid.uuid4().hex)
                self.assertLessEqual(run['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(run['checkpoint_optimizer_max_error'],1e-7)
                continued=isolated.run_continuation(root,run['id'],True,isolated.review_continuation(root,run['id']),uuid.uuid4().hex)
                self.assertLessEqual(continued['reference_parameter_max_error'],1e-7)
                self.assertEqual(continued['generated_token_ids'],run['generated_token_ids'])
