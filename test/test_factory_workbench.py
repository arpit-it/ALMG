"""Offline main workbench routing, consent and durable factory linkage."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from backend import studio, decoder_trials, recipe_contracts


class FactoryWorkbenchTest(unittest.TestCase):
    def proposal(self, system, payload):
        if 'registered_recipes' in payload:
            return {'recipe': 'decoder_from_scratch', 'approach': 'from_scratch', 'reason': 'Bounded fresh-weight trial.'}
        self.assertIn('decoder_from_scratch', payload['recipes'])
        return {'recipe': 'decoder_from_scratch', 'reason': 'A decoder produces next tokens.'}

    def request(self, job, data):
        body = json.dumps(data).encode()
        handler = Mock(path=f"/jobs/{job['id']}/approve-decoder-trial",
                       headers={'Content-Length': str(len(body))}, rfile=io.BytesIO(body))
        studio.Handler.do_POST(handler)
        return handler

    def test_automatic_routing_waits_for_exact_consent_then_links_one_durable_trial(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(studio, 'ROOT', Path(temporary)), \
             patch.object(studio, 'JOBS', {}), patch.object(studio, 'ask', side_effect=self.proposal), \
             patch.object(studio.inference.WORKER, 'submit') as submit, \
             patch.object(decoder_trials, '_ACTIVE', set()), patch.object(decoder_trials, '_CANCEL', {}):
            job = {'id': 'a'*32, 'prompt': 'Create a language model from fresh weights', 'recipe': None}
            studio.JOBS[job['id']] = job
            studio.Handler.make_plan(job)
            self.assertEqual(job['status'], 'factory_review')
            self.assertNotIn('plan', job)
            self.assertEqual(decoder_trials.list_trials(studio.ROOT), [])
            for data in ({'confirmed': False, 'proposal_revision': job['decoder_proposal']['revision']},
                         {'confirmed': True, 'proposal_revision': 'stale'}):
                self.assertEqual(self.request(job, data).respond.call_args.args[1], 400)
            submit.assert_not_called()
            data = {'confirmed': True, 'proposal_revision': job['decoder_proposal']['revision']}
            self.assertEqual(self.request(job, data).respond.call_args.args[1], 202)
            self.assertEqual(job['status'], 'factory_trial')
            record = decoder_trials.read(studio.ROOT, job['decoder_trial_id'])
            self.assertEqual(record['proposal'], job['decoder_proposal'])
            self.assertEqual(self.request(job, data).respond.call_args.args[1], 400)
            submit.assert_called_once()
            decoder_trials._ACTIVE.clear()
            studio.JOBS.clear()
            studio.restore_jobs()
            self.assertEqual(studio.JOBS[job['id']]['decoder_trial_id'], record['id'])
            self.assertEqual(studio.JOBS[job['id']]['status'], 'factory_trial')
            self.assertEqual(decoder_trials.read(studio.ROOT, record['id'])['status'], 'interrupted')

    def test_review_survives_restart_and_unavailable_approach_cannot_execute(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(studio, 'ROOT', Path(temporary)), \
             patch.object(studio, 'JOBS', {}), patch.object(studio, 'ask', side_effect=self.proposal), \
             patch.object(studio.inference.WORKER, 'submit') as submit:
            job = {'id': 'b'*32, 'prompt': 'Create a language model', 'recipe': None}
            studio.Handler.make_plan(job)
            original = dict(job)
            studio.restore_jobs()
            self.assertEqual(studio.JOBS[job['id']], original)
            with patch.object(studio, 'ask', return_value={'recipe': 'decoder_from_scratch', 'approach': 'retrieval', 'reason': 'Retrieval is a better fit.'}):
                proposal = decoder_trials.propose(studio.ROOT, job['prompt'], studio.ask)
            job['decoder_proposal'] = proposal
            studio.JOBS[job['id']] = job
            self.assertEqual(self.request(job, {'confirmed': True, 'proposal_revision': proposal['revision']}).respond.call_args.args[1], 400)
            submit.assert_not_called()
            self.assertEqual(job['status'], 'factory_review')
