import os
import platform
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_stream_optimization as optimization


def fixture_batch(split='train'):
    lengths=[16,16,16,4];inputs=[];targets=[];masks=[]
    for i,length in enumerate(lengths):
        ids=[97+(j+i)%20 for j in range(length+1)]
        inputs.append(ids[:-1]+[0]*(16-length));targets.append(ids[1:]+[0]*(16-length));masks.append([1]*length+[0]*(16-length))
    return {'rows':4,'inputs':inputs,'targets':targets,'loss_mask':masks,'sequence_lengths':lengths,
            'real_target_tokens':sum(lengths),'split':split,
            'provenance':[{'group':'a'*64,'token_offset':i*16,'split':split} for i in range(4)]}


def read_fixture(root,window_id,confirmed,reviewed,cursor=None,split='train',batch_size=4):
    return fixture_batch(split)


class StreamOptimizationTests(unittest.TestCase):
    def test_consent_and_stale_batch_reject_before_model_initialization(self):
        with TemporaryDirectory() as root,patch.object(optimization.recipe_contracts,'initialize_recipe') as initialize:
            with self.assertRaises(ValueError):optimization.run(root,'a'*32,False,{'revision':'r'},fixture_batch())
            with patch.object(optimization.batches,'read_batch',side_effect=read_fixture):
                with self.assertRaisesRegex(ValueError,'batch changed'):optimization.run(root,'a'*32,True,{'revision':'r'},{})
            initialize.assert_not_called();self.assertEqual(list(Path(root).iterdir()),[])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1' and platform.system()=='Darwin' and platform.machine()=='arm64','Requires explicit local Metal tests')
    def test_real_masked_sgd_updates_all_tensors_and_ignores_padded_targets_without_saving_model(self):
        with TemporaryDirectory() as root,patch.object(optimization.batches,'read_batch',side_effect=read_fixture),patch.object(optimization.decoder_bundle,'save') as save:
            report=optimization.run(root,'a'*32,True,{'revision':'r'},fixture_batch())
            self.assertLess(report['final_batch_loss'],report['initial_batch_loss'])
            self.assertEqual(len(report['changed_parameter_tensors']),report['parameter_tensors'])
            self.assertEqual(report['padded_positions'],12)
            self.assertLessEqual(report['masked_target_loss_error'],1e-6)
            self.assertLessEqual(report['masked_target_gradient_error'],1e-6)
            self.assertLess(report['cpu_inference_max_error'],1e-5)
            self.assertFalse(report['model_saved']);self.assertFalse(report['release_approved']);self.assertFalse(report['training_approved'])
            self.assertFalse(report['pretrained_weights_loaded']);save.assert_not_called()
            self.assertEqual(len(list((Path(root)/'decoder-stream-optimization-checks'/('a'*32)).glob('*.json'))),1)
            self.assertEqual(report['probes']['test']['scope'],'first_four_windows_only_not_full_evaluation')
            self.assertEqual(optimization.list_reports(root,'a'*32,True),[report])
            with self.assertRaises(ValueError):optimization.list_reports(root,'a'*32,False)
            path=Path(root)/'decoder-stream-optimization-checks'/('a'*32)/(report['id']+'.json')
            path.write_text(path.read_text().replace('"model_saved": false','"model_saved": true'))
            self.assertEqual(optimization.list_reports(root,'a'*32,True),[])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1' and platform.system()=='Darwin' and platform.machine()=='arm64','Requires explicit local Metal tests')
    def test_post_gpu_source_change_prevents_report_publication(self):
        calls=[]
        def changed(*args,**kwargs):
            calls.append(1);batch=read_fixture(*args,**kwargs)
            return {**batch,'changed':True} if len(calls)==4 else batch
        with TemporaryDirectory() as root,patch.object(optimization.batches,'read_batch',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'Source bindings changed'):
                optimization.run(root,'a'*32,True,{'revision':'r'},fixture_batch())
            self.assertEqual(list(Path(root).iterdir()),[])
