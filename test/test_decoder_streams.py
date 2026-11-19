import base64
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_streams as streams


class StreamedSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.data=b'local source bytes\n'*10000
        self.record=streams.create(self.root,'source.txt',len(self.data),hashlib.sha256(self.data).hexdigest(),True)

    def send(self,offset,data):
        return streams.append(self.root,self.record['id'],offset,base64.b64encode(data).decode(),True)

    def test_chunked_resume_retries_and_seal_preserve_original_hash(self):
        chunk=self.data[:65536]
        record=self.send(0,chunk)
        self.assertEqual(record['received_bytes'],65536)
        self.assertEqual(self.send(0,chunk),record)
        self.assertEqual(streams.read(self.root,record['id']),record)
        for offset in range(65536,len(self.data),65536):record=self.send(offset,self.data[offset:offset+65536])
        sealed=streams.seal(self.root,record['id'],True)
        self.assertEqual(sealed['status'],'stored_not_prepared')
        self.assertEqual((streams.folder(self.root,record['id'])/'source.bin').read_bytes(),self.data)
        self.assertEqual(streams.seal(self.root,record['id'],True),sealed)
        with self.assertRaisesRegex(ValueError,'already stored'):self.send(0,chunk)
        self.assertFalse((self.root/'decoder-datasets').exists())
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_interrupted_offset_write_discards_only_uncommitted_tail(self):
        self.send(0,self.data[:65536])
        with patch.object(streams,'_write',side_effect=OSError('interrupted commit')):
            with self.assertRaises(OSError):self.send(65536,self.data[65536:131072])
        path=streams.folder(self.root,self.record['id'])/'source.bin'
        self.assertEqual(path.stat().st_size,131072)
        record=streams.read(self.root,self.record['id'])
        self.assertEqual(record['received_bytes'],65536)
        self.assertEqual(path.read_bytes(),self.data[:65536])
        self.assertEqual(self.send(65536,self.data[65536:131072])['received_bytes'],131072)

    def test_offsets_changed_retries_bounds_consent_and_incomplete_seal_reject(self):
        with self.assertRaises(ValueError):streams.create(self.root,'other',3,'0'*64,False)
        for offset,data in ((1,b'x'),(False,b'x'),(0,b'x'*65537)):
            with self.assertRaises(ValueError):self.send(offset,data)
        self.send(0,b'local')
        with self.assertRaisesRegex(ValueError,'Retried chunk'):self.send(0,b'wrong')
        with self.assertRaisesRegex(ValueError,'remaining bytes'):streams.seal(self.root,self.record['id'],True)
        with self.assertRaises(ValueError):streams.append(self.root,self.record['id'],5,'eA==',False)
        self.assertEqual(streams.read(self.root,self.record['id'])['received_bytes'],5)

    def test_final_hash_mismatch_never_marks_source_ready(self):
        bad=streams.create(self.root,'bad',3,'0'*64,True)
        streams.append(self.root,bad['id'],0,base64.b64encode(b'bad').decode(),True)
        with self.assertRaisesRegex(ValueError,'hash mismatch'):streams.seal(self.root,bad['id'],True)
        self.assertEqual(streams.read(self.root,bad['id'])['status'],'uploading')


if __name__=='__main__':unittest.main()
