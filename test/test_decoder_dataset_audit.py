import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_datasets as datasets


class DatasetAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        words = [f'w{i}' for i in range(40)]
        self.manifest = datasets.prepare(self.root, [
            {'name': f'near-{i}.txt', 'text': ' '.join(words + [f'unique{i}'])}
            for i in range(6)], True)
        self.dataset_id = self.manifest['id']

    def test_overlap_provenance_and_immutable_repeat(self):
        folder = self.root / 'decoder-datasets' / self.dataset_id
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        report = datasets.audit(self.root, self.dataset_id, True)
        self.assertEqual((report['near_duplicate_pairs'], report['cross_split_pairs']), (15, 9))
        for finding in report['findings']:
            self.assertEqual(len(finding['records']), 2)
            for record in finding['records']:
                source = next(s for s in self.manifest['sources'] if s['name'] == record['name'])
                self.assertEqual(record['source_sha256'], source['source_sha256'])
                self.assertEqual(record['split'], source['split'])
            self.assertEqual(finding['cross_split'], len({r['split'] for r in finding['records']}) > 1)
        self.assertEqual(datasets.audit(self.root, self.dataset_id, True), report)
        self.assertEqual(datasets.list_audits(self.root, self.dataset_id), [report])
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
        self.assertEqual(set(p.name for p in self.root.iterdir()), {'decoder-datasets', 'decoder-dataset-audits'})
        self.assertEqual(len(list((self.root / 'decoder-dataset-audits' / self.dataset_id).iterdir())), 1)

    def test_unrelated_and_short_documents(self):
        manifest = datasets.prepare(self.root, [
            {'name': 'short', 'text': 'small sample'},
            {'name': 'a', 'text': ' '.join(f'a{i}' for i in range(30))},
            {'name': 'b', 'text': ' '.join(f'b{i}' for i in range(30))}], True)
        report = datasets.audit(self.root, manifest['id'], True)
        self.assertEqual(report['near_duplicate_pairs'], 0)
        self.assertEqual([f['kind'] for f in report['findings']], ['short_document'])
        self.assertEqual(report['findings'][0]['record']['name'], 'short')

    def test_privacy_locations_preserve_provenance_without_copying_contact_values(self):
        documents = [
            {'name': 'contacts.txt', 'text': '\ufeffcafé  contact alice@example.test or +44 20 7946 0958 today'},
            {'name': 'domestic.txt', 'text': 'Call (415) 555-0123 for this fictional local fixture.'},
            {'name': 'control.txt', 'text': 'Date 2026-11-19; version 1.2.3; identifier 1234567; word at example dot test.'},
        ]
        manifest = datasets.prepare(self.root, documents, True, 'utf8_bytes')
        folder = self.root / 'decoder-datasets' / manifest['id']
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        report = datasets.audit(self.root, manifest['id'], True)
        self.assertEqual(report['audit_version'], 3)
        self.assertEqual(report['privacy_matches'], 3)
        findings = [f for f in report['findings'] if f['kind'] == 'potential_personal_information']
        self.assertEqual(sorted(f['category'] for f in findings), ['email_address', 'phone_number', 'phone_number'])
        rows = {row['name']: row for row in map(json.loads, (folder / 'documents.jsonl').read_text().splitlines())}
        detected = []
        for finding in findings:
            row = rows[finding['record']['name']]
            self.assertEqual(finding['record']['source_sha256'], row['source_sha256'])
            self.assertEqual(finding['record']['split'], row['split'])
            detected.append(row['text'][finding['normalized_character_start']:finding['normalized_character_end']])
        self.assertEqual(set(detected), {'alice@example.test', '+44 20 7946 0958', '(415) 555-0123'})
        serialized = json.dumps(report)
        for value in detected:
            self.assertNotIn(value, serialized)
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
        self.assertEqual(datasets.audit(self.root, manifest['id'], True), report)
        self.assertEqual(datasets.list_audits(self.root, manifest['id']), [report])

    def test_legacy_saved_audit_remains_readable_alongside_privacy_revision(self):
        current = datasets.audit(self.root, self.dataset_id, True)
        legacy = dict(current, audit_version=1)
        for key in ('revision', 'privacy_matches', 'privacy_method', 'token_distribution'):
            legacy.pop(key)
        legacy['revision'] = datasets.digest(legacy)
        path = self.root / 'decoder-dataset-audits' / self.dataset_id / (legacy['revision'] + '.json')
        path.write_text(json.dumps(legacy))
        saved = datasets.list_audits(self.root, self.dataset_id)
        self.assertEqual({row['audit_version'] for row in saved}, {1, 3})
        self.assertEqual(json.loads(path.read_text()), legacy)

    def test_word_token_distribution_counts_unknowns_without_refitting(self):
        report = datasets.audit(self.root, self.dataset_id, True)
        distribution = report['token_distribution']
        self.assertTrue(distribution['available'])
        self.assertEqual(distribution['tokenizer_sha256'], self.manifest['tokenizer']['sha256'])
        overall = distribution['overall']
        self.assertEqual((overall['token_count'], overall['known_tokens'], overall['unknown_tokens']), (246, 244, 2))
        self.assertEqual(overall['document_tokens'], {'minimum': 41, 'maximum': 41, 'mean': 41.0, 'median': 41.0})
        for part, documents in self.manifest['splits'].items():
            summary = distribution['splits'][part]
            self.assertEqual(summary['token_count'], 41 * documents)
            self.assertEqual(summary['unknown_tokens'], 0 if part == 'train' else 1)
        self.assertGreater(overall['entropy_bits'], 0)
        self.assertEqual(len(overall['top_token_ids']), 20)
        self.assertNotIn('unique0', json.dumps(distribution))

    def test_byte_distribution_counts_multibyte_text_and_preserves_saved_tokenizer(self):
        parent = self.privacy_dataset()
        folder = self.root / 'decoder-datasets' / parent['id']
        before = (folder / 'tokenizer.json').read_bytes()
        rows = list(map(json.loads, (folder / 'documents.jsonl').read_text().splitlines()))
        report = datasets.audit(self.root, parent['id'], True)
        distribution = report['token_distribution']
        counts = [len(row['text'].encode('utf-8')) for row in rows]
        self.assertEqual(distribution['overall']['token_count'], sum(counts))
        self.assertEqual(distribution['overall']['unknown_tokens'], 0)
        self.assertEqual(distribution['overall']['known_token_coverage'], 1.0)
        self.assertGreater(sum(counts), sum(len(row['text']) for row in rows))
        self.assertEqual(before, (folder / 'tokenizer.json').read_bytes())
        self.assertEqual(sum(s['token_count'] for s in distribution['splits'].values()), sum(counts))

    def test_token_distribution_unavailable_is_explicit_and_legacy_v2_survives(self):
        dataset = datasets.prepare(self.root, [{'name':str(i),'text':f'word{i}'} for i in range(3)], True)
        report = datasets.audit(self.root, dataset['id'], True)
        self.assertFalse(report['token_distribution']['available'])
        legacy = dict(report, audit_version=2)
        for key in ('revision', 'token_distribution'):
            legacy.pop(key)
        legacy['revision'] = datasets.digest(legacy)
        path = self.root / 'decoder-dataset-audits' / dataset['id'] / (legacy['revision'] + '.json')
        path.write_text(json.dumps(legacy))
        self.assertEqual({r['audit_version'] for r in datasets.list_audits(self.root, dataset['id'])}, {2,3})

    def privacy_dataset(self):
        return datasets.prepare(self.root, [
            {'name': 'contacts.txt', 'text': 'café contact alice@example.test or +44 20 7946 0958 today'},
            {'name': 'domestic.txt', 'text': 'Call (415) 555-0123 for this fictional local fixture.'},
            {'name': 'control.txt', 'text': 'Date 2026-11-19; version 1.2.3; unrelated local control.'},
        ], True, 'utf8_bytes')

    def test_redacted_version_binds_review_and_preserves_original_lineage(self):
        parent = self.privacy_dataset()
        folder = self.root / 'decoder-datasets' / parent['id']
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        audit = datasets.audit(self.root, parent['id'], True)
        child = datasets.redact(self.root, parent['id'], True, audit['revision'])
        self.assertNotEqual(child['id'], parent['id'])
        self.assertEqual(datasets.read(self.root, child['id']), child)
        self.assertEqual(child['status'], 'prepared_for_review')
        self.assertEqual(child['tokenizer']['format'], parent['tokenizer']['format'])
        derivation = child['derivation']
        self.assertEqual(derivation['parent_dataset_id'], parent['id'])
        self.assertEqual(derivation['parent_manifest_sha256'], datasets.digest(parent))
        self.assertEqual(derivation['audit_revision'], audit['revision'])
        self.assertEqual(sum(row['replacements'] for row in derivation['sources']), 3)
        self.assertEqual(sorted(source['source_sha256'] for row in derivation['sources'] for source in row['parent_sources']),
                         sorted(source['source_sha256'] for source in parent['sources']))
        text = (self.root / 'decoder-datasets' / child['id'] / 'documents.jsonl').read_text()
        for contact in ('alice@example.test', '+44 20 7946 0958', '(415) 555-0123'):
            self.assertNotIn(contact, text)
        self.assertEqual(text.count('[CONTACT_REDACTED]'), 3)
        self.assertEqual(datasets.quality_report(self.root, child['id'])['privacy_matches'], 0)
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
        self.assertFalse((self.root / 'decoder-trials').exists())

    def test_redaction_requires_consent_current_audit_and_contact_findings(self):
        parent = self.privacy_dataset()
        audit = datasets.quality_report(self.root, parent['id'])
        before = set((self.root / 'decoder-datasets').iterdir())
        for confirmed, revision in ((False, audit['revision']), (1, audit['revision']), (True, 'stale'), (True, None)):
            with self.assertRaises(ValueError):
                datasets.redact(self.root, parent['id'], confirmed, revision)
        clean_audit = datasets.quality_report(self.root, self.dataset_id)
        with self.assertRaisesRegex(ValueError, 'No detected contact'):
            datasets.redact(self.root, self.dataset_id, True, clean_audit['revision'])
        self.assertEqual(before, set((self.root / 'decoder-datasets').iterdir()))

    def test_redaction_collapse_fails_without_publishing_partial_dataset(self):
        parent = datasets.prepare(self.root, [
            {'name': str(i), 'text': f'Contact person{i}@example.test'} for i in range(3)
        ], True, 'utf8_bytes')
        report = datasets.quality_report(self.root, parent['id'])
        before = set((self.root / 'decoder-datasets').iterdir())
        with self.assertRaisesRegex(ValueError, 'three distinct documents'):
            datasets.redact(self.root, parent['id'], True, report['revision'])
        self.assertEqual(before, set((self.root / 'decoder-datasets').iterdir()))
        self.assertFalse(list((self.root / 'decoder-datasets').glob('.prepare-*')))
        self.assertEqual(datasets.read(self.root, parent['id']), parent)

    def test_consent_and_corrupt_dataset_do_not_publish(self):
        for consent in (False, None, 1):
            with self.assertRaises(ValueError):
                datasets.audit(self.root, self.dataset_id, consent)
        (self.root / 'decoder-datasets' / self.dataset_id / 'documents.jsonl').write_text('{}')
        with self.assertRaises(ValueError):
            datasets.audit(self.root, self.dataset_id, True)
        self.assertFalse((self.root / 'decoder-dataset-audits').exists())

    def test_tampered_audit_is_not_reused(self):
        report = datasets.audit(self.root, self.dataset_id, True)
        path = self.root / 'decoder-dataset-audits' / self.dataset_id / (report['revision'] + '.json')
        report['cross_split_pairs'] = 0
        path.write_text(json.dumps(report))
        self.assertEqual(datasets.list_audits(self.root, self.dataset_id), [])
        with self.assertRaises(ValueError):
            datasets.audit(self.root, self.dataset_id, True)


if __name__ == '__main__':
    unittest.main()
