"""Independent versioned private evaluation bound to bundle and data revisions."""
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np
from backend import decoder_trials, decoder_bundle, decoder_datasets, decoder_dataset_training, studio
from backend.decoder_recipe import Decoder


def documents():
    words = ['amber', 'birch', 'cedar', 'dune']
    return [{'name': f'eval-{i}', 'text': ' '.join(words[(i+j)%4] for j in range(8+i))} for i in range(6)]


class DecoderEvaluationTest(unittest.TestCase):
    def fixture(self, root, kind='words', unrelated=False):
        dataset = decoder_datasets.prepare(root, documents(), True, kind)
        _, tokenizer, _, _ = decoder_dataset_training.preflight(root, dataset)
        record = {'schema_version': 1, 'id': 'a'*32, 'created_at': 'fixture', 'status': 'complete',
                  'dataset': dataset, 'result': {'metrics': {'passed': True}}, 'approval': {'id':'retained'}}
        decoder_trials.write(root, record)
        path = decoder_trials.folder(root, record['id'])/'artifacts/bundle'
        path.parent.mkdir(parents=True)
        model = Decoder({'vocab_size': len(tokenizer.vocabulary)})
        model.parameters['head'][:] = 0
        training = {'scope':'reviewed_local_text_trial', 'dataset_id': 'wrong' if unrelated else dataset['id'],
                    'dataset_sha256':dataset['dataset_sha256'], 'review_sha256':decoder_bundle.digest(dataset),
                    'evaluation': {'initial_train_loss':9.0, 'final_train_loss':0.001, 'passed':True}}
        decoder_bundle.save(path, model, tokenizer, training, pretraining_stage='pretraining_local')
        return record, path

    def test_recomputes_metrics_instead_of_trusting_saved_pass_and_keeps_originals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record, path = self.fixture(root)
            before = {p.name:p.read_bytes() for p in path.iterdir()}
            result = decoder_trials.evaluate(root, record['id'], True)
            self.assertFalse(result['passed'])
            self.assertEqual(result['evaluation_version'], 1)
            self.assertEqual(result['dataset_manifest_sha256'], decoder_bundle.digest(record['dataset']))
            for part in ('train','validation','test'):
                self.assertAlmostEqual(result['metrics'][part]['cross_entropy'], math.log(4))
                self.assertGreater(result['metrics'][part]['evaluated_tokens'], 0)
                self.assertLess(result['metrics'][part]['next_token_accuracy'], .8)
            saved = decoder_trials.read(root, record['id'])
            self.assertEqual(saved['result'], record['result'])
            self.assertEqual(saved['approval'], record['approval'])
            self.assertEqual(saved['evaluations'], [result])
            self.assertEqual({p.name:p.read_bytes() for p in path.iterdir()}, before)

    def test_consent_state_binding_corruption_and_invalid_scores_never_save_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record, path = self.fixture(root, unrelated=True)
            with patch.object(decoder_bundle, 'load') as load, self.assertRaises(ValueError):
                decoder_trials.evaluate(root, record['id'], False)
            load.assert_not_called()
            with self.assertRaisesRegex(ValueError, 'not bound'):
                decoder_trials.evaluate(root, record['id'], True)
            record['status'] = 'interrupted'
            decoder_trials.write(root, record)
            with self.assertRaises(ValueError): decoder_trials.evaluate(root, record['id'], True)
            self.assertNotIn('evaluations', decoder_trials.read(root, record['id']))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record, path = self.fixture(root)
            with patch.object(Decoder, 'logits', return_value=np.full((1, 8, 4), np.nan)), self.assertRaisesRegex(ValueError, 'invalid evaluation'):
                decoder_trials.evaluate(root, record['id'], True)
            (path/'decoder.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                decoder_trials.evaluate(root, record['id'], True)
            self.assertNotIn('evaluations', decoder_trials.read(root, record['id']))

    def test_byte_dataset_api_dispatch_and_history_are_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record, _ = self.fixture(root, 'utf8_bytes')
            record['evaluations'] = [{'id':str(i)} for i in range(20)]
            decoder_trials.write(root, record)
            body = json.dumps({'confirmed':True}).encode()
            handler = Mock(path=f"/decoder-trials/{record['id']}/evaluate", headers={'Content-Length':str(len(body))}, rfile=io.BytesIO(body))
            with patch.object(studio, 'ROOT', root): studio.Handler.do_POST(handler)
            result = handler.respond.call_args.args[0]
            self.assertFalse(result['passed'])
            self.assertAlmostEqual(result['metrics']['test']['cross_entropy'], math.log(256))
            saved = decoder_trials.read(root, record['id'])
            self.assertEqual(len(saved['evaluations']), 20)
            self.assertEqual(saved['evaluations'][0]['id'], '1')
