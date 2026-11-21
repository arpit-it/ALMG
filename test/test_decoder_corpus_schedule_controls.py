import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid
from backend import decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class CorpusScheduleControlsTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual local schedule training')
    def test_selected_schedules_reduce_loss_bind_approval_and_continue_from_actual_counter(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,base=corpus(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for kind in ('sgd','adamw'):
                for rate,warmup in ((.001,0),(.005,1),(.01,2),(.005,3)):
                    with self.subTest(optimizer=kind,rate=rate,warmup=warmup):
                        c={**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'learning_rate':rate,'warmup_steps':warmup}
                        approved=isolated.review(root,source,saved,c)
                        files={p for p in root.rglob('*') if p.is_file()}
                        for change in ({'learning_rate':rate/2},{'warmup_steps':(warmup+1)%4}):
                            with self.assertRaises(ValueError):isolated.run(root,True,source,saved,{**c,**change},approved,uuid.uuid4().hex)
                        self.assertEqual(files,{p for p in root.rglob('*') if p.is_file()})
                        record=isolated.run(root,True,source,saved,c,approved,uuid.uuid4().hex)
                        self.assertEqual(record['review']['config'],c)
                        rates=[entry['learning_rate'] for entry in record['step_log']]
                        self.assertAlmostEqual(rates[0],rate/warmup if warmup else rate*(.1+.45*(1+math.cos(math.pi/20))))
                        self.assertAlmostEqual(rates[-1],rate*.1)
                        if warmup:self.assertAlmostEqual(rates[warmup-1],rate)
                        self.assertLess(record['final_losses']['train'],record['initial_losses']['train'])
                        self.assertLessEqual(record['checkpoint_parameter_max_error'],1e-7)
                        self.assertLessEqual(record['checkpoint_optimizer_max_error'],1e-7)
                        continued=isolated.run_continuation(root,record['id'],True,isolated.review_continuation(root,record['id']),uuid.uuid4().hex)
                        self.assertEqual(continued['restored_step'],10);self.assertEqual(continued['completed_steps'],20)
                        self.assertLessEqual(continued['reference_parameter_max_error'],1e-7)
                        self.assertEqual(training.read(root,record['id']),record)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
