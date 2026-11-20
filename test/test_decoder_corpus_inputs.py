import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_corpus_inputs as corpus, decoder_datasets, decoder_licenses
from backend import decoder_architecture_plans as plans, decoder_architecture_initializations as initializations
from backend.run_manifest import digest


def fixture(root, vocabulary=4):
    plan = plans.save(root, True, plans.review({**plans.DEFAULT, 'vocab_size': vocabulary}))
    source = initializations.run(root, plan['id'], True, plan)
    words = ['amber', 'birch', 'cedar', 'dune']
    documents = [{'name': f'doc-{index}.txt', 'text': ' '.join(words[(index + step) % 4] for step in range(8 + index))} for index in range(6)]
    dataset = decoder_datasets.prepare(root, documents, True)
    return source, dataset


def permissions(root, dataset):
    for item in dataset['sources']:
        dataset = decoder_licenses.declare(root, dataset['id'], True, dataset, item['source_sha256'], 'user_created', 'Locally generated four-word test fixture.')
    return dataset


class CorpusInputsTest(unittest.TestCase):
    def test_permissions_vocabulary_context_and_sequence_block_without_writes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, dataset = fixture(root, 64)
            review = corpus.review(root, source['plan_id'], source, dataset, 8)
            self.assertFalse(review['compatible'])
            self.assertEqual(len(review['pending_source_permissions']), 6)
            self.assertIn('Tokenizer has 4 IDs', review['blockers'][1])
            with self.assertRaises(ValueError): corpus.save(root, source['plan_id'], True, source, dataset, 8, review)
            self.assertFalse((root / 'decoder-corpus-inputs').exists())
            for length in (True, 0, 9):
                with self.assertRaises(ValueError): corpus.review(root, source['plan_id'], source, dataset, length)
            changed = deepcopy(dataset); changed['splits']['train'] += 1
            with self.assertRaises(ValueError): corpus.review(root, source['plan_id'], source, changed, 8)

    def test_masked_windows_keep_documents_splits_and_training_weights(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary); source, dataset = fixture(root)
            dataset = permissions(root, dataset)
            review = corpus.review(root, source['plan_id'], source, dataset, 8)
            self.assertTrue(review['compatible'])
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with self.assertRaises(ValueError): corpus.save(root, source['plan_id'], False, source, dataset, 8, review)
            changed = deepcopy(review); changed['sequence_length'] = 4
            with self.assertRaises(ValueError): corpus.save(root, source['plan_id'], True, source, dataset, 8, changed)
            saved = corpus.save(root, source['plan_id'], True, source, dataset, 8, review)
            self.assertEqual(corpus.read(root, saved['id']), saved)
            self.assertEqual(corpus.history(root, source['plan_id'], source), [saved])
            folder = root / 'decoder-corpus-inputs' / saved['id']
            windows = json.loads((folder / 'windows.json').read_text())
            records = [json.loads(line) for line in (root / 'decoder-datasets' / dataset['id'] / 'documents.jsonl').read_text().splitlines()]
            tokenizer = corpus.datasets.Tokenizer.restore(json.loads((folder / 'tokenizer.json').read_text()))
            for part, rows in windows.items():
                self.assertEqual(sum(sum(row['target_mask']) for row in rows), sum(len(tokenizer.encode(row['text'])) - 1 for row in records if row['split'] == part))
                for row in rows:
                    original = next(item for item in records if item['source_sha256'] == row['document_sha256'])
                    self.assertEqual(original['split'], part)
                    count = sum(row['target_mask']); start = row['offset']; tokens = tokenizer.encode(original['text'])
                    self.assertEqual(row['inputs'][:count], tokens[start:start + count])
                    self.assertEqual(row['targets'][:count], tokens[start + 1:start + count + 1])
                    self.assertEqual(row['target_mask'], [1] * count + [0] * (8 - count))
            self.assertTrue(any(0 in row['target_mask'] for rows in windows.values() for row in rows))
            self.assertTrue(all(p.read_bytes() == content for p, content in before.items()))
            (folder / 'windows.json').write_text('{}')
            with self.assertRaises(ValueError): corpus.read(root, saved['id'])
            self.assertFalse(review['training_approved'])

    def test_training_sampling_never_repeats_evaluation_and_windows_do_not_overlap_targets(self):
        tokenizer = corpus.datasets.Tokenizer(['amber', 'birch', 'cedar', 'dune'])
        records = [{'source_sha256': part, 'group': part, 'split': part, 'text': 'amber birch cedar dune amber birch cedar dune amber birch'} for part in ('train', 'validation', 'test')]
        windows = corpus._inputs(records, tokenizer, {'mixing': {'group_weights': {part: 2 for part in ('train', 'validation', 'test')}}}, 4)
        self.assertEqual([len(windows[part]) for part in windows], [6, 3, 3])
        self.assertEqual([sum(sum(row['target_mask']) for row in windows[part]) for part in windows], [18, 9, 9])
        self.assertEqual([row['offset'] for row in windows['test']], [0, 4, 8])
        with self.assertRaises(ValueError): corpus._inputs(records * 30, tokenizer, {}, 4)
