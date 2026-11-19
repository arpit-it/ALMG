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
            'real_target_tokens':sum(lengths),'split':split,'next_cursor':None,
            'provenance':[{'group':'a'*64,'token_offset':i*16,'split':split} for i in range(4)]}


def read_fixture(root,window_id,confirmed,reviewed,cursor=None,split='train',batch_size=4):
    return fixture_batch(split)


class StreamOptimizationTests(unittest.TestCase):
    def test_consent_and_stale_batch_reject_before_model_initialization(self):
        with TemporaryDirectory() as root,patch.object(optimization.recipe_contracts,'initialize_recipe') as initialize:
            with self.assertRaises(ValueError):optimization.run(root,'a'*32,False,{'revision':'r','window_counts':{'validation':4,'test':4}},fixture_batch())
            with patch.object(optimization.batches,'read_batch',side_effect=read_fixture):
                with self.assertRaisesRegex(ValueError,'batch changed'):optimization.run(root,'a'*32,True,{'revision':'r'},{})
            initialize.assert_not_called();self.assertEqual(list(Path(root).iterdir()),[])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1' and platform.system()=='Darwin' and platform.machine()=='arm64','Requires explicit local Metal tests')
    def test_real_masked_sgd_updates_all_tensors_and_ignores_padded_targets_without_saving_model(self):
        with TemporaryDirectory() as root,patch.object(optimization.batches,'read_batch',side_effect=read_fixture),patch.object(optimization.decoder_bundle,'save') as save:
            report=optimization.run(root,'a'*32,True,{'revision':'r','window_counts':{'validation':4,'test':4}},fixture_batch())
            self.assertLess(report['final_batch_loss'],report['initial_batch_loss'])
            self.assertEqual(len(report['changed_parameter_tensors']),report['parameter_tensors'])
            self.assertEqual(report['padded_positions'],12)
            self.assertLessEqual(report['masked_target_loss_error'],1e-6)
            self.assertLessEqual(report['masked_target_gradient_error'],1e-6)
            self.assertLess(report['cpu_inference_max_error'],1e-5)
            self.assertFalse(report['model_saved']);self.assertFalse(report['release_approved']);self.assertFalse(report['training_approved'])
            self.assertFalse(report['pretrained_weights_loaded']);save.assert_not_called()
            self.assertEqual(len(list((Path(root)/'decoder-stream-optimization-checks'/('a'*32)).glob('*.json'))),1)
            self.assertEqual(report['evaluation']['test']['scope'],'all_saved_split_windows')
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
                optimization.run(root,'a'*32,True,{'revision':'r','window_counts':{'validation':4,'test':4}},fixture_batch())
            self.assertEqual(list(Path(root).iterdir()),[])


class CompleteSplitEvaluationTests(unittest.TestCase):
    def test_multiple_pages_weight_real_targets_instead_of_batch_means(self):
        pages=[{'rows':16,'real_target_tokens':256,'next_cursor':{'after':16}},
               {'rows':1,'real_target_tokens':3,'next_cursor':None}]
        calls=[]
        def read(*args):
            calls.append(args);return pages[len(calls)-1]
        def score(batch):
            return (512.0,128) if batch['rows']==16 else (12.0,3)
        with patch.object(optimization.batches,'read_batch',side_effect=read):
            result=optimization.evaluate_split(None,'a'*32,{'window_counts':{'test':17}},'test',score)
        self.assertEqual(result['windows'],17);self.assertEqual(result['target_tokens'],259)
        self.assertAlmostEqual(result['loss'],524/259);self.assertAlmostEqual(result['next_token_accuracy'],131/259)
        self.assertEqual(calls[0][-3:],(None,'test',16));self.assertEqual(calls[1][-3:],({'after':16},'test',16))
        self.assertEqual(result['optimizer_updates'],0)

    def test_incomplete_population_and_nonfinite_metrics_fail_closed(self):
        page={'rows':1,'real_target_tokens':3,'next_cursor':None}
        with patch.object(optimization.batches,'read_batch',return_value=page):
            with self.assertRaisesRegex(ValueError,'population'):
                optimization.evaluate_split(None,'a'*32,{'window_counts':{'test':2}},'test',lambda batch:(3.0,1))
            with self.assertRaisesRegex(ValueError,'invalid metrics'):
                optimization.evaluate_split(None,'a'*32,{'window_counts':{'test':1}},'test',lambda batch:(float('nan'),1))
