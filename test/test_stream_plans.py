import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch,Mock
from backend import decoder_stream_plans as plans,decoder_trials
from backend.run_manifest import digest


def record():
    return {'id':'a'*32,'revision':'r','index_id':'b'*32,'index_revision':'i','tokenizer_id':'c'*32,
            'tokenizer_revision':'t','overlap_id':'d'*32,'overlap_revision':'o','total_records':401,
            'window_counts':{'train':6344,'validation':764,'test':702},'target_tokens':121308}


class StreamPlanTests(unittest.TestCase):
    def test_summary_only_plan_reload_and_explicit_acknowledgment_never_authorize_training(self):
        review=record();planner=Mock(return_value={'recipe':'decoder_from_scratch','approach':'from_scratch','reason':'Inspect the dataset before a future local trial.'})
        with TemporaryDirectory() as root,patch.object(plans.batches,'_validated',return_value=review):
            plan=plans.propose(root,review['id'],True,review,'Synthetic local planning goal',planner,lambda:{'provider':'scripted_local_fixture'})
            system,context=planner.call_args.args
            self.assertEqual(plan['planner_request']['sha256'],digest({'system':system,'data':context}))
            self.assertEqual(plan['planner_request']['recipe_catalog_sha256'],digest(context['registered_recipes']))
            self.assertEqual(plan['planner_request']['validated_result_sha256'],digest(planner.return_value))
            self.assertEqual(context['dataset_summary'],review);self.assertFalse(context['streamed_execution_available'])
            self.assertEqual(set(context),{'goal','dataset_summary','registered_recipes','streamed_execution_available'})
            self.assertFalse(plan['executable']);self.assertFalse(plan['training_approved'])
            importlib.reload(plans);self.assertEqual(plans.read(root,plan['id']),plan)
            self.assertEqual(plans.list_plans(root,review['id'],True),[plan])
            with self.assertRaises(ValueError):plans.acknowledge(root,plan['id'],False,plan)
            with self.assertRaises(ValueError):plans.acknowledge(root,plan['id'],True,dict(plan,reason='changed'))
            with patch.object(plans.batches.windows,'read',return_value=review):
                receipt=plans.acknowledge(root,plan['id'],True,plan)
                self.assertEqual(plans.acknowledge(root,plan['id'],True,plan),receipt)
            self.assertTrue(receipt['acknowledged']);self.assertFalse(receipt['training_approved']);self.assertFalse(receipt['executable'])
            with self.assertRaises(ValueError):decoder_trials.approved_proposal(root,plan['id'],plan['revision'],{})
            self.assertFalse((Path(root)/'decoder-trials').exists());self.assertEqual(plans.read(root,plan['id']),plan)

    def test_consent_invalid_choices_and_source_change_do_not_publish(self):
        review=record();planner=Mock()
        with TemporaryDirectory() as root,patch.object(plans.batches,'_validated',return_value=review):
            with self.assertRaises(ValueError):plans.propose(root,review['id'],False,review,'goal',planner)
            planner.assert_not_called()
            for result in (None,{'recipe':[]},{'recipe':'missing'},
                           {'recipe':'decoder_from_scratch','approach':'unsupported','reason':'x'},
                           {'recipe':'decoder_from_scratch','approach':'retrieval','reason':''}):
                with self.subTest(result=result),self.assertRaises(ValueError):
                    plans.propose(root,review['id'],True,review,'goal',lambda *args:result)
            with patch.object(plans.batches,'_validated',side_effect=[review,dict(review,revision='changed')]):
                with self.assertRaisesRegex(ValueError,'evidence changed'):
                    plans.propose(root,review['id'],True,review,'goal',lambda *args:{'recipe':'decoder_from_scratch','approach':'retrieval','reason':'A retrieval approach is suggested.'})
            self.assertFalse((Path(root)/'decoder-stream-plans').exists())

    def test_saved_plan_tampering_and_changed_source_block_acknowledgment(self):
        review=record()
        with TemporaryDirectory() as root,patch.object(plans.batches,'_validated',return_value=review):
            plan=plans.propose(root,review['id'],True,review,'goal',lambda *args:{'recipe':'decoder_from_scratch','approach':'retrieval','reason':'Use retrieval for this goal.'})
            with patch.object(plans.batches.windows,'read',return_value=dict(review,revision='changed')):
                with self.assertRaisesRegex(ValueError,'revision changed'):plans.acknowledge(root,plan['id'],True,plan)
            self.assertFalse((plans._folder(root,plan['id'])/'acknowledgment.json').exists())
            path=plans._folder(root,plan['id'])/'plan.json';path.write_text(json.dumps(dict(plan,executable=True)))
            with self.assertRaises(ValueError):plans.read(root,plan['id'])
            self.assertEqual(plans.list_plans(root,review['id'],True),[])


    def test_local_qwen_requires_loaded_verified_identity_and_mutated_requests_reject(self):
        review=record();result={'recipe':'decoder_from_scratch','approach':'from_scratch','reason':'A local approach plan.'}
        with TemporaryDirectory() as root,patch.object(plans.batches,'_validated',return_value=review):
            for identity in ({'provider':'local_qwen','loaded':False},
                             {'provider':'local_qwen','loaded':True,'model':'local','verified_weights_revision':'invalid'}):
                with self.assertRaisesRegex(ValueError,'loaded, verified'):
                    plans.propose(root,review['id'],True,review,'goal',lambda *args:result,lambda:identity)
            def mutate(system,context):
                context['goal']='changed';return result
            with self.assertRaisesRegex(ValueError,'evidence changed'):
                plans.propose(root,review['id'],True,review,'goal',mutate)
            self.assertFalse((Path(root)/'decoder-stream-plans').exists())
            identity={'provider':'local_qwen','loaded':True,'model':'local','verified_weights_revision':'f'*64}
            plan=plans.propose(root,review['id'],True,review,'goal',lambda *args:result,lambda:identity)
            self.assertEqual(plan['planner'],identity);self.assertFalse(plan['executable'])
            # Version-one plans created before request fingerprints remain readable.
            legacy={key:value for key,value in plan.items() if key not in ('planner_request','revision')}
            legacy['revision']=digest(legacy)
            (plans._folder(root,plan['id'])/'plan.json').write_text(json.dumps(legacy))
            self.assertEqual(plans.read(root,plan['id']),legacy)
