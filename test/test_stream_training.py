import importlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np
from backend import decoder_stream_training as training, decoder_bundle
from backend.decoder_recipe import Decoder
import test_stream_model_persistence as persistence_tests


class StreamTrainingTests(unittest.TestCase):
    def setup_stream(self,root):
        return persistence_tests.StreamPersistenceTests().setup_stream(root)[0]

    def test_approval_and_stale_review_create_no_weights(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.setup_stream(root)
            review=training.review(root,record['id'])
            with patch.object(training.recipe_contracts,'initialize_recipe') as initialize:
                with self.assertRaises(ValueError):training.begin(root,record['id'],False,review)
                with self.assertRaises(ValueError):training.begin(root,record['id'],True,{})
                initialize.assert_not_called()
            self.assertFalse((root/'decoder-stream-training-runs').exists())

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real Apple silicon Metal')
    def test_restart_resume_exact_weights_all_heldouts_and_request_replay(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.setup_stream(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            approved=training.review(root,record['id'])
            first=training.begin(root,record['id'],True,approved)
            old=first;first=training.step(root,first['id'],True,first['revision'])
            self.assertEqual(first['completed_steps'],5)
            self.assertEqual(training.step(root,first['id'],True,old['revision']),first)
            initial_bundle=training._folder(root,first['id'])/old['checkpoint']
            initial={p:p.read_bytes() for p in initial_bundle.iterdir()}
            importlib.reload(training);self.assertEqual(training.read(root,first['id']),first)
            while first['status']!='complete':first=training.step(root,first['id'],True,first['revision'])
            second=training.begin(root,record['id'],True,approved)
            while second['status']!='complete':second=training.step(root,second['id'],True,second['revision'])
            one,tok,manifest=decoder_bundle.load(training._folder(root,first['id'])/first['checkpoint'])
            two,_,_=decoder_bundle.load(training._folder(root,second['id'])/second['checkpoint'])
            # Independent Metal reductions can differ at float32 rounding precision.
            for name in one.parameters:np.testing.assert_allclose(one.parameters[name],two.parameters[name],rtol=0,atol=1e-6)
            self.assertTrue(any(not np.array_equal(one.parameters[k],Decoder(one.config).parameters[k]) for k in one.parameters))
            self.assertEqual(first['train_cursor'],second['train_cursor'])
            self.assertEqual(first['source_batch_chain_sha256'],second['source_batch_chain_sha256'])
            self.assertEqual(first['training_targets'],second['training_targets'])
            self.assertEqual(manifest['stages']['tokenization'],4)
            self.assertFalse(first['release_approved']);self.assertLess(first['cpu_inference_max_error'],1e-5)
            for split in ('validation','test'):
                self.assertEqual(first['evaluation'][split]['windows'],record['window_counts'][split])
                self.assertEqual(first['evaluation'][split]['optimizer_updates'],0)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            self.assertTrue(all(p.read_bytes()==data for p,data in initial.items()))
            bad=dict(manifest['training'],completed_steps=6)
            with self.assertRaises(ValueError):tok.validate_training_record(bad)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real Apple silicon Metal')
    def test_publication_failure_and_source_change_keep_last_checkpoint(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.setup_stream(root)
            run=training.begin(root,record['id'],True,training.review(root,record['id']))
            old={p:p.read_bytes() for p in training._folder(root,run['id']).rglob('*') if p.is_file()}
            with patch.object(training,'_publish',side_effect=OSError('publication failed')):
                with self.assertRaises(OSError):training.step(root,run['id'],True,run['revision'])
            self.assertEqual(training.read(root,run['id']),run)
            self.assertTrue(all(p.read_bytes()==data for p,data in old.items()))
            with patch.object(training,'review',return_value={}):
                with self.assertRaises(ValueError):training.step(root,run['id'],True,run['revision'])
            self.assertEqual(training.list_runs(root,record['id'],True),[run])
            retried=training.step(root,run['id'],True,run['revision'])
            self.assertEqual(retried['completed_steps'],5)
