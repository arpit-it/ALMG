import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_datasets as datasets, decoder_dataset_training as training


def documents(prefix):
    words=['amber','birch','cedar','dune']
    return [{'name':f'{prefix}-{i}', 'text':' '.join(words[(i+j)%4] for j in range(8+i))} for i in range(6)]


class DatasetMixingTests(unittest.TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.first=datasets.prepare(self.root,documents('first'),True)
        self.second=datasets.prepare(self.root,documents('second'),True)
        self.selections=[{'dataset':self.first,'weight':1},{'dataset':self.second,'weight':2}]

    def test_mixture_global_deduplication_lineage_and_training_only_weights(self):
        before={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        mixed=datasets.mix_datasets(self.root,self.selections,True)
        self.assertEqual((mixed['input_documents'],mixed['unique_documents']),(12,6))
        self.assertEqual(set(mixed['mixing']['group_weights'].values()),{3})
        self.assertEqual(mixed['derivation']['operation'],'mix_local_datasets')
        self.assertEqual({row['parent_dataset_id'] for row in mixed['derivation']['sources']},{self.first['id'],self.second['id']})
        self.assertEqual(mixed['status'],'prepared_for_review')
        _,_,_,normal=training.preflight(self.root,self.first)
        _,_,_,weighted=training.preflight(self.root,mixed)
        self.assertEqual(len(weighted['train']),3*len(normal['train']))
        for part in ('validation','test'):self.assertEqual(weighted[part],normal[part])
        for name,data in before.items():self.assertEqual((self.root/name).read_bytes(),data)
        self.assertEqual(datasets.read(self.root,mixed['id']),mixed)
        self.assertFalse((self.root/'decoder-trials').exists())
        with self.assertRaisesRegex(ValueError,'nested weighted'):
            datasets.mix_datasets(self.root,[{'dataset':mixed,'weight':1},{'dataset':self.first,'weight':1}],True)

    def test_invalid_selection_consent_and_stale_review_do_not_publish(self):
        before=set((self.root/'decoder-datasets').iterdir())
        for confirmed,selections in ((False,self.selections),(1,self.selections),(True,[]),
                (True,[self.selections[0]]*2),(True,[{'dataset':self.first,'weight':True},self.selections[1]]),
                (True,[{'dataset':self.first,'weight':5},self.selections[1]]),
                (True,[{'dataset':dict(self.first,status='changed'),'weight':1},self.selections[1]])):
            with self.assertRaises(ValueError):datasets.mix_datasets(self.root,selections,confirmed)
        self.assertEqual(before,set((self.root/'decoder-datasets').iterdir()))

    def test_malformed_weights_rejected_and_weighted_window_budget_enforced(self):
        mixed=datasets.mix_datasets(self.root,self.selections,True)
        path=self.root/'decoder-datasets'/mixed['id']/'manifest.json'
        changed=json.loads(path.read_text());key=next(iter(changed['mixing']['group_weights']))
        changed['mixing']['group_weights'][key]=True;path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'mixing weights'):training.preflight(self.root,changed)
        # An otherwise valid bounded contract must still obey the trial's window cap.
        for group in changed['mixing']['group_weights']:changed['mixing']['group_weights'][group]=16
        path.write_text(json.dumps(changed))
        self.assertEqual(len(training.preflight(self.root,changed)[3]['train']),64)
        byte=datasets.prepare(self.root,documents('long-bytes'),True,'utf8_bytes')
        byte_mix=datasets.mix_datasets(self.root,[self.selections[0],{'dataset':byte,'weight':1}],True)
        byte_path=self.root/'decoder-datasets'/byte_mix['id']/'manifest.json'
        for group in byte_mix['mixing']['group_weights']:byte_mix['mixing']['group_weights'][group]=16
        byte_path.write_text(json.dumps(byte_mix))
        with self.assertRaisesRegex(ValueError,'at most 64 training'):
            training.preflight(self.root,byte_mix)
        changed['mixing']['group_weights'].pop(key);path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'mixing weights'):datasets.read(self.root,mixed['id'])

    def test_byte_parent_selects_byte_kind_and_duplicate_parent_does_not_count_twice(self):
        byte=datasets.prepare(self.root,documents('bytes'),True,'utf8_bytes')
        mixed=datasets.mix_datasets(self.root,[self.selections[0],{'dataset':byte,'weight':1}],True)
        self.assertEqual(mixed['tokenizer']['format'],'almg-utf8-byte-tokenizer-v1')
        self.assertEqual(set(mixed['mixing']['group_weights'].values()),{2})


if __name__=='__main__':unittest.main()
