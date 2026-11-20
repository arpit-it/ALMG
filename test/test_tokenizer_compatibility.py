import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend import decoder_datasets as datasets, decoder_tokenizer_experiments as experiments
from backend import decoder_tokenizer_compatibility as compatibility
from backend.decoder_recipe import Decoder
from backend.run_manifest import digest, file_digest
from backend.decoder_character_bpe import CharacterBPE


class CompatibilityTests(unittest.TestCase):
    def prepare(self, root, multilingual=False, **config):
        texts = (['banana bandana café '*8, '日本語 世界 宇宙 '*8, 'नमस्ते दुनिया '*8,
                  'orchard apple harvest '*8, 'emoji 🐈 🚀 '*8] if multilingual else
                 ['abcdefghijklmnopqrstuvwxyz ' + text for text in
                  ('orchard apple harvest', 'telescope stars planets', 'river water stones',
                   'violin piano music', 'garden flower seeds')])
        dataset = datasets.prepare(root, [{'name': f'{i}.txt', 'text': text} for i, text in enumerate(texts)], True, 'utf8_bytes')
        record = experiments.train(root, dataset['id'], True, dataset,
                                   {'algorithm': 'character_bpe', 'vocabulary_cap': 128, **config})
        return dataset, record

    def test_lossless_matching_ids_including_controls_no_writes_or_weight_initialization(self):
        with TemporaryDirectory() as root:
            dataset, record = self.prepare(root, special_tokens={'pad':'<PAD>', 'bos':'<BOS>', 'eos':'<EOS>'})
            before = {str(p.relative_to(root)):p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}
            with patch.object(Decoder, '__init__', side_effect=AssertionError('No weights should be initialized')):
                result = compatibility.review(root, record['id'], record, {'vocab_size':record['vocabulary_size']})
            self.assertTrue(result['vocabulary_and_lossless_checks_passed'])
            self.assertTrue(all(value['lossless'] for value in result['splits'].values()))
            self.assertEqual(result['special_tokens'], record['special_tokens'])
            self.assertFalse(result['pretraining_allowed']); self.assertFalse(result['release_approved'])
            self.assertEqual(result['dataset_manifest_sha256'], digest(dataset))
            self.assertEqual(result['revision'], digest({k:v for k,v in result.items() if k!='revision'}))
            importlib.reload(compatibility)
            self.assertEqual(result, compatibility.review(root, record['id'], record, {'vocab_size':record['vocabulary_size']}))
            self.assertEqual(before, {str(p.relative_to(root)):p.read_bytes() for p in Path(root).rglob('*') if p.is_file()})
            mismatch = compatibility.review(root, record['id'], record, {'vocab_size':16})
            self.assertIn('vocabulary_mismatch', [b['code'] for b in mismatch['compatibility_blockers']])

    def test_oversized_vocabulary_and_lossy_heldouts_are_distinct_blockers(self):
        with TemporaryDirectory() as root:
            _, large = self.prepare(root, multilingual=True, algorithm='byte_level_bpe', vocabulary_cap=320)
            report = compatibility.review(root, large['id'], large, {'vocab_size':256})
            self.assertEqual({b['code'] for b in report['compatibility_blockers']}, {'vocabulary_mismatch'})
            self.assertTrue(all(s['lossless'] for s in report['splits'].values()))
            matching=compatibility.review(root,large['id'],large,{'vocab_size':large['vocabulary_size']})
            self.assertTrue(matching['vocabulary_and_lossless_checks_passed'])
            self.assertEqual(matching['recipe']['architecture_version'],2)
            _, lossy = self.prepare(root, multilingual=True, algorithm='unigram',
                                    special_tokens={'unk':'<UNK>'}, unknown_policy='replace')
            report = compatibility.review(root, lossy['id'], lossy, {'vocab_size':lossy['vocabulary_size']})
            self.assertFalse(report['vocabulary_and_lossless_checks_passed'])
            self.assertEqual({b['code'] for b in report['compatibility_blockers']}, {'lossless_encoding_required'})
            self.assertTrue(report['splits']['train']['lossless'])
            self.assertGreater(sum(s['uncovered_characters'] for s in report['splits'].values()), 0)

    def test_stale_reviews_invalid_dimensions_changed_source_and_wrong_training_provenance(self):
        with TemporaryDirectory() as root:
            dataset, record = self.prepare(root)
            for config in ({}, {'vocab_size':True}, {'vocab_size':3}, {'vocab_size':513}, {'vocab_size':32,'width':8}):
                with self.assertRaises(ValueError): compatibility.review(root, record['id'], record, config)
            with self.assertRaisesRegex(ValueError, 'review changed'):
                compatibility.review(root, record['id'], {}, {'vocab_size':32})
            with patch.object(datasets, 'read', return_value={**dataset, 'dataset_sha256':'0'*64}):
                with self.assertRaisesRegex(ValueError, 'dataset revision changed'):
                    compatibility.review(root, record['id'], record, {'vocab_size':32})
            folder = Path(root)/'decoder-tokenizer-experiments'/record['id']
            artifact = json.loads((folder/'tokenizer.json').read_text())
            artifact['training_documents_sha256'] = '0'*64
            (folder/'tokenizer.json').write_text(json.dumps(artifact))
            with self.assertRaises(ValueError): compatibility.review(root, record['id'], record, {'vocab_size':32})
            forged = {**record, 'training_documents_sha256':'0'*64, 'tokenizer_sha256':digest(artifact),
                      'files':{'tokenizer.json':file_digest(folder/'tokenizer.json')}}
            forged['revision'] = digest({k:v for k,v in forged.items() if k!='revision'})
            (folder/'manifest.json').write_text(json.dumps(forged))
            with self.assertRaisesRegex(ValueError, 'training provenance'):
                compatibility.review(root, record['id'], forged, {'vocab_size':32})

    def test_invalid_emitted_ids_fail_without_decoding_or_initializing_a_model(self):
        with TemporaryDirectory() as root:
            _, record = self.prepare(root)
            size = record['vocabulary_size']
            with patch.object(CharacterBPE, 'encode', return_value=[size]):
                report = compatibility.review(root, record['id'], record, {'vocab_size':size})
            self.assertFalse(report['vocabulary_and_lossless_checks_passed'])
            self.assertEqual(sum(s['invalid_id_documents'] for s in report['splits'].values()), 5)

    def test_recomputed_checks_ignore_claimed_comparison_and_recheck_concurrent_changes(self):
        with TemporaryDirectory() as root:
            _, record = self.prepare(root, multilingual=True)
            original_read = experiments.read
            claimed = {**record, 'comparison':{split:{'round_trip_verified':True} for split in ('train','validation','test')}}
            with patch.object(experiments, 'read', return_value=claimed):
                report = compatibility.review(root, record['id'], claimed, {'vocab_size':record['vocabulary_size']})
            self.assertFalse(report['vocabulary_and_lossless_checks_passed'])
            with patch.object(experiments, 'read', side_effect=[record, {**record, 'revision':'0'*64}]):
                with self.assertRaisesRegex(ValueError, 'changed during'):
                    compatibility.review(root, record['id'], record, {'vocab_size':record['vocabulary_size']})
            self.assertEqual(original_read(root, record['id']), record)
