import base64
import hashlib
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_streams as streams, decoder_stream_indexes as indexes


class StreamRecordPageTests(unittest.TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        lines=[f'Record {i} local text contact person{i}@example.test for the review fixture.' for i in range(25)]
        lines.append(' '.join(f'word{i}' for i in range(300)))
        raw=('\n'.join(lines)+'\n').encode()
        source=streams.create(self.root,'review.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
        streams.append(self.root,source['id'],0,base64.b64encode(raw).decode(),True)
        streams.seal(self.root,source['id'],True)
        record=indexes.begin(self.root,source['id'],True)
        while record['status']!='complete':record=indexes.step(self.root,record['id'],True)
        self.record=record;self.index_id=record['id']

    def test_keyset_pages_cover_every_record_once_mask_contacts_and_preserve_files(self):
        folder=self.root/'decoder-stream-indexes'/self.index_id
        before={p.name:p.read_bytes() for p in folder.iterdir()}
        groups=[];cursor=None;rows=[]
        while True:
            page=indexes.record_page(self.root,self.index_id,True,cursor,limit=5)
            self.assertLessEqual(len(page['records']),5);self.assertTrue(page['read_only'])
            for row in page['records']:
                groups.append(row['group']);rows.append(row)
                self.assertLessEqual(len(row['text_excerpt']),512)
                self.assertNotIn('@example.test',row['text_excerpt'])
                if row['privacy_matches']:
                    self.assertTrue(row['detected_contacts_masked'])
                    self.assertIn('[CONTACT_REDACTED]',row['text_excerpt'])
                    self.assertEqual(row['source_sha256'],self.record['source_sha256'])
            cursor=page['next_cursor']
            if cursor is None:break
        self.assertEqual(len(groups),26);self.assertEqual(groups,sorted(set(groups)))
        self.assertTrue(any(row['excerpt_truncated'] for row in rows))
        self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_split_filters_and_bound_cursors_reject_stale_or_changed_context(self):
        for split in ('train','validation','test'):
            page=indexes.record_page(self.root,self.index_id,True,split=split,limit=20)
            self.assertTrue(all(row['split']==split for row in page['records']))
        first=indexes.record_page(self.root,self.index_id,True,limit=1)
        cursor=first['next_cursor'];self.assertIsNotNone(cursor)
        for changed in (dict(cursor,revision='stale'),dict(cursor,after='bad'),dict(cursor,split='test'),{}):
            with self.assertRaisesRegex(ValueError,'cursor changed'):indexes.record_page(self.root,self.index_id,True,changed)
        for confirmed,split,limit in ((False,'all',10),(True,'wrong',10),(True,'all',True),(True,'all',21)):
            with self.assertRaises(ValueError):indexes.record_page(self.root,self.index_id,confirmed,split=split,limit=limit)

    def test_dense_contact_findings_are_capped_while_every_excerpt_match_is_masked(self):
        raw=(' '.join(f'p{i}@example.test' for i in range(30))+'\n').encode()
        source=streams.create(self.root,'contacts.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
        streams.append(self.root,source['id'],0,base64.b64encode(raw).decode(),True)
        streams.seal(self.root,source['id'],True)
        record=indexes.begin(self.root,source['id'],True)
        record=indexes.step(self.root,record['id'],True)
        row=indexes.record_page(self.root,record['id'],True)['records'][0]
        self.assertEqual(row['privacy_matches'],30)
        self.assertEqual(len(row['privacy_findings']),20)
        self.assertTrue(row['privacy_findings_truncated'])
        self.assertNotIn('@example.test',row['text_excerpt'])
        self.assertLessEqual(len(row['text_excerpt']),512)

    def test_unfinished_or_corrupt_index_cannot_be_reviewed(self):
        source_id=self.record['source_id'];pending=indexes.begin(self.root,source_id,True)
        with self.assertRaisesRegex(ValueError,'Complete text indexing'):indexes.record_page(self.root,pending['id'],True)
        database=self.root/'decoder-stream-indexes'/self.index_id/'records.sqlite3'
        with sqlite3.connect(database) as connection:connection.execute('UPDATE documents SET text=?',('changed',))
        with self.assertRaisesRegex(ValueError,'integrity'):indexes.record_page(self.root,self.index_id,True)


if __name__=='__main__':unittest.main()
