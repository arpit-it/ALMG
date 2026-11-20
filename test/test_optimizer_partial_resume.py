from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_optimizer_continuations as continuations,decoder_optimizer_fixture as fixture,decoder_optimizer_isolated as isolated,decoder_architecture_plans as plans,decoder_architecture_initializations as initializations


class PartialResumeTests(unittest.TestCase):
    def source(self,root,optimizer):
        plan=plans.save(root,True,plans.review(dict(plans.DEFAULT)));initialized=initializations.run(root,plan['id'],True,plan)
        c={**fixture.DEFAULT,'schema_version':5,'optimizer':optimizer,'weight_decay':.01 if optimizer=='adamw' else 0.,'compute_precision':'mixed_float16' if optimizer=='adamw' else 'float32','loss_scale':128. if optimizer=='adamw' else 1.,'gradient_accumulation_steps':2,'batch_size':2,'sequence_length':8,'steps':20}
        parent=fixture.run(root,plan['id'],True,initialized,c,fixture.review(root,plan['id'],initialized,c));token=('a' if optimizer=='sgd' else 'b')*32;update=fixture.update
        def cancel_at_eleven(*args):
            result=update(*args)
            if result[1]['step']==11:continuations.cancellation.request(root,parent['id'],token,True)
            return result
        with patch.object(fixture,'update',side_effect=cancel_at_eleven):partial=continuations.run(root,parent['id'],True,continuations.review(root,parent['id']),token)
        return parent,partial

    def test_no_consent_never_reads_or_launches_a_partial_resume(self):
        with TemporaryDirectory() as temporary,patch.object(isolated.subprocess,'Popen') as spawn:
            root=Path(temporary)
            with self.assertRaises(ValueError):continuations.run_partial(root,'a'*32,False,None)
            with self.assertRaises(ValueError):isolated.run_partial(root,'a'*32,False,None)
            self.assertEqual(list(root.rglob('*')),[]);spawn.assert_not_called()

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires private partial optimizer recovery')
    def test_sgd_and_mixed_adamw_resume_at_retained_counter_and_match_original_final_model(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            for optimizer in ('sgd','adamw'):
                parent,partial=self.source(root,optimizer);before={p:fixture.file_digest(p) for p in root.rglob('*') if p.is_file()};review=continuations.review_partial(root,partial['id'])
                self.assertEqual(review['restore_step'],11);self.assertEqual(review['estimates']['optimizer_updates'],9)
                self.assertEqual(review['resume_from']['optimizer_sha256'],partial['files']['optimizer.json'])
                changed=deepcopy(review);changed['resume_from']['optimizer_sha256']='changed';changed['revision']=fixture.digest({k:v for k,v in changed.items() if k!='revision'})
                with self.assertRaises(ValueError):isolated.run_partial(root,partial['id'],True,changed)
                resumed=isolated.run_partial(root,partial['id'],True,review)
                self.assertEqual(resumed['format'],'almg-optimizer-continuation-v3');self.assertEqual(resumed['status'],'completed');self.assertEqual(resumed['restored_steps'],11)
                self.assertEqual(resumed['step_log'],parent['step_log'][11:]);self.assertEqual(resumed['completed_steps'],20);self.assertEqual(resumed['scheduler_completed_steps'],20)
                self.assertEqual(resumed['source_final_parameter_max_error'],0.);self.assertEqual(resumed['generated_token_ids'],parent['generated_token_ids'])
                self.assertEqual(continuations.read(root,resumed['id']),resumed);self.assertFalse(resumed['release_approved'])
                self.assertTrue(all(fixture.file_digest(p)==sha for p,sha in before.items()))
                feedback=continuations.review_partial(root,partial['id'])['estimates']['optimizer_work_estimate'];self.assertEqual(feedback['sample_count'],1)
                self.assertEqual(feedback['source_records'][0]['record_id'],resumed['id'])
                self.assertIsNone(continuations.review(root,parent['id'])['estimates']['optimizer_work_estimate'])
                with self.assertRaises(ValueError):continuations.review_partial(root,resumed['id'])
                path=continuations._folder(root,partial['id'])/'optimizer.json';saved=path.read_bytes();path.write_text('{}')
                with self.assertRaises(ValueError):continuations.review_partial(root,partial['id'])
                path.write_bytes(saved)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires repeated cancel/resume lineage')
    def test_resume_can_be_canceled_again_and_lineage_rejects_cycles(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);parent,partial=self.source(root,'adamw');token='c'*32
            continuations.cancellation.request(root,partial['id'],token,True,'continuation')
            with self.assertRaises(ValueError):continuations.cancellation.requested(root,partial['id'],partial['revision'],token,'fixture')
            stopped=isolated.run_partial(root,partial['id'],True,continuations.review_partial(root,partial['id']),token)
            self.assertEqual(stopped['status'],'canceled');self.assertEqual(stopped['restored_steps'],11);self.assertEqual(stopped['completed_steps'],11);self.assertEqual(stopped['step_log'],[])
            self.assertEqual(continuations.read(root,stopped['id']),stopped)
            finished=isolated.run_partial(root,stopped['id'],True,continuations.review_partial(root,stopped['id']))
            self.assertEqual(finished['source_final_parameter_max_error'],0.);self.assertEqual(finished['completed_steps'],20)
            self.assertEqual(continuations.read(root,finished['id']),finished)
            path=continuations._folder(root,finished['id'])/'record.json';saved=path.read_text();changed=json.loads(saved);changed['review']['resume_from']['record_id']=finished['id'];changed['revision']=fixture.digest({k:v for k,v in changed.items() if k!='revision'});path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,'cyclic|depth'):continuations.read(root,finished['id'])
            path.write_text(saved)
