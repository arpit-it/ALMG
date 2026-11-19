import base64
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_streams as streams,decoder_stream_indexes as indexes,decoder_stream_token_stats as stats,decoder_stream_tokenizers as tokenizers,decoder_stream_overlap as overlap,decoder_stream_windows as windows,decoder_stream_batches as batches
from backend.decoder_tokenizer import ByteTokenizer


class StreamBatchTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        lines=[' '.join(f'unique{i}word{j}' for j in range(20)) for i in range(61)];raw=('\n'.join(lines)+'\n').encode()
        source=streams.create(self.root,'batches.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
        streams.append(self.root,source['id'],0,base64.b64encode(raw).decode(),True);streams.seal(self.root,source['id'],True)
        index=indexes.begin(self.root,source['id'],True)
        while index['status']!='complete':index=indexes.step(self.root,index['id'],True)
        report=stats.begin(self.root,index['id'],True)
        while report['status']!='complete':report=stats.step(self.root,report['id'],True)
        tokenizer=tokenizers.prepare(self.root,report['id'],True,report)
        evidence=overlap.begin(self.root,index['id'],True)
        while evidence['status']!='complete':evidence=overlap.step(self.root,evidence['id'],True)
        self.record=windows.begin(self.root,tokenizer['id'],evidence['id'],True,{'index':index,'tokenizer':tokenizer,'overlap':evidence})
        while self.record['status']!='complete':self.record=windows.step(self.root,self.record['id'],True)
        self.index=index

    def test_padded_batches_match_source_targets_masks_and_split_populations(self):
        source_folder=indexes._folder(self.root,self.index['id']);before={p.name:p.read_bytes() for p in source_folder.iterdir()}
        with indexes._connect(source_folder/'records.sqlite3',True) as db:source={row[0]:row[1:] for row in db.execute('SELECT group_sha256,text,split FROM documents')}
        cursor=None;seen=set();targets=0;saw_padding=False;codec=ByteTokenizer('0'*64)
        while True:
            batch=batches.read_batch(self.root,self.record['id'],True,self.record,cursor,'train',16)
            self.assertLessEqual(batch['rows'],16);self.assertFalse(batch['training_approved'])
            for inputs,labels,mask,length,ref in zip(batch['inputs'],batch['targets'],batch['loss_mask'],batch['sequence_lengths'],batch['provenance']):
                self.assertEqual(len(inputs),16);self.assertEqual(len(labels),16);self.assertEqual(len(mask),16)
                text,split=source[ref['group']];self.assertEqual(split,'train');start=ref['token_offset'];ids=codec.encode(text)[start:start+17]
                self.assertEqual(inputs[:length],ids[:-1]);self.assertEqual(labels[:length],ids[1:])
                self.assertEqual(mask,[1]*length+[0]*(16-length))
                self.assertTrue(all(value==0 for value in inputs[length:]+labels[length:]))
                self.assertNotIn((ref['group'],start),seen);seen.add((ref['group'],start));saw_padding|=length<16
            targets+=batch['real_target_tokens'];cursor=batch['next_cursor']
            if cursor is None:break
        self.assertTrue(saw_padding)
        self.assertEqual(len(seen),self.record['window_counts']['train'])
        self.assertEqual(targets,sum(len(codec.encode(text))-1 for text,split in source.values() if split=='train'))
        for split in ('validation','test'):
            batch=batches.read_batch(self.root,self.record['id'],True,self.record,split=split)
            self.assertTrue(all(ref['split']==split for ref in batch['provenance']))
        self.assertEqual(before,{p.name:p.read_bytes() for p in source_folder.iterdir()})
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_consent_review_limits_and_cross_split_cursors_reject(self):
        with self.assertRaises(ValueError):batches.read_batch(self.root,self.record['id'],False,self.record)
        with self.assertRaises(ValueError):batches.read_batch(self.root,self.record['id'],True,{})
        for size in (True,0,17):
            with self.assertRaises(ValueError):batches.read_batch(self.root,self.record['id'],True,self.record,batch_size=size)
        first=batches.read_batch(self.root,self.record['id'],True,self.record)
        with self.assertRaises(ValueError):batches.read_batch(self.root,self.record['id'],True,self.record,first['next_cursor'],'test')
        with self.assertRaises(ValueError):batches.read_batch(self.root,self.record['id'],True,self.record,split='all')

    def test_changed_source_evidence_rejects_without_mutating_prepared_windows(self):
        folder=windows._folder(self.root,self.record['id']);before={p.name:p.read_bytes() for p in folder.iterdir()}
        database=indexes._folder(self.root,self.index['id'])/'records.sqlite3'
        with database.open('ab') as output:output.write(b'changed')
        with self.assertRaises(ValueError):batches.read_batch(self.root,self.record['id'],True,self.record)
        self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})


if __name__=='__main__':unittest.main()
