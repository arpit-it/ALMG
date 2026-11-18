import unittest
from backend import studio


class WordVariantsTest(unittest.TestCase):
    def test_single_word_variants_stay_together_without_automatic_exclusion(self):
        rows = [
            {'text': 'Please send the latest orchard fruit invoice before Monday morning', 'label': 'billing', 'group': 'A'},
            {'text': 'Please send the latest orchard fruit invoice before Tuesday morning', 'label': 'shipping', 'group': 'B'},
            {'text': 'A telescope records distant stars during clear summer nights', 'label': 'shipping', 'group': 'C'},
            {'text': 'Other source related content', 'label': 'billing', 'group': 'A'},
        ]
        variants = studio.classifier_word_variant_groups(rows)
        self.assertIsNotNone(variants[0])
        self.assertEqual(variants[0], variants[1])
        self.assertIsNone(variants[2])
        groups = studio.classifier_split_groups(rows)
        self.assertEqual(groups[0], groups[1])
        self.assertEqual(groups[1], groups[3])
        self.assertNotEqual(groups[0], groups[2])
        self.assertEqual(studio.usable_classifier_indices(rows), [0, 1, 2, 3])

    def test_exact_variants_short_phrases_and_two_word_changes_are_not_counted(self):
        def row(text): return {'text': text}
        self.assertEqual(studio.classifier_word_variant_groups([row('Invoice now'), row('Invoice later')]), [None, None])
        text = 'Please send the latest orchard fruit invoice before Monday morning'
        self.assertEqual(studio.classifier_word_variant_groups([row(text), row(text.upper())]), [None, None])
        self.assertEqual(studio.classifier_word_variant_groups([row(text), row(text.replace('Monday morning', 'Tuesday evening'))]), [None, None])
