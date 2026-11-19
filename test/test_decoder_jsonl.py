import base64
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile
from backend import decoder_jsonl as importer,decoder_datasets as datasets
from backend.run_manifest import digest


def documents(raw=None):
    if raw is None:
        raw=('\ufeff'+json.dumps({'text':'Orchard café apple harvest and fresh garden fruit.'},ensure_ascii=False)+'\r\n\n'+
             json.dumps({'text':'Distant telescope galaxy stars across the night sky.'})+'\n'+
             json.dumps({'text':'Ocean coral reefs shelter marine fish and coastal waves.'})+'\n').encode()
    return [{'name':'fixture.jsonl','data':base64.b64encode(raw).decode()}]


class JsonlImportTests(unittest.TestCase):
    def test_review_prepare_reload_and_private_export_preserve_file_and_line_provenance(self):
        inputs=documents();review=importer.review(inputs);raw=base64.b64decode(inputs[0]['data'])
        self.assertEqual(review['text_records'],3);self.assertEqual(review['sources'][0]['blank_lines'],1)
        self.assertEqual([row['line'] for row in review['sources'][0]['records']],[1,3,4])
        self.assertEqual(review['sources'][0]['original_source_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(review['sources'][0]['records'][0]['raw_line_sha256'],hashlib.sha256(raw.split(b'\n')[0]).hexdigest())
        self.assertIn('café',review['sources'][0]['records'][0]['preview'])
        with TemporaryDirectory() as root:
            manifest=importer.prepare(root,inputs,True,review);self.assertEqual(datasets.read(root,manifest['id']),manifest)
            provenance=manifest['derivation']['extraction_provenance']
            self.assertEqual(provenance['revision'],digest({k:v for k,v in provenance.items() if k!='revision'}))
            self.assertNotIn('preview',json.dumps(provenance));self.assertFalse(provenance['training_approved'])
            original_rows={row['document_name']:row for row in provenance['sources'][0]['records']}
            for source in manifest['sources']:
                self.assertEqual(source['source_sha256'],original_rows[source['name']]['extracted_source_sha256'])
            review_export=datasets.export_review(root,manifest['id'])
            archive=datasets.export_dataset(root,manifest['id'],True,review_export['revision'])
            payload=base64.b64decode(archive['data'])
            with zipfile.ZipFile(io.BytesIO(payload)) as package:
                exported=json.loads(package.read('manifest.json'))
                self.assertEqual(exported['derivation'],manifest['derivation'])
                self.assertFalse(any(name.endswith('fixture.jsonl') for name in package.namelist()))
            self.assertFalse((Path(root)/'decoder-trials').exists())

    def test_consent_stale_review_and_changed_bytes_leave_no_dataset(self):
        inputs=documents();review=importer.review(inputs)
        with TemporaryDirectory() as root:
            for confirmed,checked in ((False,review),(True,dict(review,implementation_sha256='stale'))):
                with self.assertRaises(ValueError):importer.prepare(root,inputs,confirmed,checked)
            changed=documents(base64.b64decode(inputs[0]['data']).replace(b'Orchard',b'Changed'))
            with self.assertRaises(ValueError):importer.prepare(root,changed,True,review)
            self.assertFalse((Path(root)/'decoder-datasets').exists())

    def test_malformed_metadata_duplicate_fields_encoding_and_bounds_fail(self):
        for raw in (b'\xff',b'{"text":"x","text":"y"}',b'{"text":"x","license":"private"}',
                    b'{"text":null}',b'{"text":{"text":"nested"}}',b'["text"]',b'{bad}',
                    b'{"text":""}',b'{"text":"\\ud800"}',b'\n\n',b'x'*65537,b'['*2000+b']'*2000,
                    b'\n'.join(json.dumps({'text':str(i)}).encode() for i in range(17))):
            with self.subTest(raw=raw[:60]),self.assertRaises(ValueError):importer.review(documents(raw))
        with self.assertRaisesRegex(ValueError,'at least three'):importer.review(documents(b'{"text":"one"}\n'))
        with self.assertRaises(ValueError):importer.review(documents()+documents())

    def test_unicode_line_separator_remains_inside_one_record(self):
        inputs=documents();raw=base64.b64decode(inputs[0]['data']).replace(b'Orchard',b'Orchard\xe2\x80\xa8')
        review=importer.review(documents(raw));self.assertEqual(review['text_records'],3)
