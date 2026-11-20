import importlib
import json
import math
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_stream_unigram_candidates as candidates,decoder_stream_indexes as indexes,decoder_stream_permissions as permissions,decoder_stream_fitted_tokenizer_evaluations as comparisons
from test_stream_character_bpe import fixture


def finish(root,record):
    while record['status']!='complete':record=candidates.step(root,record['id'],True)
    return record


class UnigramCandidateTests(unittest.TestCase):
    def test_complete_training_counts_ranking_initial_mass_and_restart_without_em(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            record=candidates.begin(root,index['id'],True,candidates.review(root,index['id'],64))
            with patch.object(candidates,'MAX_BATCH_RECORDS',3),patch.object(candidates,'MAX_COUNTER_ENTRIES',7):record=candidates.step(root,record['id'],True)
            self.assertEqual(record['processed_records'],3);importlib.reload(candidates);self.assertEqual(candidates.read(root,record['id']),record)
            record=finish(root,record)
            with indexes._connect(indexes._folder(root,index['id'])/'records.sqlite3',True) as db:rows=db.execute('SELECT group_sha256,text,split FROM documents ORDER BY group_sha256').fetchall()
            train=[text for group,text,split in rows if split=='train'];self.assertGreater(len(train),16)
            alphabet=Counter(''.join(train));substrings=Counter()
            for text in train:
                for word in text.split():
                    for start in range(len(word)):
                        for length in range(2,min(8,len(word)-start)+1):substrings[word[start:start+length]]+=1
            selected=sorted((piece for piece,count in substrings.items() if count>=2),key=lambda piece:(-substrings[piece]*(len(piece)-1),piece))[:64-len(alphabet)]
            pieces=sorted(alphabet)+sorted(selected);expected=[alphabet[p] if len(p)==1 else substrings[p] for p in pieces]
            initial=record['initializer'];self.assertEqual(initial['pieces'],pieces);self.assertEqual(initial['counts'],expected)
            self.assertEqual(initial['distinct_training_substrings'],len(substrings));self.assertEqual(initial['initial_probabilities'],[value/sum(expected) for value in expected]);self.assertAlmostEqual(math.fsum(initial['initial_probabilities']),1)
            chain=candidates.digest([])
            for group,text,split in rows:
                if split=='train':chain=candidates.digest({'previous':chain,'group_sha256':group})
            self.assertEqual(record['training_chain_sha256'],chain);self.assertEqual(record['training_bytes'],sum(len(text.encode()) for text in train))
            self.assertFalse(record['tokenizer_trained']);self.assertEqual(initial['em_updates'],0);self.assertFalse(record['model_training_enabled'])
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()));self.assertEqual(candidates.step(root,record['id'],True),record)
            self.assertEqual(candidates.list_reports(root,index['id']),[record])
            with self.assertRaises(ValueError):comparisons._worker('unigram_candidates')

    def test_overflow_and_consent_stale_review_rollback(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root);review=candidates.review(root,index['id'],32)
            for cap in (True,31,513):
                with self.assertRaises(ValueError):candidates.review(root,index['id'],cap)
            with self.assertRaises(ValueError):candidates.begin(root,index['id'],False,review)
            with self.assertRaises(ValueError):candidates.begin(root,index['id'],True,{**review,'vocabulary_cap':64})
            record=candidates.begin(root,index['id'],True,review)
            with self.assertRaisesRegex(ValueError,'alphabet exceeds'):candidates.step(root,record['id'],True)
            self.assertEqual(candidates.read(root,record['id']),record)
            with indexes._connect(candidates._folder(root,record['id'])/'counts.sqlite3',True) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM alphabet').fetchone()[0],0)

    def test_transaction_publication_and_permission_recovery(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root);record=candidates.begin(root,index['id'],True,candidates.review(root,index['id'],64))
            with patch.object(candidates,'_write',side_effect=OSError('transaction interrupted')):
                with self.assertRaises(ValueError):candidates.step(root,record['id'],True)
            self.assertEqual(candidates.read(root,record['id']),record)
            with patch.object(candidates,'_publish',side_effect=OSError('publication interrupted')):
                with self.assertRaises(ValueError):candidates.step(root,record['id'],True)
            pending=candidates.read(root,record['id']);self.assertEqual(pending['status'],'awaiting_publication')
            complete=candidates.step(root,record['id'],True);self.assertEqual(complete['processed_records'],pending['processed_records'])
            other=candidates.begin(root,index['id'],True,candidates.review(root,index['id'],64));old=permissions.review(root,index['id']);permissions.declare(root,index['id'],True,old,'user_created','QA')
            with self.assertRaisesRegex(ValueError,'permissions changed'):candidates.step(root,other['id'],True)
            self.assertEqual(candidates.read(root,other['id']),other)

    def test_heldout_only_characters_and_long_training_records_without_cross_word_pieces(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            held=next(f'heldout Ω tail{i}' for i in range(10000) if int(candidates.digest(f'heldout Ω tail{i}')[:8],16)%100>=80)
            long=next('abcdefghij '*450+f'end{i}' for i in range(10000) if int(candidates.digest('abcdefghij '*450+f'end{i}')[:8],16)%100<80)
            index=fixture(root,[held,long]);record=finish(root,candidates.begin(root,index['id'],True,candidates.review(root,index['id'],64)))
            self.assertNotIn('Ω',record['initializer']['alphabet'])
            self.assertTrue(all(2<=len(piece)<=8 and not any(c.isspace() for c in piece) for piece in record['initializer']['pieces'][len(record['initializer']['alphabet']):]))
            self.assertGreater(record['training_bytes'],len(long.encode()))
            self.assertEqual(record['processed_records'],index['split_counts']['train'])

    def test_mid_batch_same_bytes_source_rewrite_preserves_counts_and_cursor(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root);record=candidates.begin(root,index['id'],True,candidates.review(root,index['id'],64))
            source=candidates.sources.streams.folder(root,index['source_id'])/'source.bin';binding=candidates.sources._binding;calls=0
            def changed(*args):
                nonlocal calls
                calls+=1
                if calls==2:source.write_bytes(source.read_bytes())
                return binding(*args)
            with patch.object(candidates.sources,'_binding',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'changed during'):candidates.step(root,record['id'],True)
            self.assertEqual(candidates.read(root,record['id']),record)
