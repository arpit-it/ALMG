from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import test_decoder_stream_mixture_inputs as helpers
from backend import decoder_stream_mixture_lexical_gate as gate, decoder_stream_mixture_inputs as inputs
from backend import decoder_stream_mixtures as mixtures, decoder_stream_overlap as within
from backend import decoder_stream_mixture_near_overlap as near, decoder_stream_mixture_audits as exact, studio
from backend.run_manifest import digest


class MixtureLexicalGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.factory = helpers.MixtureInputTests(methodName='runTest');self.factory.root = self.root
        self.base = ' '.join('token' + str(i) for i in range(30))
        self.variant = ' '.join(self.base.split()[:-1] + ['replacement5'])
        self.left = self.factory.source('left', self.documents('left') + [self.base])
        self.right = self.factory.source('right', self.documents('right'))
        self.tokenizer = self.factory.fit(self.left)
        self.state, self.input_review, self.evidence = self.fixture(self.left, self.right)
        self.reviewed = gate.review(self.root, self.state['id'], True, self.input_review, self.evidence)

    def documents(self, prefix):
        rows = []
        for split, count in (('train', 3), ('validation', 2), ('test', 2)):
            for number in range(count):
                for nonce in range(1000):
                    text = ' '.join(f'{prefix}_{split}_{number}_{nonce}_{word}' for word in range(20))
                    bucket = int(digest(text)[:8], 16) % 100
                    if ('train' if bucket < 80 else 'validation' if bucket < 90 else 'test') == split:
                        rows.append(text);break
                else: raise AssertionError('Missing split fixture')
        return rows

    def fixture(self, left, right):
        state, packet = self.factory.session(left, right)
        codec = self.tokenizer if self.tokenizer['index_id'] in (left['id'], right['id']) else self.factory.fit(left)
        reviewed = self.factory.review(state, packet, codec)
        plan = mixtures.read(self.root, state['review']['mixture_id'])
        source_audits = []
        for source in (left, right):
            record = within.begin(self.root, source['id'], True)
            while record['status'] != 'complete': record = within.step(self.root, record['id'], True)
            source_audits.append({'index_id': source['id'], 'audit_id': record['id']})
        report = exact.overlap.review(self.root, plan['id'], True, plan)
        saved = exact.save(self.root, plan['id'], True, plan, report)
        record = near.begin(self.root, plan['id'], True, plan)
        while record['status'] != 'complete': record = near.step(self.root, record['id'], True)
        return state, reviewed, {'source_audits': source_audits, 'exact_audit_id': saved['id'], 'near_audit_id': record['id']}

    def test_matching_complete_audits_gate_all_input_pages_without_writes(self):
        self.assertTrue(self.reviewed['lexical_cross_split_gate_passed'])
        self.assertEqual(self.reviewed['short_record_pairs_unassessed'], 0)
        for flag in inputs.sessions.FLAGS: self.assertIs(self.reviewed[flag], False)
        before = {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        cursor = None;total = 0
        while True:
            page = gate.batch(self.root, self.state['id'], True, self.reviewed, cursor, 16)
            self.assertTrue(page['lexical_cross_split_gate_passed']);self.assertFalse(page['training_approved'])
            total += page['real_target_tokens'];cursor = page['next_cursor']
            if cursor is None: break
        self.assertEqual(total, self.input_review['total_target_tokens'])
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_cross_source_eval_contamination_blocks_before_input_emission(self):
        bad = self.factory.source('cross-bad', self.documents('crossbad') + [self.variant])
        state, reviewed, evidence = self.fixture(self.left, bad)
        self.assertEqual(near.read(self.root, evidence['near_audit_id'])['cross_split_pairs'], 1)
        before = {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        with self.assertRaisesRegex(ValueError, 'Cross-source near-duplicate split findings'):
            gate.review(self.root, state['id'], True, reviewed, evidence)
        with patch.object(inputs, 'batch') as emit:
            with self.assertRaises(ValueError): gate.batch(self.root, state['id'], True, {'input_review': reviewed, 'evidence': evidence})
            emit.assert_not_called()
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_within_source_cross_split_findings_also_block(self):
        bad = self.factory.source('within-bad', self.documents('withinbad') + [self.base, self.variant])
        state, reviewed, evidence = self.fixture(bad, self.right)
        with self.assertRaisesRegex(ValueError, 'Within-source cross-split lexical findings'):
            gate.review(self.root, state['id'], True, reviewed, evidence)

    def test_partial_wrong_source_and_unsupported_producer_or_method_reject(self):
        partial = within.begin(self.root, self.left['id'], True)
        evidence = deepcopy(self.evidence)
        next(value for value in evidence['source_audits'] if value['index_id'] == self.left['id'])['audit_id'] = partial['id']
        with self.assertRaisesRegex(ValueError, 'Complete the matching'): gate.review(self.root, self.state['id'], True, self.input_review, evidence)
        evidence = deepcopy(self.evidence);evidence['source_audits'][1] = evidence['source_audits'][0]
        with self.assertRaises(ValueError): gate.review(self.root, self.state['id'], True, self.input_review, evidence)
        with patch.object(within, '_implementation', return_value='changed'):
            with self.assertRaisesRegex(ValueError, 'producer changed'): gate.review(self.root, self.state['id'], True, self.input_review, self.evidence)
        original = within.read
        def changed(*args):
            value = deepcopy(original(*args));value['method']['threshold'] = .9;return value
        with patch.object(within, 'read', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'method does not match'): gate.review(self.root, self.state['id'], True, self.input_review, self.evidence)

    def test_consent_and_evidence_bound_cursors_reject(self):
        with patch.object(gate, '_build') as inspected:
            with self.assertRaises(ValueError): gate.review(self.root, self.state['id'], False, self.input_review, self.evidence)
            with self.assertRaises(ValueError): gate.batch(self.root, self.state['id'], False, self.reviewed)
            with self.assertRaises(ValueError): gate.batch(self.root, self.state['id'], True, self.reviewed, batch_size=True)
            inspected.assert_not_called()
        page = gate.batch(self.root, self.state['id'], True, self.reviewed, batch_size=1)
        with self.assertRaises(ValueError): gate.batch(self.root, self.state['id'], True, self.reviewed, {**page['next_cursor'], 'gate_revision': 'changed'})
        swapped = deepcopy(self.evidence);swapped['source_audits'].reverse()
        self.assertEqual(gate.review(self.root, self.state['id'], True, self.input_review, swapped), self.reviewed)

    def test_missing_evaluation_splits_reject_even_valid_candidate_inputs(self):
        only_train = self.factory.source('only-train', [self.factory.train('train-only lexical fixture with enough words ' * 3)])
        state, packet = self.factory.session(self.left, only_train)
        reviewed = self.factory.review(state, packet, self.tokenizer)
        with self.assertRaisesRegex(ValueError, 'nonempty train, validation and test'):
            gate.review(self.root, state['id'], True, reviewed, self.evidence)

    def test_changed_audit_during_batch_produces_no_valid_page(self):
        selected = self.evidence['source_audits'][0]['audit_id'];path = within._folder(self.root, selected) / 'manifest.json'
        original = path.read_bytes();emit = inputs.batch
        def changed(*args, **kwargs):
            result = emit(*args, **kwargs)
            value = json.loads(original);value['revision'] = '0' * 64;path.write_text(json.dumps(value));return result
        try:
            with patch.object(inputs, 'batch', side_effect=changed):
                with self.assertRaises(ValueError): gate.batch(self.root, self.state['id'], True, self.reviewed)
        finally: path.write_bytes(original)

    def test_app_review_and_batch_routes(self):
        for action, values in (('lexical-input-review', {'confirmed': True, 'reviewed_input': self.input_review, 'evidence': self.evidence}),
                               ('lexical-input-batch', {'confirmed': True, 'reviewed': self.reviewed, 'batch_size': 2})):
            raw = json.dumps(values).encode()
            handler = Mock(path='/decoder-stream-mixture-sessions/' + self.state['id'] + '/' + action,
                           headers={'Content-Length': str(len(raw))}, rfile=BytesIO(raw));handler.authorized.return_value = True
            with patch.object(studio, 'ROOT', self.root): studio.Handler.do_POST(handler)
            result = handler.respond.call_args.args[0];self.assertNotIn('error', result)
            if action == 'lexical-input-batch': self.assertEqual(result['rows'], 2)
