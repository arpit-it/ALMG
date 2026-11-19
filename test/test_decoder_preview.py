"""Private, verified, bounded decoder inference with durable local history."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np
from backend import decoder_trials, decoder_bundle, studio
from backend.decoder_recipe import Decoder
from backend.decoder_tokenizer import Tokenizer


class DecoderPreviewTest(unittest.TestCase):
    def fixture(self, root, status='complete'):
        record = {'schema_version': 1, 'id': 'a'*32, 'created_at': 'fixture', 'status': status,
                  'approval': {'id': 'retained'}, 'artifact_directory': '/untrusted/path'}
        decoder_trials.write(root, record)
        model = Decoder({'vocab_size': 4, 'context_length': 16})
        model.parameters['head'][:] = 0
        path = decoder_trials.folder(root, record['id'])/'artifacts/bundle'
        path.parent.mkdir(parents=True)
        decoder_bundle.save(path, model, Tokenizer.fit(['amber birch cedar dune']), {'seed': 7, 'steps': 100})
        return record, path

    def test_verified_cpu_preview_uses_sliding_context_and_preserves_trial_and_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record, path = self.fixture(root)
            before = {p.name: p.read_bytes() for p in path.iterdir()}
            result = decoder_trials.preview(root, record['id'], True, 'birch cedar '*8, 32)
            self.assertEqual(result['generated_token_ids'], [0]*32)
            self.assertEqual(result['completion'], ' '.join(['amber']*32))
            self.assertEqual(len(result['text'].split()), 48)
            self.assertEqual(result['inference']['version'], 1)
            self.assertEqual(result['inference']['runtime'], 'numpy_cpu')
            self.assertEqual(result['bundle_manifest_sha256'], decoder_bundle.digest(json.loads((path/'manifest.json').read_text())))
            saved = decoder_trials.read(root, record['id'])
            self.assertEqual(saved['approval'], record['approval'])
            self.assertEqual(saved['status'], 'complete')
            self.assertEqual(saved['previews'], [result])
            self.assertEqual({p.name: p.read_bytes() for p in path.iterdir()}, before)

    def test_consent_state_and_input_bounds_reject_without_inference_or_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record, _ = self.fixture(root)
            for confirmed, prompt, count in ((False, 'amber', 12), (True, '', 12), (True, 'x'*4097, 12),
                                            (True, 'amber', True), (True, 'amber', 0), (True, 'amber', 33)):
                with patch.object(decoder_bundle, 'load') as load, self.assertRaises(ValueError):
                    decoder_trials.preview(root, record['id'], confirmed, prompt, count)
                load.assert_not_called()
            for prompt in ('unknown', ' '.join(['amber']*17)):
                with self.assertRaises(ValueError):
                    decoder_trials.preview(root, record['id'], True, prompt)
            self.assertNotIn('previews', decoder_trials.read(root, record['id']))
            record['status'] = 'interrupted'
            decoder_trials.write(root, record)
            with patch.object(decoder_bundle, 'load') as load, self.assertRaises(ValueError):
                decoder_trials.preview(root, record['id'], True, 'amber')
            load.assert_not_called()

    def test_bundle_corruption_and_invalid_scores_never_save_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record, path = self.fixture(root)
            with patch.object(Decoder, 'logits', return_value=np.full((1, 1, 4), np.nan)), self.assertRaisesRegex(ValueError, 'invalid inference'):
                decoder_trials.preview(root, record['id'], True, 'amber')
            (path/'decoder.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                decoder_trials.preview(root, record['id'], True, 'amber')
            self.assertNotIn('previews', decoder_trials.read(root, record['id']))

    def test_bounded_history_and_api_route_require_current_saved_trial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record, _ = self.fixture(root)
            record['previews'] = [{'id': str(i)} for i in range(20)]
            decoder_trials.write(root, record)
            body = json.dumps({'confirmed': True, 'prompt': 'amber', 'max_new_tokens': 2}).encode()
            handler = Mock(path=f"/decoder-trials/{record['id']}/preview", headers={'Content-Length': str(len(body))}, rfile=io.BytesIO(body))
            with patch.object(studio, 'ROOT', root):
                studio.Handler.do_POST(handler)
            self.assertEqual(handler.respond.call_args.args[0]['completion'], 'amber amber')
            saved = decoder_trials.read(root, record['id'])
            self.assertEqual(len(saved['previews']), 20)
            self.assertEqual(saved['previews'][0]['id'], '1')
