import base64
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_html as html,decoder_html_preparations as drafts,decoder_datasets as datasets


class HtmlPreparationTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.documents=[{'name':f'original-{i}.html','data':base64.b64encode(f'<p>Local source {i} with unique topic {word} and several words.</p>'.encode()).decode()}
                        for i,word in enumerate(('orchard','astronomy','ocean'))]
        self.review=html.review(self.documents)

    def test_original_inputs_survive_reload_and_explicit_prepare_is_idempotent(self):
        draft=drafts.create(self.root,self.documents,True,self.review)
        before=(drafts._folder(self.root,draft['id'])/'inputs.json').read_bytes()
        self.assertFalse((self.root/'decoder-datasets').exists())
        importlib.reload(drafts);self.assertEqual(drafts.read(self.root,draft['id']),draft)
        with self.assertRaises(ValueError):drafts.resume(self.root,draft['id'],False)
        dataset=drafts.resume(self.root,draft['id'],True)
        self.assertEqual(dataset['id'],draft['id']);self.assertEqual(datasets.read(self.root,draft['id']),dataset)
        self.assertEqual(drafts.resume(self.root,draft['id'],True),dataset)
        self.assertEqual(len(list((self.root/'decoder-datasets').iterdir())),1)
        self.assertEqual((drafts._folder(self.root,draft['id'])/'inputs.json').read_bytes(),before)
        self.assertEqual(drafts.list_drafts(self.root)[0]['status'],'complete')
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_publication_followed_by_record_failure_recovers_same_dataset(self):
        draft=drafts.create(self.root,self.documents,True,self.review)
        with patch.object(drafts,'_write',side_effect=OSError('simulated record-write failure')):
            with self.assertRaises(OSError):drafts.resume(self.root,draft['id'],True)
        self.assertEqual(drafts.read(self.root,draft['id'])['status'],'awaiting_preparation')
        published=datasets.read(self.root,draft['id'])
        importlib.reload(drafts)
        self.assertEqual(drafts.resume(self.root,draft['id'],True),published)
        self.assertEqual(len(list((self.root/'decoder-datasets').iterdir())),1)

    def test_stale_reviews_tampered_inputs_and_changed_code_fail_closed(self):
        with self.assertRaises(ValueError):drafts.create(self.root,self.documents,False,self.review)
        with self.assertRaises(ValueError):drafts.create(self.root,self.documents,True,dict(self.review,revision='changed'))
        draft=drafts.create(self.root,self.documents,True,self.review)
        with patch.object(drafts,'_implementation',return_value='changed'):
            self.assertFalse(drafts.read(self.root,draft['id'])['implementation_current'])
            with self.assertRaisesRegex(ValueError,'implementation changed'):drafts.resume(self.root,draft['id'],True)
        path=drafts._folder(self.root,draft['id'])/'inputs.json';path.write_text('{}')
        with self.assertRaises(ValueError):drafts.read(self.root,draft['id'])
        with self.assertRaises(ValueError):drafts.resume(self.root,draft['id'],True)
        self.assertFalse((self.root/'decoder-datasets').exists())


if __name__=='__main__':unittest.main()
