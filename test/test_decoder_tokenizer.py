import json
import unittest
from backend.decoder_tokenizer import Tokenizer


class DecoderTokenizerTest(unittest.TestCase):
    def test_training_only_vocabulary_is_deterministic_and_held_out_words_do_not_refit(self):
        training = ['amber birch cedar dune', 'dune cedar birch amber']
        first = Tokenizer.fit(training)
        second = Tokenizer.fit(list(reversed(training)))
        self.assertEqual(first.fingerprint(), second.fingerprint())
        self.assertEqual(first.encode('dune amber'), [3, 0])
        before = first.fingerprint()
        with self.assertRaisesRegex(ValueError, 'outside the training vocabulary'):
            first.encode('held-out-only')
        self.assertEqual(first.fingerprint(), before)
        copied = first.vocabulary
        copied.clear()
        self.assertEqual(len(first.vocabulary), 4)

    def test_unicode_and_whitespace_roundtrip_and_artifact_restore(self):
        tokenizer = Tokenizer.fit(['café birch cedar dune'])
        self.assertEqual(tokenizer.decode(tokenizer.encode('cafe\u0301\t birch\n cedar dune')), 'café birch cedar dune')
        restored = Tokenizer.restore(json.loads(json.dumps(tokenizer.artifact())))
        self.assertEqual(restored.fingerprint(), tokenizer.fingerprint())
        self.assertEqual(restored.encode('café dune'), tokenizer.encode('café dune'))

    def test_bounds_and_invalid_artifact_versions_are_rejected(self):
        for documents in ([], ['one two three'], ['x' * 65], [None], [' '.join('word'+str(i) for i in range(257))]):
            with self.subTest(documents=str(documents)[:50]), self.assertRaises(ValueError):
                Tokenizer.fit(documents)
        tokenizer = Tokenizer.fit(['amber birch cedar dune'])
        for tokens in ([], [True], [-1], [4], [1.5], [0] * 4097):
            with self.assertRaises(ValueError): tokenizer.decode(tokens)
        for text in (' ', 'x' * 65537, 'amber ' * 4097):
            with self.assertRaises(ValueError): tokenizer.encode(text)
        for change in ({'schema_version': True}, {'normalization': 'NFKC'}, {'vocabulary': ['d', 'c', 'b', 'a']}, {'extra': 1}):
            with self.assertRaises(ValueError): Tokenizer.restore({**tokenizer.artifact(), **change})
