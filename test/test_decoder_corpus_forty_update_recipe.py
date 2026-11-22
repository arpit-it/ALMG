import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_sixteen_vocab_recipe import sixteen_words


class FortyUpdateRecipeTest(unittest.TestCase):
    def test_exact_budget_and_resource_denials_remain_readonly(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,corpus,base=sixteen_words(root);c={**base,'schema_version':6,'steps':40}
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            profile={'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},'available_memory_bytes':8*1024**3,'free_disk_bytes':8*1024**3,'errors':[]}
            with patch.object(training.hardware,'hardware',return_value=profile):
                for kind in ('sgd','adamw'):
                    settings={**c,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                    review=isolated.review(root,source,corpus,settings);self.assertTrue(review['feasible']);self.assertEqual(review['estimates']['checkpoint_step'],20)
                rejected={**c,'schema_version':7,'steps':80};review=isolated.review(root,source,corpus,rejected);self.assertFalse(review['feasible'])
                with self.assertRaises(ValueError):isolated.run(root,True,source,corpus,rejected,review,uuid.uuid4().hex)
            profile.update(available_memory_bytes=1,free_disk_bytes=1)
            with patch.object(training.hardware,'hardware',return_value=profile):
                review=isolated.review(root,source,corpus,c);self.assertFalse(review['feasible'])
                with self.assertRaises(ValueError):isolated.run(root,True,source,corpus,c,review,uuid.uuid4().hex)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual forty-update sixteen-ID training and recovery')
    def test_both_optimizers_finish_forty_and_restore_twenty_step_midpoint(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,corpus,base=sixteen_words(root)
            for kind in ('sgd','adamw'):
                c={**base,'schema_version':6,'steps':40,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                run=isolated.run(root,True,source,corpus,c,isolated.review(root,source,corpus,c),uuid.uuid4().hex)
                self.assertEqual(run['completed_steps'],40);self.assertEqual(run['checkpoint_restored_steps'],20)
                self.assertLess(run['final_losses']['train'],run['initial_losses']['train'])
                self.assertLessEqual(run['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(run['checkpoint_optimizer_max_error'],1e-7)
                resumed=isolated.run_continuation(root,run['id'],True,isolated.review_continuation(root,run['id']),uuid.uuid4().hex)
                self.assertEqual(resumed['completed_steps'],40);self.assertEqual(resumed['restored_step'],20)
                self.assertLessEqual(resumed['reference_parameter_max_error'],1e-7);self.assertEqual(resumed['generated_token_ids'],run['generated_token_ids'])
