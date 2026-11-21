import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid
from backend import decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated, decoder_corpus_continuations as continuations
from test_decoder_corpus_optimizer import corpus


class CorpusLossTraceTest(unittest.TestCase):
    def test_optional_legacy_logs_and_strict_finite_nonnegative_values(self):
        for record in ({},{'step_log':[{'step':1}]},{'step_log':[{'batch_loss_before_update':0.}]}):
            training.validate_batch_losses(record)
        for value in (True,None,'1',float('nan'),float('inf'),-1.):
            for field in ('step_log','reference_step_log'):
                with self.assertRaises(ValueError):training.validate_batch_losses({field:[{'batch_loss_before_update':value}]})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual Metal loss evaluation')
    def test_masked_unscaled_batch_losses_and_restored_counters_for_both_precisions(self):
        for precision in ('float32','mixed_float16'):
            for kind in ('sgd','adamw'):
                with self.subTest(precision=precision,optimizer=kind),TemporaryDirectory() as temporary:
                    root=Path(temporary);source,saved,base=corpus(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                    c={**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'batch_size':2,'gradient_accumulation_steps':2,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.}
                    _,_,_,windows,_=training._source(root,source,saved);model=training.PlannedDecoder.load(training.hardware.initializations._folder(root,source['plan_id'])/source['id']/'model.json');_,arrays=training.batch_arrays(windows['train'],0,2)
                    expected=training.backward.cpu_loss(model,*arrays)
                    record=isolated.run(root,True,source,saved,c,isolated.review(root,source,saved,c),uuid.uuid4().hex)
                    self.assertEqual(len(record['step_log']),20);self.assertLess(abs(record['step_log'][0]['batch_loss_before_update']-expected),.05 if precision=='mixed_float16' else 1e-5)
                    self.assertTrue(all(math.isfinite(e['batch_loss_before_update']) and e['batch_loss_before_update']>=0 for e in record['step_log']))
                    continued=isolated.run_continuation(root,record['id'],True,isolated.review_continuation(root,record['id']),uuid.uuid4().hex)
                    self.assertEqual([e['step'] for e in continued['step_log']],list(range(11,21)))
                    for actual,reference in zip(continued['step_log'],record['step_log'][10:]):self.assertLessEqual(abs(actual['batch_loss_before_update']-reference['batch_loss_before_update']),1e-6)
                    for item,reader,directory in ((record,training.read,'decoder-corpus-optimizer-runs'),(continued,continuations.read,'decoder-corpus-continuations')):
                        path=root/directory/item['id']/'record.json';original=path.read_bytes();changed=json.loads(original);changed['step_log'][0]['batch_loss_before_update']=True;changed['revision']=training.digest({k:v for k,v in changed.items() if k!='revision'});path.write_text(json.dumps(changed))
                        with self.assertRaisesRegex(ValueError,'batch-loss'):reader(root,item['id'])
                        path.write_bytes(original)
                    self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires invalid-loss Metal guard')
    def test_invalid_loss_stops_before_gradient_update_and_checkpoint_publication(self):
        import mlx.core as mx
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=corpus(root);_,current,_,windows,_=training._source(root,source,saved);model=training.PlannedDecoder.load(training.hardware.initializations._folder(root,source['plan_id'])/source['id']/'model.json')
            for value in (float('nan'),float('inf'),-1.):
                gradient=Mock();checkpoint=Mock();observer=SimpleNamespace(sample=Mock());state={'step':0,'m':{},'v':{}}
                with patch.object(training.backward,'metal_functions',return_value=(None,lambda *args:mx.array(value),gradient)),patch.object(training.optimizer,'update') as update:
                    with self.assertRaisesRegex(ValueError,'before optimizer update 1'):training.train_updates(model.parameters,state,1,windows['train'],c,current['config'],mx,observer,checkpoint=checkpoint)
                    gradient.assert_not_called();update.assert_not_called();checkpoint.assert_not_called();observer.sample.assert_not_called();self.assertEqual(state['step'],0)
