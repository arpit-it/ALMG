import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid
from backend import decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class CorpusRegularizationControlsTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual local clipping and decay training')
    def test_selected_clipping_and_decay_bind_approval_update_weights_and_continue(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,base=corpus(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()};adam_models=[]
            cases=[('sgd',clip,0.) for clip in (.1,.5,1.)]+[('adamw',.1,decay) for decay in (0.,.01,.05)]
            for kind,clip,decay in cases:
                with self.subTest(optimizer=kind,clip=clip,decay=decay):
                    c={**base,'optimizer':kind,'gradient_clip_norm':clip,'weight_decay':decay}
                    approved=isolated.review(root,source,saved,c);files={p for p in root.rglob('*') if p.is_file()}
                    changes=[{'gradient_clip_norm':clip/2}]+([{'weight_decay':.05 if decay==0 else 0.}] if kind=='adamw' else [])
                    for change in changes:
                        with self.assertRaises(ValueError):isolated.run(root,True,source,saved,{**c,**change},approved,uuid.uuid4().hex)
                    self.assertEqual(files,{p for p in root.rglob('*') if p.is_file()})
                    record=isolated.run(root,True,source,saved,c,approved,uuid.uuid4().hex)
                    self.assertEqual(record['review']['config'],c)
                    for entry in record['step_log']:
                        self.assertAlmostEqual(entry['clip_scale'],min(1.,clip/entry['gradient_norm']))
                        self.assertLessEqual(entry['gradient_norm']*entry['clip_scale'],clip+1e-10)
                    if clip==.1:self.assertLess(record['step_log'][0]['clip_scale'],1.)
                    self.assertLess(record['final_losses']['train'],record['initial_losses']['train'])
                    self.assertLessEqual(record['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(record['checkpoint_optimizer_max_error'],1e-7)
                    continued=isolated.run_continuation(root,record['id'],True,isolated.review_continuation(root,record['id']),uuid.uuid4().hex)
                    self.assertEqual(continued['restored_step'],10);self.assertEqual(continued['completed_steps'],20);self.assertLessEqual(continued['reference_parameter_max_error'],1e-7)
                    self.assertEqual(training.read(root,record['id']),record)
                    if kind=='adamw':adam_models.append(record['files']['trained-model.json'])
            self.assertEqual(len(set(adam_models)),3,'Changing only AdamW decay must change the saved trained weights.')
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
