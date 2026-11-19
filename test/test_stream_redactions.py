import base64
import hashlib
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_streams as streams, decoder_stream_indexes as indexes, decoder_stream_redactions as redactions, decoder_stream_permissions as permissions, decoder_stream_exports as exports


class StreamRedactionTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        lines=[f'Local unique document {i} contact person@example.test and orchard harvest' for i in range(230)]
        lines+=['Same document contact first@example.test','Same document contact second@example.test',lines[0]]
        raw=('\n'.join(lines)+'\n').encode()
        source=streams.create(self.root,'contacts.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
        streams.append(self.root,source['id'],0,base64.b64encode(raw).decode(),True);streams.seal(self.root,source['id'],True)
        self.parent=indexes.begin(self.root,source['id'],True)
        while self.parent['status']!='complete':self.parent=indexes.step(self.root,self.parent['id'],True)
        review=permissions.review(self.root,self.parent['id'])
        permissions.declare(self.root,self.parent['id'],True,review,'user_created','Synthetic fixture only.')

    def test_resumable_filtered_index_keeps_lineage_and_originals_with_global_rededuplication(self):
        folder=indexes._folder(self.root,self.parent['id']);before={p.name:p.read_bytes() for p in folder.iterdir()}
        child=redactions.begin(self.root,self.parent['id'],True,self.parent)
        child=redactions.step(self.root,child['id'],True);self.assertEqual(child['processed_parent_records'],100)
        importlib.reload(redactions);self.assertEqual(indexes.read(self.root,child['id']),child)
        while child['status']!='complete':child=redactions.step(self.root,child['id'],True)
        self.assertEqual(child['processed_parent_records'],232);self.assertEqual(child['filtered_records'],232)
        self.assertEqual(child['unique_records'],231);self.assertEqual(child['duplicate_records'],2)
        self.assertEqual(child['source_sha256'],self.parent['source_sha256'])
        with indexes._connect(indexes._folder(self.root,child['id'])/'records.sqlite3',True) as db:
            rows=db.execute('SELECT text,occurrences FROM documents').fetchall()
            self.assertTrue(all('@' not in text and '[CONTACT_REDACTED]' in text for text,_ in rows))
            self.assertEqual(sum(n for _,n in rows),233)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM redaction_lineage').fetchone()[0],232)
            self.assertEqual(db.execute('SELECT SUM(replacement_spans) FROM redaction_lineage').fetchone()[0],232)
        declaration=child['derivation']['parent_source_permission_review']['latest_declaration']
        self.assertEqual(declaration['note'],'Synthetic fixture only.');self.assertFalse(declaration['training_approved'])
        review=exports.review(self.root,child['id']);self.assertEqual(exports.seal(self.root,child['id'],True,review)['revision'],review['revision'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
        self.assertFalse((self.root/'decoder-trials').exists())
        with self.assertRaisesRegex(ValueError,'already contact-filtered'):redactions.begin(self.root,child['id'],True,child)

    def test_failed_batch_source_and_code_changes_preserve_progress(self):
        child=redactions.begin(self.root,self.parent['id'],True,self.parent)
        original=redactions.datasets._privacy_findings;calls=[]
        def interrupted(*args):
            calls.append(1)
            if len(calls)==5:raise RuntimeError('interrupted after partial batch')
            return original(*args)
        with patch.object(redactions.datasets,'_privacy_findings',side_effect=interrupted):
            with self.assertRaises(RuntimeError):redactions.step(self.root,child['id'],True)
        with indexes._connect(indexes._folder(self.root,child['id'])/'records.sqlite3',True) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM redaction_lineage').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM documents').fetchone()[0],0)
        self.assertEqual(indexes.read(self.root,child['id']),child)
        with patch.object(redactions,'_implementation',return_value='changed'):
            with self.assertRaisesRegex(ValueError,'implementation changed'):redactions.step(self.root,child['id'],True)
        with (indexes._folder(self.root,self.parent['id'])/'records.sqlite3').open('ab') as output:output.write(b'changed')
        with self.assertRaisesRegex(ValueError,'Parent index changed'):redactions.step(self.root,child['id'],True)
        self.assertEqual(indexes.read(self.root,child['id']),child)

    def test_consent_and_stale_parent_reviews_reject_without_creating_children(self):
        for confirmed,reviewed in ((False,self.parent),(True,dict(self.parent,revision='stale'))):
            with self.assertRaises(ValueError):redactions.begin(self.root,self.parent['id'],confirmed,reviewed)
        self.assertEqual(len(list((self.root/'decoder-stream-indexes').iterdir())),1)
        child=redactions.begin(self.root,self.parent['id'],True,self.parent)
        with self.assertRaises(ValueError):redactions.step(self.root,child['id'],False)


if __name__=='__main__':unittest.main()
