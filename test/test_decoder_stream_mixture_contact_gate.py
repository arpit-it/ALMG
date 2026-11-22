from copy import deepcopy
import unittest
from unittest.mock import patch

import test_decoder_stream_mixture_lexical_gate as helpers
from backend import decoder_stream_mixture_contact_gate as gate, decoder_stream_audits as audits
from backend.run_manifest import digest


class MixtureContactGateTests(unittest.TestCase):
    def setUp(self):
        self.fixture = helpers.MixtureLexicalGateTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.state = self.fixture.state
        self.lexical = self.fixture.reviewed
        self.selections = self.audit_sources(self.fixture.left, self.fixture.right)
        self.reviewed = gate.review(self.root, self.state['id'], True, self.lexical, self.selections)

    def audit_sources(self, *sources):
        result = []
        for source in sources:
            value = audits.begin(self.root, source['id'], True)
            while value['status'] != 'complete':
                value = audits.step(self.root, value['id'], True)
            result.append({'index_id': source['id'], 'audit_id': value['id']})
        return result

    def test_all_pages_preserve_sources_and_do_not_clear_hygiene_or_training(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        cursor = None
        total = 0
        while True:
            page = gate.batch(self.root, self.state['id'], True, self.reviewed, cursor, 16)
            self.assertTrue(page['contact_pattern_gate_passed'])
            self.assertFalse(page['hygiene_gate_applied'])
            for flag in gate.lexical.inputs.sessions.FLAGS:
                self.assertIs(page[flag], False)
            total += page['real_target_tokens']
            cursor = page['next_cursor']
            if cursor is None: break
        self.assertEqual(total, self.fixture.input_review['total_target_tokens'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_contact_in_heldout_record_blocks_before_emission(self):
        rows = self.fixture.documents('contact')
        for nonce in range(10000):
            text = ' '.join(f'private_{nonce}_{word}' for word in range(20)) + ' audit@example.invalid'
            if int(digest(text)[:8], 16) % 100 >= 90: break
        else: self.fail('No held-out fixture')
        rows.append(text)
        source = self.fixture.factory.source('contact', rows)
        state, inputs, evidence = self.fixture.fixture(self.fixture.left, source)
        lexical = gate.lexical.review(self.root, state['id'], True, inputs, evidence)
        selections = self.audit_sources(self.fixture.left, source)
        report = audits.read(self.root, selections[1]['audit_id'])
        self.assertEqual(report['privacy_records'], 1)
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError, 'Known source contact-pattern'):
            gate.review(self.root, state['id'], True, lexical, selections)
        with patch.object(gate.lexical, 'batch') as emit:
            with self.assertRaisesRegex(ValueError, 'Known source contact-pattern'):
                gate.batch(self.root, state['id'], True, {'lexical_review': lexical, 'contact_audits': selections})
            emit.assert_not_called()
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_partial_missing_duplicate_and_foreign_audits_reject(self):
        partial = audits.begin(self.root, self.fixture.left['id'], True)
        for selections in ([], [self.selections[0]] * 2,
                           [dict(index_id='foreign', audit_id=partial['id']), self.selections[1]],
                           [dict(index_id=self.fixture.left['id'], audit_id=partial['id']), self.selections[1]]):
            with self.subTest(selections=selections), self.assertRaises(ValueError):
                gate.review(self.root, self.state['id'], True, self.lexical, selections)

    def test_method_producer_source_and_invalid_counters_reject(self):
        original = audits.read
        changes = [('implementation_sha256', 'changed'), ('source_sha256', 'changed'),
                   ('processed_records', True), ('privacy_records', -1),
                   ('privacy_matches', True), ('privacy_match_occurrences', 1)]
        for key, value in changes:
            def changed(*args):
                report = deepcopy(original(*args)); report[key] = value; return report
            with self.subTest(key=key), patch.object(audits, 'read', side_effect=changed), self.assertRaises(ValueError):
                gate.review(self.root, self.state['id'], True, self.lexical, self.selections)
        def method(*args):
            report = deepcopy(original(*args)); report['method']['privacy'] = 'unknown'; return report
        with patch.object(audits, 'read', side_effect=method), self.assertRaises(ValueError):
            gate.review(self.root, self.state['id'], True, self.lexical, self.selections)

    def test_consent_stale_review_and_cursor_reject(self):
        with patch.object(gate, '_build') as inspect:
            with self.assertRaises(ValueError): gate.review(self.root, self.state['id'], False, self.lexical, self.selections)
            with self.assertRaises(ValueError): gate.batch(self.root, self.state['id'], False, self.reviewed)
            inspect.assert_not_called()
        page = gate.batch(self.root, self.state['id'], True, self.reviewed, batch_size=1)
        with self.assertRaises(ValueError):
            gate.batch(self.root, self.state['id'], True, self.reviewed, {**page['next_cursor'], 'contact_gate_revision': 'changed'})
        changed = deepcopy(self.reviewed); changed['revision'] = 'changed'
        with self.assertRaises(ValueError): gate.batch(self.root, self.state['id'], True, changed)
        self.assertEqual(self.reviewed, gate.review(self.root, self.state['id'], True, self.lexical, list(reversed(self.selections))))

    def test_changed_audit_during_read_discards_page(self):
        path = audits._folder(self.root, self.selections[0]['audit_id']) / 'manifest.json'
        original = path.read_bytes()
        emit = gate.lexical.batch
        def changed(*args, **kwargs):
            result = emit(*args, **kwargs); path.write_text('{}'); return result
        try:
            with patch.object(gate.lexical, 'batch', side_effect=changed), self.assertRaises(ValueError):
                gate.batch(self.root, self.state['id'], True, self.reviewed)
        finally: path.write_bytes(original)
