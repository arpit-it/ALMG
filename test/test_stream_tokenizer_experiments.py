import base64
import hashlib
import importlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from backend import decoder_streams as streams, decoder_stream_indexes as indexes
from backend import decoder_stream_tokenizer_experiments as experiments, decoder_stream_permissions as permissions
from backend.decoder_special_tokens import SpecialTokenizer, restore_base
from backend.run_manifest import digest


def fixture(root):
    texts=[f'local record {i} banana bandana café 世界 abcdefghijklmnopqrstuvwxyz' for i in range(180)]
    texts += ['oversized '+('abcdefghij '*450)+str(i) for i in range(40)]
    data=('\n'.join(texts+[texts[0]])+'\n').encode()
    source=streams.create(root,'tokenizer-stream.txt',len(data),hashlib.sha256(data).hexdigest(),True)
    for offset in range(0,len(data),65536):streams.append(root,source['id'],offset,base64.b64encode(data[offset:offset+65536]).decode(),True)
    source=streams.seal(root,source['id'],True)
    index=indexes.begin(root,source['id'],True)
    while index['status']!='complete':index=indexes.step(root,index['id'],True)
    return source,index


class StreamTokenizerTests(unittest.TestCase):
    def test_sample_is_bounded_whole_records_training_only_fit_provenance_and_export(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,index=fixture(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            config={'algorithm':'byte_level_bpe','vocabulary_cap':320}
            reviewed=experiments.review(root,index['id'],config)
            self.assertEqual(reviewed['sample_split_counts'],{'train':16,'validation':8,'test':8})
            self.assertTrue(all(row['utf8_bytes']<=4096 for row in reviewed['sample_records']))
            self.assertLess(sum(reviewed['sample_split_counts'].values()),index['unique_records'])
            self.assertFalse(any('text' in row for row in reviewed['sample_records']))
            self.assertGreater(index['duplicate_records'],0)
            record=experiments.train(root,index['id'],True,reviewed)
            folder=experiments._folder(root,record['id'])
            model=restore_base(json.loads((folder/'tokenizer.json').read_text()))
            with indexes._connect(indexes._folder(root,index['id'])/'records.sqlite3',True) as db:
                by_group=dict(db.execute('SELECT group_sha256,text FROM documents'))
            train=[by_group[row['group_sha256']] for row in reviewed['sample_records'] if row['split']=='train']
            self.assertEqual(model.artifact(),type(model).fit(train,320).artifact())
            self.assertEqual(model.training_sha256,digest(train))
            for split in ('train','validation','test'):
                self.assertEqual(record['comparison'][split]['documents'],reviewed['sample_split_counts'][split])
                self.assertTrue(record['comparison'][split]['round_trip_verified'])
                self.assertEqual(record['comparison'][split]['used_for_fitting'],split=='train')
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            self.assertFalse((root/'decoder-trials').exists());self.assertFalse(record['model_training_enabled'])
            exported=experiments.export(root,record['id'],True,record)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported['data']))) as archive:
                self.assertEqual(set(archive.namelist()),{'manifest.json','tokenizer.json'})
                self.assertEqual(json.loads(archive.read('manifest.json')),record)
                self.assertEqual(restore_base(json.loads(archive.read('tokenizer.json'))).artifact(),model.artifact())
            importlib.reload(experiments)
            self.assertEqual(experiments.read(root,record['id']),record)
            self.assertEqual(experiments.list_experiments(root,index['id']),[record])

    def test_character_and_unigram_special_codecs_reload_and_sample_config_bound(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);_,index=fixture(root)
            for algorithm in ('character_bpe','unigram'):
                config={'algorithm':algorithm,'vocabulary_cap':128,'special_tokens':{'bos':'<B>','eos':'<E>','unk':'<U>'},'unknown_policy':'replace'}
                review=experiments.review(root,index['id'],config)
                record=experiments.train(root,index['id'],True,review)
                artifact=json.loads((experiments._folder(root,record['id'])/'tokenizer.json').read_text())
                model=SpecialTokenizer.restore(artifact)
                self.assertEqual(model.decode(model.encode('banana café 世界')),'banana café 世界')
                self.assertEqual(experiments.read(root,record['id']),record)
                self.assertEqual(record['config'],config)

    def test_confirmation_stale_permissions_and_source_changes_reject_without_publication(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,index=fixture(root)
            review=experiments.review(root,index['id'],{'vocabulary_cap':320})
            with self.assertRaises(ValueError):experiments.train(root,index['id'],False,review)
            with self.assertRaises(ValueError):experiments.train(root,index['id'],True,{})
            old=permissions.review(root,index['id'])
            permissions.declare(root,index['id'],True,old,'user_created','QA-owned source')
            with self.assertRaisesRegex(ValueError,'review changed'):experiments.train(root,index['id'],True,review)
            original=streams.folder(root,source['id'])/'source.bin';data=original.read_bytes();original.write_bytes(data+b'x')
            with self.assertRaisesRegex(ValueError,'source changed'):experiments.review(root,index['id'],{'vocabulary_cap':320})
            self.assertFalse((root/'decoder-stream-tokenizer-experiments').exists())

    def test_failed_and_changed_scope_publication_preserves_sources(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);_,index=fixture(root)
            config={'vocabulary_cap':320};review=experiments.review(root,index['id'],config)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(Path,'rename',side_effect=OSError('fixture interruption')):
                with self.assertRaises(OSError):experiments.train(root,index['id'],True,review)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            with patch.object(experiments,'review',return_value={**review,'revision':'0'*64}):
                with self.assertRaisesRegex(ValueError,'changed during'):experiments.train(root,index['id'],True,review)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            record=experiments.train(root,index['id'],True,review)
            for approved,reviewed in [(False,record),(True,{})]:
                with self.assertRaises(ValueError):experiments.export(root,record['id'],approved,reviewed)
            path=experiments._folder(root,record['id'])/'tokenizer.json';path.write_text('{}')
            with self.assertRaises(ValueError):experiments.read(root,record['id'])

    def test_missing_original_returns_actionable_failure_without_creating_experiments(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,index=fixture(root)
            (streams.folder(root,source['id'])/'source.bin').rename(root/'preserved-source.bin')
            with self.assertRaisesRegex(ValueError,'restore its verified source files'):
                experiments.review(root,index['id'],{'vocabulary_cap':320})
            self.assertFalse((root/'decoder-stream-tokenizer-experiments').exists())

    def test_no_eligible_heldout_rejects_and_review_cannot_mutate_global_limits(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);_,index=fixture(root)
            config={'vocabulary_cap':320}
            review=experiments.review(root,index['id'],config)
            review['method']['maximum_records_per_split']['train']=100000
            self.assertEqual(experiments.LIMITS['train'],16)
            with patch.object(experiments,'LIMITS',{'train':16,'validation':0,'test':8}):
                with self.assertRaisesRegex(ValueError,'Each split'):experiments.review(root,index['id'],config)
