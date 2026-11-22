import json
import os
import random
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_architecture_plans as plans, decoder_architecture_initializations as initializations, decoder_corpus_inputs as inputs, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated, decoder_datasets as datasets, decoder_licenses as licenses


def sixteen_words(root):
    words='amber birch cedar dune ember fern grove hazel iris juniper kelp larch maple nettle oak pine'.split()
    rng=random.Random(7);documents=[]
    for index in range(6):
        ordered=words.copy();rng.shuffle(ordered)
        documents.append({'name':f'pattern-{index}.txt','text':' '.join(ordered)})
    dataset=datasets.prepare(root,documents,True)
    for source in dataset['sources']:
        dataset=licenses.declare(root,dataset['id'],True,dataset,source['source_sha256'],'user_created','Locally generated sixteen-word numerical training fixture.')
    assert datasets.quality_report(root,dataset['id'])['cross_split_pairs']==0
    config={**plans.DEFAULT,'layers':7,'hidden_size':64,'attention_heads':8,'head_dim':8,'feed_forward_size':128,'context_length':16,'vocab_size':16,'seed':7,'batch_size':4}
    plan=plans.save(root,True,plans.review(config));source=initializations.run(root,plan['id'],True,plan)
    corpus=inputs.save(root,plan['id'],True,source,dataset,8,inputs.review(root,plan['id'],source,dataset,8))
    settings={**training.optimizer.DEFAULT,'schema_version':5,'steps':20,'batch_size':2,'sequence_length':8,'gradient_accumulation_steps':2,'compute_precision':'float32','loss_scale':1.,'learning_rate':.001,'warmup_steps':3,'gradient_clip_norm':1.,'weight_decay':0.}
    return source,corpus,settings


class SixteenVocabularyRecipeTest(unittest.TestCase):
    def test_all_ids_masked_padding_and_specific_recipe_controls(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=sixteen_words(root)
            self.assertEqual(source['actual_parameter_count'],232448);self.assertFalse(source['pretrained_weights_loaded'])
            windows=json.loads((root/'decoder-corpus-inputs'/saved['id']/'windows.json').read_text())
            self.assertEqual({token for row in windows['train'] for token,mask in zip(row['targets'],row['target_mask']) if mask},set(range(16)))
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            profile={'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},'available_memory_bytes':8*1024**3,'free_disk_bytes':8*1024**3,'errors':[]}
            with patch.object(training.hardware,'hardware',return_value=profile):
                for kind in ('sgd','adamw'):
                    config={**c,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                    self.assertTrue(isolated.review(root,source,saved,config)['feasible'])
                for changes in ({'learning_rate':.005},{'gradient_accumulation_steps':1},{'compute_precision':'mixed_float16','loss_scale':128.},{'schema_version':7,'steps':80}):
                    config={**c,**changes};review=isolated.review(root,source,saved,config);self.assertFalse(review['feasible'])
                    with self.assertRaises(ValueError):isolated.run(root,True,source,saved,config,review,uuid.uuid4().hex)
            profile.update(available_memory_bytes=1,free_disk_bytes=1)
            with patch.object(training.hardware,'hardware',return_value=profile):self.assertFalse(isolated.review(root,source,saved,c)['feasible'])
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real sixteen-ID vocabulary training and recovery')
    def test_both_optimizers_restore_sixteen_id_heads_and_generate(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,base=sixteen_words(root);base={**base,'steps':10}
            for kind in ('sgd','adamw'):
                c={**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                record=isolated.run(root,True,source,saved,c,isolated.review(root,source,saved,c),uuid.uuid4().hex)
                self.assertLess(record['final_losses']['train'],record['initial_losses']['train'])
                self.assertLessEqual(record['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(record['checkpoint_optimizer_max_error'],1e-7)
                model=training.PlannedDecoder.load(training._folder(root,record['id'])/'trained-model.json');self.assertEqual(model.parameters['head'].shape,(64,16))
                continued=isolated.run_continuation(root,record['id'],True,isolated.review_continuation(root,record['id']),uuid.uuid4().hex)
                self.assertLessEqual(continued['reference_parameter_max_error'],1e-7);self.assertEqual(continued['generated_token_ids'],record['generated_token_ids'])
                self.assertTrue(all(0<=token<16 for token in continued['generated_token_ids']))
