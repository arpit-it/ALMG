import base64
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_streams as streams, decoder_stream_indexes as indexes, decoder_stream_audits as audits


class FullIndexAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        healthy=' '.join('term'+chr(97+i//26)+chr(97+i%26) for i in range(32))
        contact=healthy+' contact audit@example.test'
        raw=('\n'.join([healthy,'echo '*64,contact,contact,'café'])+'\n').encode()
        source=streams.create(self.root,'source.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
        streams.append(self.root,source['id'],0,base64.b64encode(raw).decode(),True);streams.seal(self.root,source['id'],True)
        self.index=indexes.begin(self.root,source['id'],True)
        while self.index['status']!='complete':self.index=indexes.step(self.root,self.index['id'],True)

    def test_scan_all_unique_records_resume_and_preserve_occurrences_and_originals(self):
        folder=self.root/'decoder-stream-indexes'/self.index['id'];before={p.name:p.read_bytes() for p in folder.iterdir()}
        record=audits.begin(self.root,self.index['id'],True)
        with patch.object(audits,'MAX_BATCH_RECORDS',2):
            record=audits.step(self.root,record['id'],True)
            self.assertEqual(record['processed_records'],2);self.assertEqual(record['status'],'scanning')
            self.assertEqual(audits.read(self.root,record['id']),record)
            record=audits.step(self.root,record['id'],True)
        self.assertEqual(record['status'],'complete')
        self.assertEqual((record['processed_records'],record['source_occurrences']),(4,5))
        self.assertEqual((record['hygiene_review_records'],record['privacy_records'],record['finding_records']),(2,1,3))
        self.assertEqual((record['privacy_matches'],record['privacy_match_occurrences']),(1,2))
        self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
        self.assertNotIn(b'audit@example.test',(self.root/'decoder-stream-audits'/record['id']/'audit.sqlite3').read_bytes())
        self.assertEqual(audits.step(self.root,record['id'],True),record)
        self.assertEqual(audits.list_audits(self.root,self.index['id']),[record])
        rows=[];cursor=None
        while True:
            page=audits.record_page(self.root,record['id'],True,cursor,limit=1);rows.extend(page['records'])
            cursor=page['next_cursor']
            if cursor is None:break
        self.assertEqual(len({row['group'] for row in rows}),3)
        self.assertTrue(all(row['text_omitted'] for row in rows))
        self.assertTrue(all(row['source_sha256']==self.index['source_sha256'] for row in rows))
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_batch_error_rolls_back_counts_and_findings_then_retry_succeeds(self):
        record=audits.begin(self.root,self.index['id'],True)
        original=audits.datasets._text_hygiene;calls=[]
        def interrupted(text,words):
            calls.append(1)
            if len(calls)==3:raise ValueError('interrupted local heuristic')
            return original(text,words)
        with patch.object(audits.datasets,'_text_hygiene',side_effect=interrupted):
            with self.assertRaisesRegex(ValueError,'interrupted local'):audits.step(self.root,record['id'],True)
        self.assertEqual(audits.read(self.root,record['id']),record)
        with sqlite3.connect(self.root/'decoder-stream-audits'/record['id']/'audit.sqlite3') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM findings').fetchone()[0],0)
        self.assertEqual(audits.step(self.root,record['id'],True)['processed_records'],4)

    def test_interrupted_publication_and_cursor_or_manifest_tampering(self):
        record=audits.begin(self.root,self.index['id'],True)
        with patch.object(audits,'_publish',side_effect=OSError('interrupted publication')):
            with self.assertRaises(OSError):audits.step(self.root,record['id'],True)
        self.assertEqual(audits.read(self.root,record['id'])['status'],'awaiting_publication')
        complete=audits.step(self.root,record['id'],True)
        self.assertEqual(complete['processed_records'],4)
        page=audits.record_page(self.root,record['id'],True,limit=1)
        with self.assertRaisesRegex(ValueError,'cursor changed'):
            audits.record_page(self.root,record['id'],True,dict(page['next_cursor'],revision='stale'))
        path=self.root/'decoder-stream-audits'/record['id']/'manifest.json'
        changed=dict(complete,processed_records=999);path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'integrity'):audits.read(self.root,record['id'])

    def test_consent_implementation_and_source_changes_are_rejected(self):
        with self.assertRaises(ValueError):audits.begin(self.root,self.index['id'],False)
        record=audits.begin(self.root,self.index['id'],True)
        with self.assertRaises(ValueError):audits.step(self.root,record['id'],False)
        with self.assertRaisesRegex(ValueError,'Complete the audit'):audits.record_page(self.root,record['id'],True)
        with patch.object(audits,'_implementation',return_value='changed'):
            with self.assertRaisesRegex(ValueError,'implementation changed'):audits.step(self.root,record['id'],True)
        with patch.object(audits,'_runtime',return_value={'python':'changed'}):
            with self.assertRaisesRegex(ValueError,'implementation changed'):audits.step(self.root,record['id'],True)
        path=self.root/'decoder-stream-indexes'/self.index['id']/'records.sqlite3'
        with sqlite3.connect(path) as db:db.execute('UPDATE documents SET text=?',('changed source',))
        with self.assertRaisesRegex(ValueError,'source index changed'):audits.step(self.root,record['id'],True)


if __name__=='__main__':unittest.main()
