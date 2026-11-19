import base64
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_streams as streams, decoder_stream_indexes as indexes


class StreamIndexTests(unittest.TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)

    def source(self,data):
        record=streams.create(self.root,'text.txt',len(data),hashlib.sha256(data).hexdigest(),True)
        for offset in range(0,len(data),65536):
            streams.append(self.root,record['id'],offset,base64.b64encode(data[offset:offset+65536]).decode(),True)
        return streams.seal(self.root,record['id'],True)

    def test_bounded_steps_normalize_deduplicate_and_preserve_first_source_offsets(self):
        data='\ufeffcafe\u0301 local text\n café  local text \n\nsecond distinct line\nthird line\n'.encode()
        source=self.source(data);record=indexes.begin(self.root,source['id'],True)
        self.assertEqual(record['offset'],0)
        with patch.object(indexes,'MAX_STEP_LINES',2):
            record=indexes.step(self.root,record['id'],True)
            self.assertEqual((record['lines'],record['unique_records'],record['duplicate_records']),(2,1,1))
            self.assertLess(record['offset'],len(data))
            self.assertEqual(indexes.read(self.root,record['id']),record)
            while record['status']!='complete':record=indexes.step(self.root,record['id'],True)
        self.assertEqual((record['lines'],record['empty_lines'],record['unique_records'],record['duplicate_records']),(5,1,3,1))
        self.assertEqual(record['offset'],len(data))
        with sqlite3.connect(self.root/'decoder-stream-indexes'/record['id']/'records.sqlite3') as db:
            rows=db.execute('SELECT text,first_line,first_byte_offset,raw_line_sha256,occurrences,split FROM documents').fetchall()
        first=next(row for row in rows if row[0]=='café local text')
        self.assertEqual(first[1:3],(1,0));self.assertEqual(first[4],2)
        self.assertEqual(first[3],hashlib.sha256(data.splitlines(keepends=True)[0]).hexdigest())
        self.assertEqual(sum(record['split_counts'].values()),3)
        self.assertEqual(indexes.step(self.root,record['id'],True),record)
        self.assertEqual(indexes.list_indexes(self.root,source['id']),[record])
        self.assertEqual((streams.folder(self.root,source['id'])/'source.bin').read_bytes(),data)
        self.assertFalse((self.root/'decoder-datasets').exists());self.assertFalse((self.root/'decoder-trials').exists())

    def test_invalid_utf8_batch_rolls_back_without_losing_prior_progress(self):
        source=self.source(b'valid first line\n\xffinvalid\n')
        record=indexes.begin(self.root,source['id'],True)
        with patch.object(indexes,'MAX_STEP_LINES',1):record=indexes.step(self.root,record['id'],True)
        before=indexes.read(self.root,record['id'])
        with self.assertRaisesRegex(ValueError,'Invalid or unsupported UTF-8'):indexes.step(self.root,record['id'],True)
        self.assertEqual(indexes.read(self.root,record['id']),before)
        self.assertFalse((self.root/'decoder-stream-indexes'/record['id']/'manifest.json').exists())
        too_long=self.source(b'x'*65536+b'\n')
        record=indexes.begin(self.root,too_long['id'],True)
        with self.assertRaisesRegex(ValueError,'exceeds 65536'):indexes.step(self.root,record['id'],True)
        self.assertEqual(indexes.read(self.root,record['id'])['offset'],0)

    def test_interrupted_publication_resumes_without_reprocessing_or_duplicate_counts(self):
        source=self.source(b'one local line\none local line\nanother line\n')
        record=indexes.begin(self.root,source['id'],True)
        with patch.object(indexes,'_publish',side_effect=OSError('interrupted publication')):
            with self.assertRaises(OSError):indexes.step(self.root,record['id'],True)
        pending=indexes.read(self.root,record['id']);self.assertEqual(pending['status'],'awaiting_publication')
        complete=indexes.step(self.root,record['id'],True)
        self.assertEqual((complete['lines'],complete['unique_records'],complete['duplicate_records']),(3,2,1))
        self.assertEqual(indexes.read(self.root,record['id']),complete)

    def test_source_changes_consent_stale_implementation_and_manifest_tampering_reject(self):
        source=self.source(b'one local line\nanother local line\n')
        with self.assertRaises(ValueError):indexes.begin(self.root,source['id'],False)
        record=indexes.begin(self.root,source['id'],True)
        with self.assertRaises(ValueError):indexes.step(self.root,record['id'],False)
        with patch.object(indexes,'_implementation',return_value='changed'):
            with self.assertRaisesRegex(ValueError,'implementation changed'):indexes.step(self.root,record['id'],True)
        complete=indexes.step(self.root,record['id'],True)
        path=self.root/'decoder-stream-indexes'/record['id']/'manifest.json'
        changed=dict(complete,split_counts={'train':999});path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'integrity'):indexes.read(self.root,record['id'])
        record=indexes.begin(self.root,source['id'],True)
        (streams.folder(self.root,source['id'])/'source.bin').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Original source changed'):indexes.step(self.root,record['id'],True)


if __name__=='__main__':unittest.main()
