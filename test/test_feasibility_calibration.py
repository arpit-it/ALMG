from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch
from backend import decoder_architecture_feasibility as feasibility,decoder_architecture_plans as plans,decoder_architecture_initializations as initializations
from backend.run_manifest import digest,file_digest


class FeasibilityCalibrationTests(unittest.TestCase):
    def fixture(self,root):
        plan=plans.save(root,True,plans.review(dict(plans.DEFAULT)));record=initializations.run(root,plan['id'],True,plan)
        hardware={'system':'Darwin','machine':'arm64','mlx_version':'fixture','metal_available':True,'metal_device':{'device_name':'Fixture GPU','max_recommended_working_set_size':8*1024**3},
                  'available_memory_bytes':4*1024**3,'free_disk_bytes':8*1024**3,'errors':[]}
        with patch.object(feasibility,'hardware',return_value=hardware):saved=feasibility.review(root,plan['id'],True,record)
        report={'id':'a'*32,'format':'almg-planned-decoder-backward-check-v4','schema_version':4,'plan_id':plan['id'],
                'initialization_revision':record['revision'],'model_sha256':record['model_sha256'],'config':record['config'],
                'backward_checked':True,'updated_weights_saved':False,'training_approved':False,'release_approved':False,'hardware_feasibility':saved,
                'implementation_sha256':digest({name:file_digest(Path(feasibility.__file__).with_name(name)) for name in ('decoder_architecture_backward.py','decoder_architecture_feasibility.py','decoder_diagnostic_measurements.py','decoder_diagnostic_worker.py','planned_decoder.py')}),
                'diagnostic_measurements':{'isolated_trial_peak_measured':True,'scope':'fresh_process_synthetic_diagnostic','isolated_metal_peak_bytes':16*1024**2,'isolated_process_peak_rss_bytes':1024**3}}
        path=root/'decoder-architecture-backward-checks'/plan['id']/(report['id']+'.json');path.parent.mkdir(parents=True)
        return record,hardware,report,path

    def write(self,path,report):
        report['revision']=digest({k:v for k,v in report.items() if k!='revision'});path.write_text(json.dumps(report))

    def test_compatible_measurement_raises_reserves_readonly_and_live_admission_blocks(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record,hardware,report,path=self.fixture(root);self.write(path,report);before=path.read_bytes()
            with patch.object(feasibility,'hardware',return_value=hardware):review=feasibility.review(root,record['plan_id'],True,record)
            self.assertEqual(len(review['calibration']['compatible_reports']),1)
            self.assertEqual(review['estimates']['required_available_memory_bytes'],256*1024**2+1024**3+16*1024**2)
            self.assertEqual(path.read_bytes(),before)
            low=deepcopy(hardware);low['available_memory_bytes']=512*1024**2
            with patch.object(feasibility,'hardware',return_value=low):
                with self.assertRaisesRegex(ValueError,'blocked'):feasibility.admit(root,record['plan_id'],record,review)

    def test_incompatible_tampered_and_shared_records_do_not_calibrate(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record,hardware,original,path=self.fixture(root)
            variants=[]
            for key,value in [('implementation_sha256','old'),('initialization_revision','wrong')]:
                changed=deepcopy(original);changed[key]=value;variants.append(changed)
            changed=deepcopy(original);changed['diagnostic_measurements']['isolated_trial_peak_measured']=False;variants.append(changed)
            changed=deepcopy(original);changed['diagnostic_measurements']['isolated_metal_peak_bytes']=-1;variants.append(changed)
            changed=deepcopy(original);changed['hardware_feasibility']['hardware']['mlx_version']='different';variants.append(changed)
            for report in variants:
                self.write(path,report)
                with patch.object(feasibility,'hardware',return_value=hardware):review=feasibility.review(root,record['plan_id'],True,record)
                self.assertFalse(review['calibration']['compatible_reports'])
            self.write(path,original);path.write_text(path.read_text().replace('16777216','16777217'))
            with patch.object(feasibility,'hardware',return_value=hardware):self.assertFalse(feasibility.review(root,record['plan_id'],True,record)['calibration']['compatible_reports'])

    def test_older_high_water_measurement_is_retained_beyond_twenty_reports(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record,hardware,original,path=self.fixture(root);self.write(path,original)
            for index in range(21):
                report=deepcopy(original);report['id']=format(int('b'*32,16)+index,'032x')
                report['diagnostic_measurements']['isolated_metal_peak_bytes']=1
                report['diagnostic_measurements']['isolated_process_peak_rss_bytes']=1
                self.write(path.with_name(report['id']+'.json'),report)
            with patch.object(feasibility,'hardware',return_value=hardware):review=feasibility.review(root,record['plan_id'],True,record)
            self.assertEqual(len(review['calibration']['compatible_reports']),22)
            self.assertEqual(review['calibration']['observed_process_peak_rss_bytes'],1024**3)
