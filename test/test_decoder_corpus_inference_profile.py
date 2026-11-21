from copy import deepcopy
import json
import os
from pathlib import Path
import platform
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch,MagicMock
import uuid
from backend import decoder_corpus_inference_profile as profile, decoder_corpus_isolated as isolated
from backend.run_manifest import digest
from test_decoder_corpus_optimizer import corpus


def response(identifier,nonce,pid):
    benchmark={'format':'almg-corpus-inference-benchmark-v1','source':{'record_id':identifier},'runtime':{'device':'CPU'}}
    benchmark['revision']=digest(benchmark)
    report={'format':'almg-corpus-inference-profile-v1','schema_version':1,'protocol':deepcopy(profile.PROTOCOL),
            'protocol_revision':digest(profile.PROTOCOL),'worker_process_id':pid,'source':benchmark['source'],
            'benchmark':benchmark,'memory':{'measured':True,'baseline_after_imports_peak_rss_bytes':100,
            'process_peak_rss_bytes':120,'incremental_model_peak_memory_bytes':None,'allocator_peak_memory_bytes':None,'system':platform.system()},
            'training_approved':False,'release_approved':False,'language_quality_validated':False}
    report['revision']=digest(report)
    return {'nonce':nonce,'process_id':pid,'report':report}


class InferenceProfileTest(unittest.TestCase):
    def test_platform_rss_units_and_invalid_observations(self):
        self.assertEqual(profile._rss_bytes(256,'Darwin'),256)
        self.assertEqual(profile._rss_bytes(256,'Linux'),262144)
        for value,system in ((0,'Darwin'),(-1,'Linux'),(True,'Darwin'),(1.,'Linux'),(256,'Windows')):
            with self.assertRaises(ValueError):profile._rss_bytes(value,system)

    def test_worker_nonce_pid_source_memory_and_revision_binding(self):
        identifier='a'*32;nonce='b'*32;pid=os.getpid()+100000
        original=response(identifier,nonce,pid)
        self.assertEqual(profile._validated_response(original,nonce,pid,identifier),original['report'])
        for changed in ({**original,'nonce':'other'},{**original,'process_id':pid+1}, {'report':{}},[],None):
            with self.assertRaises(ValueError):profile._validated_response(changed,nonce,pid,identifier)
        with self.assertRaises(ValueError):profile._validated_response(original,nonce,pid,'c'*32)
        changed=deepcopy(original);changed['report']['memory']['process_peak_rss_bytes']=99
        changed['report']['revision']=digest({k:v for k,v in changed['report'].items() if k!='revision'})
        with self.assertRaises(ValueError):profile._validated_response(changed,nonce,pid,identifier)
        changed=deepcopy(original);changed['report']['memory']['process_peak_rss_bytes']=121
        with self.assertRaises(ValueError):profile._validated_response(changed,nonce,pid,identifier)

    def test_timeout_kills_and_drains_worker_without_source_writes(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);marker=root/'retained';marker.write_bytes(b'keep')
            process=MagicMock();process.communicate.side_effect=[subprocess.TimeoutExpired('worker',60),('','')]
            with patch.object(profile.subprocess,'Popen',return_value=process),self.assertRaisesRegex(ValueError,'timed out'):
                profile.profile(root,'a'*32)
            process.kill.assert_called_once();self.assertEqual(process.communicate.call_count,2)
            self.assertEqual(marker.read_bytes(),b'keep')

    def test_invalid_ids_and_malformed_worker_responses_rejected(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            with patch.object(profile.subprocess,'Popen') as spawn:
                for identifier in ('bad',None,3):
                    with self.assertRaises(ValueError):profile.profile(root,identifier)
                spawn.assert_not_called()
            for stdout,code in (('invalid',0),('[]',0),('{}',0),('x'*262145,0),(json.dumps({'error':'failed'}),1)):
                process=MagicMock(returncode=code,pid=os.getpid()+100000);process.communicate.return_value=(stdout,'')
                with patch.object(profile.subprocess,'Popen',return_value=process),self.assertRaises(ValueError):profile.profile(root,'a'*32)
            self.assertEqual(list(root.iterdir()),[])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires a real completed corpus model and fresh profiling workers')
    def test_real_workers_have_distinct_ids_measured_rss_and_preserve_sources(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,base=corpus(root)
            config={**base,'steps':10}
            record=isolated.run(root,True,source,saved,config,isolated.review(root,source,saved,config),uuid.uuid4().hex)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            reports=[profile.profile(root,record['id']) for _ in range(2)]
            self.assertNotEqual(reports[0]['worker_process_id'],reports[1]['worker_process_id'])
            for report in reports:
                self.assertNotEqual(report['worker_process_id'],os.getpid())
                memory=report['memory'];self.assertTrue(memory['measured'])
                self.assertGreaterEqual(memory['process_peak_rss_bytes'],memory['baseline_after_imports_peak_rss_bytes'])
                self.assertGreater(memory['process_peak_rss_bytes'],0)
                self.assertIsNone(memory['incremental_model_peak_memory_bytes']);self.assertIsNone(memory['allocator_peak_memory_bytes'])
                self.assertEqual(report['source']['record_revision'],record['revision'])
                self.assertEqual(report['benchmark']['metrics']['generated_tokens'],24)
                self.assertEqual(report['benchmark']['model_size']['parameter_count'],source['actual_parameter_count'])
                for field in ('training_approved','release_approved','language_quality_validated'):self.assertFalse(report[field])
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
