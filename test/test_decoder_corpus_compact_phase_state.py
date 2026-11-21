import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
from backend import decoder_corpus_optimizer as training, decoder_corpus_reference_resume as reference, decoder_corpus_training_resume as recorded
from test_decoder_optimizer_state import state
from test_planned_decoder_compact import larger


class CompactPhaseStateTest(unittest.TestCase):
    def test_zero_state_stays_legacy_and_cannot_claim_moments(self):
        model=larger();c={**training.optimizer.DEFAULT,'optimizer':'adamw'}
        with TemporaryDirectory() as temporary:
            root=Path(temporary);path=root/'optimizer.json';initial={'step':0,'m':{},'v':{}}
            training.run_cancellation._save_state(path,initial,model,c)
            self.assertEqual(json.loads(path.read_text()),initial)
            self.assertEqual(training.run_cancellation._state(root,path.name,model,c,0),initial)
            with self.assertRaises(ValueError):training.run_cancellation._save_state(path,{'step':0,'m':{'head':model.parameters['head']},'v':{}},model,c)
            path.write_text(json.dumps({**initial,'format':'unknown'}))
            with self.assertRaises(ValueError):training.run_cancellation._state(root,path.name,model,c,0)

    def test_phase_loaders_restore_legacy_and_compact_moments(self):
        model=larger();c={**training.optimizer.DEFAULT,'optimizer':'adamw'}
        with TemporaryDirectory() as temporary:
            root=Path(temporary);identifier='a'*32;folder=training._folder(root,identifier);folder.mkdir(parents=True)
            model.save(folder/'trained-model.json');model.save(folder/'reference-model.json')
            parent={'id':identifier,'completed_steps':5,'review':{'config':c}}
            for compact in (False,True):
                for name,step in (('optimizer.json',5),('reference-optimizer.json',10)):
                    original=state(model.parameters);original['step']=step
                    if compact:training.run_cancellation._save_state(folder/name,original,model,c)
                    else:(folder/name).write_text(json.dumps(training.optimizer.optimizer_state.encode(original,model.parameters,c,compact=False,allow_completed=True)))
                for loader,step in ((reference.state,5),(recorded.reference,10)):
                    _,restored=loader(root,parent);expected=state(model.parameters)
                    self.assertEqual(restored['step'],step)
                    for kind in ('m','v'):
                        for name,value in expected[kind].items():np.testing.assert_array_equal(restored[kind][name].view(np.uint32),value.view(np.uint32))
                with self.assertRaises(ValueError):training.run_cancellation._state(folder,'optimizer.json',model,c,6)

    def test_bad_nonzero_state_does_not_replace_destination(self):
        model=larger();c={**training.optimizer.DEFAULT,'optimizer':'adamw'}
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/'optimizer.json';original=state(model.parameters)
            training.run_cancellation._save_state(path,original,model,c);before=path.read_bytes()
            original['v']['head'][0,0]=-1
            with self.assertRaises(ValueError):training.run_cancellation._save_state(path,original,model,c)
            self.assertEqual(path.read_bytes(),before)
