import base64
from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from backend import decoder_streams as streams,decoder_stream_indexes as indexes,decoder_stream_overlap as overlap,decoder_stream_character_bpe as fits,decoder_stream_fitted_tokenizer_evaluations as scans,decoder_stream_learned_windows as windows,decoder_stream_learned_batches as batches


def finish(worker,root,record):
    while record['status']!='complete':record=worker.step(root,record['id'],True)
    return record


def pipeline(root,contaminated=False):
    lines=([' '.join([f'baseword{j}' for j in range(40)]+[f'tail{i}']) for i in range(40)] if contaminated else
           [' '.join(f'unique{i}word{j}' for j in range(20))+' café 世界 0123456789' for i in range(61)])
    raw=('\n'.join(lines)+'\n').encode();source=streams.create(root,'character-inputs.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
    streams.append(root,source['id'],0,base64.b64encode(raw).decode(),True);streams.seal(root,source['id'],True)
    index=finish(indexes,root,indexes.begin(root,source['id'],True))
    fitted=finish(fits,root,fits.begin(root,index['id'],True,fits.review(root,index['id'],64)))
    comparison=finish(scans,root,scans.begin(root,fitted['id'],True,fitted,'character_bpe'))
    evidence=finish(overlap,root,overlap.begin(root,index['id'],True))
    return fitted,comparison,evidence


class CharacterModelInputTests(unittest.TestCase):
    def test_version2_windows_exact_ids_provenance_masks_complete_splits_and_restart(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);fitted,comparison,evidence=pipeline(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            review=windows.review(root,comparison['id'],evidence['id'])
            self.assertEqual(review['model_input_profile']['vocabulary_size'],64)
            self.assertEqual(review['model_input_profile']['architecture_version'],1)
            record=windows.begin(root,comparison['id'],evidence['id'],True,review)
            self.assertEqual(record['schema_version'],2);self.assertEqual(record['format'],'almg-stream-learned-windows-v2')
            with patch.object(windows,'MAX_BATCH_RECORDS',3):record=windows.step(root,record['id'],True)
            self.assertEqual(record['processed_records'],3);importlib.reload(windows);self.assertEqual(windows.read(root,record['id']),record)
            record=finish(windows,root,record)
            _,_,codec,_=scans._binding(root,fitted['id'],'character_bpe',True)
            with indexes._connect(indexes._folder(root,record['index_id'])/'records.sqlite3',True) as db:
                source={group:(text,part,line,offset,sha) for group,text,part,line,offset,sha in db.execute('SELECT group_sha256,text,split,first_line,first_byte_offset,raw_line_sha256 FROM documents')}
            with indexes._connect(windows._folder(root,record['id'])/'windows.sqlite3',True) as db:
                rows=db.execute('SELECT group_sha256,token_offset,split,tokens FROM windows').fetchall()
            for group,offset,split,tokens in rows:
                self.assertEqual(json.loads(tokens),codec.encode(source[group][0])[offset:offset+17]);self.assertEqual(split,source[group][1])
            padded=False
            for split in ('train','validation','test'):
                seen=targets=0
                for batch in batches.iter_batches(root,record['id'],True,record,split,7):
                    self.assertEqual(batch['format'],'almg-stream-learned-model-batch-v2');self.assertEqual(batch['tokenizer_kind'],'character_bpe')
                    seen+=batch['rows'];targets+=batch['real_target_tokens']
                    for x,y,mask,length,ref in zip(batch['inputs'],batch['targets'],batch['loss_mask'],batch['sequence_lengths'],batch['provenance']):
                        text,part,line,offset,sha=source[ref['group']];ids=codec.encode(text)[ref['token_offset']:ref['token_offset']+17]
                        self.assertEqual(x,ids[:-1]+[0]*(16-length));self.assertEqual(y,ids[1:]+[0]*(16-length));self.assertEqual(mask,[1]*length+[0]*(16-length))
                        self.assertEqual(ref['first_line'],line);self.assertEqual(ref['raw_line_sha256'],sha);self.assertEqual(part,split)
                        self.assertTrue(all(0<=value<64 for value in x+y));padded|=length<16
                self.assertEqual(seen,record['window_counts'][split]);self.assertEqual(targets,sum(len(codec.encode(row[0]))-1 for row in source.values() if row[1]==split))
            self.assertTrue(padded);self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            self.assertFalse(record['training_approved']);self.assertFalse((root/'decoder-trials').exists())
            with self.assertRaises(ValueError):windows.begin(root,comparison['id'],evidence['id'],True,{**review,'model_input_profile':{}})

    def test_contamination_and_model_vocabulary_guards_precede_publication(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);fitted,comparison,evidence=pipeline(root,True)
            self.assertTrue(comparison['all_records_lossless']);self.assertGreater(evidence['cross_split_pairs'],0)
            with self.assertRaisesRegex(ValueError,'Cross-split'):windows.review(root,comparison['id'],evidence['id'])
            self.assertFalse((root/'decoder-stream-learned-windows').exists())
            invalid={'fit_kind':'character_bpe','status':'complete','all_records_lossless':True,'fit_id':'a'*32}
            with patch.object(scans,'read',return_value=invalid),patch.object(scans,'_binding',return_value=({'vocabulary_size':3},{},SimpleNamespace(pieces=[0,1,2]),{})):
                with self.assertRaisesRegex(ValueError,'between 4 and 512'):windows.review(root,'a'*32,'b'*32)

    def test_version2_transaction_failure_and_publication_recovery_keep_committed_progress(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);fitted,comparison,evidence=pipeline(root)
            review=windows.review(root,comparison['id'],evidence['id']);record=windows.begin(root,comparison['id'],evidence['id'],True,review)
            original=fits.StreamCharacterBPE.encode;calls=0
            def interrupted(codec,text):
                nonlocal calls
                calls+=1
                if calls==4:raise RuntimeError('injected character encoding interruption')
                return original(codec,text)
            with patch.object(fits.StreamCharacterBPE,'encode',interrupted):
                with self.assertRaises(RuntimeError):windows.step(root,record['id'],True)
            self.assertEqual(windows.read(root,record['id']),record)
            with patch.object(windows,'_publish',side_effect=OSError('injected v2 publication failure')):
                with self.assertRaises(OSError):windows.step(root,record['id'],True)
            pending=windows.read(root,record['id']);self.assertEqual(pending['schema_version'],2);self.assertEqual(pending['status'],'awaiting_publication')
            complete=windows.step(root,record['id'],True);self.assertEqual(complete['processed_records'],pending['processed_records'])
            self.assertEqual(windows.step(root,record['id'],True),complete)
