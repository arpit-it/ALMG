"""Offline main workbench routing, consent and durable factory linkage."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from backend import studio, decoder_trials, recipe_contracts, decoder_datasets


class FactoryWorkbenchTest(unittest.TestCase):
    def setUp(self):
        hardware={'system':'Darwin','machine':'arm64','metal_available':True,'mlx_version':'fixture',
                  'metal_device':{'device_name':'Fixture GPU','max_recommended_working_set_size':8*1024**3},
                  'available_memory_bytes':8*1024**3,'free_disk_bytes':8*1024**3,'errors':[]}
        probe=patch.object(studio.decoder_trial_feasibility.architecture,'hardware',return_value=hardware)
        probe.start();self.addCleanup(probe.stop)

    def proposal(self, system, payload):
        if 'registered_recipes' in payload:
            return {'recipe': 'decoder_from_scratch', 'approach': 'from_scratch', 'reason': 'Bounded fresh-weight trial.'}
        self.assertIn('decoder_from_scratch', payload['recipes'])
        return {'recipe': 'decoder_from_scratch', 'reason': 'A decoder produces next tokens.'}

    def request(self, job, data, action="approve-decoder-trial"):
        body = json.dumps(data).encode()
        handler = Mock(path=f"/jobs/{job['id']}/{action}",
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
            self.assertFalse(record['factory_hardware_review']['reviewed_before_approval'])
            self.assertFalse(record['generated_trial_hardware']['reviewed_before_approval'])
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

    def test_selected_dataset_requires_review_and_new_proposal_before_training(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(studio, 'ROOT', Path(temporary)), \
             patch.object(studio, 'JOBS', {}), patch.object(studio, 'ask', side_effect=self.proposal), \
             patch.object(studio.inference.WORKER, 'submit') as submit, \
             patch.object(decoder_trials, '_ACTIVE', set()), patch.object(decoder_trials, '_CANCEL', {}):
            job = {'id': 'c'*32, 'prompt': 'Create a local language model', 'recipe': None}
            studio.JOBS[job['id']] = job
            studio.Handler.make_plan(job)
            old_revision = job['decoder_proposal']['revision']
            words = ['amber', 'birch', 'cedar', 'dune']
            docs = [{'name': f'doc-{i}', 'text': ' '.join(words[(i+j)%4] for j in range(8+i))} for i in range(6)]
            dataset = decoder_datasets.prepare(studio.ROOT, docs, True)
            for selected, confirmed in ((dataset, False), ({**dataset, 'unique_documents': 99}, True), (None, True)):
                with patch.object(studio.threading, 'Thread') as worker:
                    response = self.request(job, {'confirmed': confirmed, 'dataset': selected}, 'plan-decoder-dataset')
                self.assertEqual(response.respond.call_args.args[1], 400)
                self.assertEqual(job['status'], 'factory_review')
                worker.assert_not_called()
            with patch.object(studio.threading, 'Thread') as worker:
                response = self.request(job, {'confirmed': True, 'dataset': dataset}, 'plan-decoder-dataset')
            self.assertEqual(response.respond.call_args.args[1], 202)
            self.assertEqual(job['status'], 'planning')
            submit.assert_not_called()
            studio.Handler.make_factory_plan(*worker.call_args.kwargs['args'])
            self.assertEqual(job['status'], 'factory_review')
            self.assertEqual(job['decoder_dataset'], dataset)
            self.assertNotEqual(job['decoder_proposal']['revision'], old_revision)
            self.assertEqual(self.request(job, {'confirmed': True, 'proposal_revision': old_revision}).respond.call_args.args[1], 400)
            submit.assert_not_called()
            self.request(job, {'confirmed': True, 'proposal_revision': job['decoder_proposal']['revision']})
            record = decoder_trials.read(studio.ROOT, job['decoder_trial_id'])
            self.assertEqual(record['dataset'], dataset)
            self.assertEqual(record['proposal']['dataset_summary']['id'], dataset['id'])
            with patch.object(decoder_trials.decoder_dataset_training, 'run', return_value={'passed': True}):
                decoder_trials.execute(studio.ROOT, record['id'])
            studio.JOBS.clear()
            studio.restore_jobs()
            self.assertEqual(studio.JOBS[job['id']]['decoder_dataset'], dataset)

    def test_failed_dataset_replanning_never_starts_training(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(studio, 'ROOT', Path(temporary)), \
             patch.object(studio, 'ask', side_effect=ValueError('Planner unavailable')), \
             patch.object(studio.inference.WORKER, 'submit') as submit:
            job = {'id': 'd'*32, 'prompt': 'Create language model', 'status': 'planning'}
            studio.Handler.make_factory_plan(job)
            self.assertEqual(job['status'], 'failed')
            self.assertIn('Planner unavailable', job['error'])
            submit.assert_not_called()

    def test_factory_feasibility_is_readonly_and_exact_review_is_retained_before_submission(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(studio,'ROOT',Path(temporary)),patch.object(studio,'JOBS',{}),patch.object(studio,'ask',side_effect=self.proposal),patch.object(studio.inference.WORKER,'submit') as submit,patch.object(decoder_trials,'_ACTIVE',set()),patch.object(decoder_trials,'_CANCEL',{}):
            job={'id':'e'*32,'prompt':'Create a local language model','recipe':None};studio.JOBS[job['id']]=job;studio.Handler.make_plan(job)
            before={p:p.read_bytes() for p in studio.ROOT.rglob('*') if p.is_file()};revision=job['decoder_proposal']['revision']
            handler=self.request(job,{'proposal_revision':revision},'decoder-feasibility');review=handler.respond.call_args.args[0]
            self.assertTrue(review['feasible']);self.assertEqual(review['factory']['job_id'],job['id']);self.assertTrue(all(p.read_bytes()==value for p,value in before.items()))
            submit.assert_not_called();self.assertEqual(job['status'],'factory_review')
            stale=json.loads(json.dumps(review));stale['factory']['proposal_revision']='changed'
            rejected=self.request(job,{'confirmed':True,'proposal_revision':revision,'reviewed_feasibility':stale})
            self.assertEqual(rejected.respond.call_args.args[1],400);submit.assert_not_called();self.assertFalse((studio.ROOT/'decoder-trials').exists())
            handler=self.request(job,{'confirmed':True,'proposal_revision':revision,'reviewed_feasibility':review})
            self.assertEqual(handler.respond.call_args.args[1],202);record=decoder_trials.read(studio.ROOT,job['decoder_trial_id'])
            self.assertEqual(record['factory_hardware_review']['approval'],review);self.assertTrue(record['factory_hardware_review']['reviewed_before_approval']);submit.assert_called_once()
