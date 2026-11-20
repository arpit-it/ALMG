from copy import deepcopy
import importlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np
from backend import decoder_stream_evaluations as evaluations, decoder_stream_training as training
from backend.decoder_recipe import Decoder
import test_stream_previews as preview_tests


class StreamEvaluationTests(unittest.TestCase):
    def test_consent_and_incomplete_or_stale_trials_never_score(self):
        with patch.object(Decoder,'logits') as score:
            with self.assertRaises(ValueError):evaluations.evaluate('/unused','a'*32,False,'r')
            for run in ({'revision':'r','status':'paused','completed_steps':5}, {'revision':'old','status':'complete','completed_steps':20}):
                with patch.object(training,'read',return_value=run):
                    with self.assertRaises(ValueError):evaluations.evaluate('/unused','a'*32,True,'r')
            score.assert_not_called()

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real trained Metal fixture')
    def test_full_cpu_evaluation_restart_and_padding_invariance_without_weight_changes(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);run=preview_tests.StreamPreviewTests().complete(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            first=evaluations.evaluate(root,run['id'],True,run['revision'])
            self.assertEqual(first['runtime']['device'],'CPU');self.assertEqual(first['optimizer_updates'],0);self.assertFalse(first['release_approved'])
            for part in ('validation','test'):
                self.assertEqual(first['evaluation'][part]['windows'],run['review']['windows']['window_counts'][part])
                self.assertLess(first['comparison_to_training'][part]['absolute_loss_difference'],1e-5)
                self.assertEqual(first['comparison_to_training'][part]['absolute_accuracy_difference'],0)
            importlib.reload(evaluations)
            self.assertEqual(evaluations.list_reports(root,run['id'],True,run['revision']),[first])
            original=training.batches.iter_batches;changed=0
            def altered(*args,**kwargs):
                nonlocal changed
                for batch in original(*args,**kwargs):
                    batch=deepcopy(batch)
                    for row,mask in zip(batch['targets'],batch['loss_mask']):
                        for index,weight in enumerate(mask):
                            if not weight:row[index]=(row[index]+1)%64;changed+=1
                    yield batch
            with patch.object(training.batches,'iter_batches',side_effect=altered):
                second=evaluations.evaluate(root,run['id'],True,run['revision'])
            self.assertGreater(changed,0);self.assertEqual(first['evaluation'],second['evaluation'])
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real trained Metal fixture')
    def test_nonfinite_scores_source_change_and_publication_failure_save_no_report(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);run=preview_tests.StreamPreviewTests().complete(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(Decoder,'logits',side_effect=lambda tokens:np.full((len(tokens),len(tokens[0]),64),np.nan)):
                with self.assertRaisesRegex(ValueError,'Nonfinite'):evaluations.evaluate(root,run['id'],True,run['revision'])
            with patch.object(evaluations,'_validated',side_effect=[run,ValueError('source changed')]):
                with self.assertRaisesRegex(ValueError,'source changed'):evaluations.evaluate(root,run['id'],True,run['revision'])
            with patch.object(Path,'replace',side_effect=OSError('publication failed')):
                with self.assertRaises(OSError):evaluations.evaluate(root,run['id'],True,run['revision'])
            self.assertEqual(evaluations.list_reports(root,run['id'],True,run['revision']),[])
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
