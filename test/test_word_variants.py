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

    def test_inserted_or_omitted_word_groups_in_either_input_order(self):
        text = 'Please send the latest orchard fruit invoice before Monday morning'
        longer = text.replace('send the', 'send only the')
        for texts in [(text, longer), (longer, text)]:
            rows = [{'text': value, 'group': str(index), 'label': 'billing'} for index, value in enumerate(texts)]
            groups = studio.classifier_word_variant_groups(rows)
            self.assertIsNotNone(groups[0])
            self.assertEqual(groups[0], groups[1])
            self.assertEqual(len(set(studio.classifier_split_groups(rows))), 1)
            self.assertEqual(studio.usable_classifier_indices(rows), [0, 1])
        self.assertEqual(studio.classifier_word_variant_groups([
            {'text': text}, {'text': text.replace('send the', 'send only this the')}]), [None, None])

    def test_word_insertions_respect_phrase_length_bounds(self):
        for length in (7, 80):
            short = ' '.join('word' + str(index) for index in range(length))
            self.assertEqual(studio.classifier_word_variant_groups([
                {'text': short}, {'text': short + ' extra'}]), [None, None])

    def test_preview_prioritizes_potential_ambiguity_without_excluding_rows(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        normal = [{'text': f'Independent telescope observation {index}', 'label': 'astronomy', 'group': str(index)} for index in range(5)]
        text = 'Please send the latest orchard fruit invoice before Monday morning'
        rows = normal + [
            {'text': text, 'label': 'fruit', 'group': 'A'},
            {'text': text.replace('send the', 'send only the'), 'label': 'astronomy', 'group': 'B'}]
        for same_label in (False, True):
            rows[-1]['label'] = 'fruit' if same_label else 'astronomy'
            job = {'id': 'ambiguity', 'recipe': 'classifier', 'plan': {'labels': ['fruit', 'astronomy']}}
            with tempfile.TemporaryDirectory() as folder, patch.object(studio, 'ROOT', Path(folder)), patch.object(studio, 'store_job'):
                studio.prepare_dataset(job, rows)
            self.assertEqual(job['status'], 'dataset_ready')
            self.assertEqual(job['ambiguous_variant_groups'], 0 if same_label else 1)
            self.assertEqual(job['conflicting_texts'], 0)
            self.assertEqual(sum(job['usable_counts'].values()), 7)
            if not same_label:
                self.assertTrue(all(row['possible_label_ambiguity'] for row in job['preview'][:2]))
                self.assertTrue(all(not row['possible_label_ambiguity'] for row in job['preview'][2:]))
            studio.TRAINING_DATA.pop('ambiguity', None)
