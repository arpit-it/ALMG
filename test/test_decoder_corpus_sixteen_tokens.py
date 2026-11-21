import json
from itertools import permutations
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_inputs as inputs, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated, decoder_corpus_interruptions as interruptions
from backend import decoder_datasets,decoder_architecture_plans as plans,decoder_architecture_initializations as initializations
from test_decoder_corpus_inputs import fixture,permissions
from test_decoder_corpus_interruptions import HOOK


def long_fixture(root):
    source,_=fixture(root);words=['amber','birch','cedar','dune']
    cycles=[[words[0],*tail] for tail in permutations(words[1:])]
    dataset=decoder_datasets.prepare(root,[{'name':f'long-{i}.txt','text':' '.join(cycle[j%4] for j in range(20+i))} for i,cycle in enumerate(cycles)],True)
    return source,dataset


def saved_sixteen(root):
    source,dataset=long_fixture(root);dataset=permissions(root,dataset);review=inputs.review(root,source['plan_id'],source,dataset,16)
    return source,inputs.save(root,source['plan_id'],True,source,dataset,16,review)


def settings(kind='sgd',budget=20):
    return {**training.optimizer.DEFAULT,'schema_version':8,'steps':budget,'batch_size':2,'sequence_length':16,'gradient_accumulation_steps':2,'compute_precision':'float32','loss_scale':1.,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}


