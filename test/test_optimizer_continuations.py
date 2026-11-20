from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_optimizer_continuations as continuations,decoder_optimizer_fixture as fixture,decoder_architecture_plans as plans,decoder_architecture_initializations as initializations


class OptimizerContinuationTests(unittest.TestCase):
    def source(self,root,settings):
        plan=plans.save(root,True,plans.review(dict(plans.DEFAULT)));initialized=initializations.run(root,plan['id'],True,plan)
        approved=fixture.review(root,plan['id'],initialized,settings)
        return fixture.run(root,plan['id'],True,initialized,settings,approved)

    def test_no_consent_or_invalid_source_never_creates_output_files(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            with self.assertRaises(ValueError):continuations.run(root,'a'*32,False,None)
            with self.assertRaises(ValueError):continuations.review(root,'../outside')
            self.assertEqual(list(root.rglob('*')),[])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires independent Metal optimizer continuation')
    def test_legacy_sgd_and_mixed_adamw_finish_original_budget_without_resetting_state(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            for optimizer in ('sgd','adamw'):
                c=dict(fixture.DEFAULT) if optimizer=='sgd' else {**fixture.DEFAULT,'schema_version':5,'optimizer':'adamw','weight_decay':.01,'gradient_accumulation_steps':2,'compute_precision':'mixed_float16','loss_scale':128.,'batch_size':2,'sequence_length':8,'steps':20}
                parent=self.source(root,c);before={p:fixture.file_digest(p) for p in root.rglob('*') if p.is_file()};approved=continuations.review(root,parent['id']);midpoint=c['steps']//2
                self.assertEqual(approved['estimates']['optimizer_updates'],c['steps']-midpoint);self.assertIsNone(approved['estimates']['optimizer_work_estimate'])
                changed=deepcopy(approved);changed['source']['optimizer_sha256']='changed';changed['revision']=fixture.digest({k:v for k,v in changed.items() if k!='revision'})
                with self.assertRaises(ValueError):continuations.run(root,parent['id'],True,changed)
                profile={**approved['hardware'],'available_memory_bytes':1}
                with patch.object(fixture.hardware,'hardware',return_value=profile):
                    blocked=continuations.review(root,parent['id']);self.assertFalse(blocked['feasible'])
                    with self.assertRaises(ValueError):continuations.run(root,parent['id'],True,blocked)
                record=continuations.run(root,parent['id'],True,approved)
                self.assertEqual(record['restored_steps'],midpoint);self.assertEqual(record['completed_steps'],c['steps']);self.assertEqual(record['scheduler_completed_steps'],c['steps'])
                self.assertEqual([entry['step'] for entry in record['step_log']],list(range(midpoint+1,c['steps']+1)))
                self.assertEqual(record['step_log'][0]['learning_rate'],fixture.learning_rate(c,midpoint))
                self.assertEqual(record['source_final_parameter_max_error'],0.);self.assertEqual(record['generated_token_ids'],parent['generated_token_ids'])
                self.assertLess(record['final_train_loss'],record['initial_train_loss']);self.assertFalse(record['release_approved']);self.assertFalse(record['source_modified'])
                self.assertEqual(continuations.read(root,record['id']),record);self.assertEqual(continuations.history(root,parent['id']),[record])
                self.assertTrue(all(fixture.file_digest(p)==sha for p,sha in before.items()))
                state=json.loads((continuations._folder(root,record['id'])/'optimizer.json').read_text());self.assertEqual(state['step'],c['steps'])
                self.assertEqual(bool(state['m']),optimizer=='adamw')

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real persisted optimizer checkpoint')
    def test_changed_checkpoint_and_continued_state_are_rejected(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);parent=self.source(root,dict(fixture.DEFAULT));approved=continuations.review(root,parent['id']);record=continuations.run(root,parent['id'],True,approved)
            state=continuations._folder(root,record['id'])/'optimizer.json';state.write_text('{}')
            with self.assertRaises(ValueError):continuations.read(root,record['id'])
            self.assertEqual(continuations.history(root,parent['id']),[])
            checkpoint=fixture._folder(root,parent['id'])/'step-5'/'optimizer.json';checkpoint.write_text('{}')
            before={p:fixture.file_digest(p) for p in root.rglob('*') if p.is_file()}
            with self.assertRaises(ValueError):continuations.run(root,parent['id'],True,approved)
            self.assertEqual(before,{p:fixture.file_digest(p) for p in root.rglob('*') if p.is_file()})
