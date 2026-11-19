import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from backend import decoder_datasets as datasets, decoder_languages as languages

ENGLISH = 'The children are reading interesting books at the local library every morning while their parents discuss the weather and plan a pleasant walk through the park.'
SPANISH = 'Los niños leen libros interesantes en la biblioteca local cada mañana mientras sus padres hablan del tiempo y preparan un paseo agradable por el parque.'


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dataset = datasets.prepare(self.root, [
            {'name':'english.txt','text':ENGLISH}, {'name':'spanish.txt','text':SPANISH},
            {'name':'short.txt','text':'café'}], True, 'utf8_bytes')
        self.dataset_id = self.dataset['id']

    def test_explicit_report_binds_records_and_leaves_short_text_unknown(self):
        folder = self.root/'decoder-datasets'/self.dataset_id
        before = {p.name:p.read_bytes() for p in folder.iterdir()}
        def recognize(texts):
            self.assertNotIn('café', texts)
            return [{'en':.95,'fr':.03} if text==ENGLISH else {'es':.91,'pt':.05} for text in texts]
        with patch.object(languages, '_recognize', side_effect=recognize):
            report = languages.analyze(self.root,self.dataset_id,True)
            self.assertEqual(languages.analyze(self.root,self.dataset_id,True),report)
        rows = {row['name']:row for row in report['records']}
        self.assertEqual((report['identified_records'],report['unknown_records']),(2,1))
        self.assertEqual(rows['english.txt']['language'],'en')
        self.assertEqual(rows['spanish.txt']['language'],'es')
        self.assertEqual(rows['short.txt']['language'],'und')
        self.assertEqual(rows['short.txt']['reason'],'insufficient_alphabetic_text')
        for row in rows.values():
            source=next(s for s in self.dataset['sources'] if s['name']==row['name'])
            self.assertEqual(row['source_sha256'],source['source_sha256'])
            self.assertEqual(row['split'],source['split'])
        self.assertNotIn(ENGLISH,json.dumps(report))
        self.assertEqual(languages.list_reports(self.root,self.dataset_id),[report])
        self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_ambiguity_and_unavailable_provider_are_explicit_unknowns(self):
        with patch.object(languages,'_recognize',side_effect=lambda texts:[{'en':.82,'fr':.75} for _ in texts]):
            report=languages.analyze(self.root,self.dataset_id,True)
        self.assertEqual(report['identified_records'],0)
        self.assertTrue(all(row['language']=='und' for row in report['records']))
        with patch.object(languages,'_recognize',side_effect=lambda texts:[{'und':1.0} for _ in texts]):
            report=languages.analyze(self.root,self.dataset_id,True)
        self.assertEqual(report['identified_records'],0)
        with patch.object(languages,'_recognize',return_value=None):
            report=languages.analyze(self.root,self.dataset_id,True)
        self.assertFalse(report['runtime']['provider_available'])
        self.assertEqual({row['reason'] for row in report['records']},{'provider_unavailable','insufficient_alphabetic_text'})

    def test_consent_integrity_and_tampered_receipts(self):
        with patch.object(languages,'_recognize') as recognize:
            with self.assertRaises(ValueError): languages.analyze(self.root,self.dataset_id,False)
            recognize.assert_not_called()
        with patch.object(languages,'_recognize',return_value=None):
            report=languages.analyze(self.root,self.dataset_id,True)
            path=self.root/'decoder-language-reports'/self.dataset_id/(report['revision']+'.json')
            changed=dict(report,identified_records=99);path.write_text(json.dumps(changed))
            self.assertEqual(languages.list_reports(self.root,self.dataset_id),[])
            with self.assertRaisesRegex(ValueError,'integrity'): languages.analyze(self.root,self.dataset_id,True)
        (self.root/'decoder-datasets'/self.dataset_id/'documents.jsonl').write_text('{}')
        with self.assertRaisesRegex(ValueError,'hash mismatch'): languages.analyze(self.root,self.dataset_id,True)

    def test_native_adapter_validates_output_and_uses_stdin_without_shell(self):
        with patch.object(languages.platform,'system',return_value='Darwin'), patch.object(languages.subprocess,'run') as run:
            run.return_value=Mock(stdout='[{"en":0.99}]')
            self.assertEqual(languages._recognize([ENGLISH]),[{'en':.99}])
            args,kwargs=run.call_args
            self.assertNotIn(ENGLISH,str(args))
            self.assertEqual(json.loads(kwargs['input']),[ENGLISH])
            self.assertNotIn('shell',kwargs)
            for invalid in ('{}','[{"en":NaN}]','[{"en":true}]','[{"en":1.1}]','[{"invalid code":0.9}]','[]'):
                run.return_value=Mock(stdout=invalid)
                self.assertIsNone(languages._recognize([ENGLISH]))
            run.side_effect=subprocess.TimeoutExpired('osascript',10)
            self.assertIsNone(languages._recognize([ENGLISH]))
        with patch.object(languages.platform,'system',return_value='Linux'), patch.object(languages.subprocess,'run') as run:
            self.assertIsNone(languages._recognize([ENGLISH]))
            run.assert_not_called()


if __name__=='__main__':unittest.main()