class SixteenTokenTest(unittest.TestCase):
    def test_versioned_inputs_preserve_legacy_masks_permissions_context_and_strict_configuration(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,dataset=long_fixture(root)
            self.assertFalse(inputs.review(root,source['plan_id'],source,dataset,16)['compatible']);dataset=permissions(root,dataset)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()};records=[]
            for length,version in ((8,1),(16,2)):
                review=inputs.review(root,source['plan_id'],source,dataset,length)
                self.assertEqual(review['schema_version'],version)
                with self.assertRaises(ValueError):inputs.save(root,source['plan_id'],False,source,dataset,length,review)
                record=inputs.save(root,source['plan_id'],True,source,dataset,length,review);records.append(record);self.assertEqual(inputs.read(root,record['id']),record)
            windows=json.loads((root/'decoder-corpus-inputs'/records[-1]['id']/'windows.json').read_text())
            self.assertTrue(any(sum(row['target_mask'])==16 for row in windows['train']));self.assertTrue(any(0 in row['target_mask'] for row in windows['train']))
            for part in windows:self.assertEqual(records[0]['review']['splits'][part]['target_tokens'],records[1]['review']['splits'][part]['target_tokens'])
            self.assertEqual({r['id'] for r in inputs.history(root,source['plan_id'],source)},{r['id'] for r in records})
            short_plan=plans.save(root,True,plans.review({**plans.DEFAULT,'vocab_size':4,'context_length':8}));short=initializations.run(root,short_plan['id'],True,short_plan)
            blocked=inputs.review(root,short['plan_id'],short,dataset,16);self.assertFalse(blocked['compatible'])
            with self.assertRaises(ValueError):inputs.save(root,short['plan_id'],True,short,dataset,16,blocked)
            for budget in (10,20):self.assertEqual(training.configuration(settings(budget=budget),16),settings(budget=budget))
            for changes in ({'sequence_length':8},{'sequence_length':32},{'compute_precision':'mixed_float16','loss_scale':128.},{'steps':40},{'steps':80},{'steps':100},{'batch_size':4},{'steps':True}):
                with self.assertRaises(ValueError):training.configuration({**settings(),**changes},16)
            for version,budget in ((5,20),(6,40),(7,80)):
                with self.assertRaises(ValueError):training.configuration({**settings(),'schema_version':version,'steps':budget},16)
            with patch.object(training.hardware,'_source') as load:
                with self.assertRaisesRegex(ValueError,'reviewed corpus workflow'):training.optimizer.review(root,source['plan_id'],source,settings())
                load.assert_not_called()
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            path=root/'decoder-corpus-inputs'/records[-1]['id']/'record.json';original=path.read_bytes();changed=json.loads(original);changed.update(format='almg-decoder-corpus-inputs-v1',schema_version=1);changed['revision']=training.digest({k:v for k,v in changed.items() if k!='revision'});path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):inputs.read(root,changed['id'])
            path.write_bytes(original)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires sixteen-token Metal corpus gradients')
    def test_both_fp32_optimizers_and_budgets_restore_state_and_continue_exactly(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved=saved_sixteen(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for kind in ('sgd','adamw'):
                for budget in (10,20):
                    c=settings(kind,budget);approved=isolated.review(root,source,saved,c);record=isolated.run(root,True,source,saved,c,approved,uuid.uuid4().hex)
                    self.assertEqual(record['completed_steps'],budget);self.assertEqual(record['checkpoint_restored_steps'],budget//2);self.assertLessEqual(record['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(record['checkpoint_optimizer_max_error'],1e-7)
                    self.assertLess(record['final_losses']['train'],record['initial_losses']['train']);self.assertLessEqual(record['cpu_metal_max_error'],1e-5);self.assertEqual(training.read(root,record['id']),record)
                    continued=isolated.run_continuation(root,record['id'],True,isolated.review_continuation(root,record['id']),uuid.uuid4().hex)
                    self.assertEqual(continued['restored_step'],budget//2);self.assertEqual(continued['completed_steps'],budget);self.assertLessEqual(continued['reference_parameter_max_error'],1e-7)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual sixteen-token worker interruption')
    def test_training_midpoint_survives_worker_interruption_for_both_fp32_optimizers(self):
        for kind in ('sgd','adamw'):
            with self.subTest(optimizer=kind),TemporaryDirectory() as temporary:
                root=Path(temporary);source,saved=saved_sixteen(root);c=settings(kind);approved=isolated.review(root,source,saved,c);token=uuid.uuid4().hex;hooks=root/'hooks';hooks.mkdir();(hooks/'sitecustomize.py').write_text(HOOK)
                env={**os.environ,'PYTHONPATH':str(hooks)+os.pathsep+str(Path(__file__).resolve().parent.parent),'ALMG_INTERRUPTION_TEST_ROOT':str(root),'ALMG_INTERRUPTION_TEST_PHASE':'3','ALMG_INTERRUPTION_TEST_STEP':'11'}
                process=subprocess.Popen([sys.executable,'-m','backend.decoder_corpus_worker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
                try:
                    process.stdin.write(json.dumps({'root':str(root),'initialized':source,'corpus':saved,'settings':c,'approved':approved,'request_id':token,'nonce':uuid.uuid4().hex,'action':'full'}));process.stdin.close();process.stdin=None;deadline=time.monotonic()+15
                    while not (root/'progress.json').exists():
                        if process.poll() is not None:self.fail(process.communicate()[1])
                        self.assertLess(time.monotonic(),deadline);time.sleep(.02)
                    records=[training.read(root,p.parent.name) for p in (root/interruptions.DIRECTORY).glob('*/record.json')];self.assertEqual(len(records),7);record=max(records,key=interruptions.progress);self.assertEqual(record['completed_steps'],10);self.assertEqual(record['owner_process_id'],process.pid)
                    process.kill();process.communicate(timeout=10)
                finally:
                    if process.poll() is None:process.kill();process.communicate(timeout=10)
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()};result=isolated.run_training_resume(root,record['id'],True,isolated.review_training_resume(root,record['id']),uuid.uuid4().hex)
                self.assertEqual(result['training_steps_carried'],10);self.assertEqual(result['training_updates_executed'],10);self.assertEqual(result['reference_updates_executed'],0);self.assertLessEqual(result['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(result['checkpoint_optimizer_max_error'],1e-7)
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
