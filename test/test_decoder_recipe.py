import io
import json
import unittest
from unittest.mock import Mock, patch
import numpy as np
from backend import decoder_recipe, recipe_contracts, studio


class DecoderRecipeTest(unittest.TestCase):
    def test_registered_initializer_builds_new_weights_without_file_loading(self):
        with patch('pathlib.Path.open', side_effect=AssertionError('No student files should be opened')):
            model = recipe_contracts.initialize_recipe('decoder_from_scratch', {'seed': 7})
        self.assertEqual(sum(value.size for value in model.parameters.values()), 896)
        self.assertEqual(model.logits([[0, 1, 2]]).shape, (1, 3, 16))
        contract = recipe_contracts.recipe_contract('decoder_from_scratch')
        self.assertEqual(contract['status'], 'bounded_trial')
        self.assertNotIn('decoder_from_scratch', studio.TRAINING_RECIPES)
        self.assertNotIn('decoder_from_scratch', {item['id'] for item in recipe_contracts.recipe_catalog()})

    def test_initialization_is_deterministic_causal_and_does_not_mutate_global_rng(self):
        before = np.random.get_state()
        first = decoder_recipe.Decoder({})
        second = decoder_recipe.Decoder({})
        other = decoder_recipe.Decoder({'seed': 8})
        after = np.random.get_state()
        self.assertTrue(all(np.array_equal(a, b) for a, b in zip(before, after)))
        self.assertTrue(all(np.array_equal(value, second.parameters[key]) for key, value in first.parameters.items()))
        self.assertFalse(np.array_equal(first.parameters['head'], other.parameters['head']))
        np.testing.assert_array_equal(first.logits([[0, 1, 2, 3]])[:, :-1], first.logits([[0, 1, 2, 4]])[:, :-1])
        result = decoder_recipe.verify(recipe_contracts.initialize_recipe)
        self.assertTrue(result['passed'])
        self.assertEqual(result['weight_origin'], 'newly_initialized')
        self.assertFalse(result['pretrained_weights_loaded'])

    def test_invalid_configuration_tokens_and_registry_entries_fail_clearly(self):
        for config in ({'seed': True}, {'width': 100000}, {'context_length': 0},
                       {'weights': '/tmp/pretrained'}, {'vocab_size': float('nan')}, None):
            with self.subTest(config=config), self.assertRaises(ValueError):
                decoder_recipe.Decoder(config)
        model = decoder_recipe.Decoder({})
        for tokens in ([1, 2], [[-1]], [[16]], [[1.5]], [[]], [[0] * 17]):
            with self.subTest(tokens=tokens), self.assertRaises(ValueError):
                model.logits(tokens)
        for recipe in ('unknown', 'classifier'):
            with self.assertRaises(ValueError):
                recipe_contracts.initialize_recipe(recipe, {})
        registry = recipe_contracts.RecipeRegistry(lambda module: False)
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            registry.register(decoder_recipe.CONTRACT, dependencies=['numpy'], initializer=decoder_recipe.Decoder)
        self.assertEqual(registry.catalog(), [])

    def test_runtime_check_requires_explicit_confirmation(self):
        for confirmed in (None, False, 1, True):
            body = json.dumps({'confirmed': confirmed}).encode()
            handler = Mock(path='/runtime/decoder-initialization', headers={'Content-Length': str(len(body))}, rfile=io.BytesIO(body))
            with patch.object(decoder_recipe, 'verify', return_value={'passed': True}) as verify:
                studio.Handler.do_POST(handler)
            if confirmed is True:
                verify.assert_called_once_with(recipe_contracts.initialize_recipe)
                self.assertEqual(handler.respond.call_args.args[0], {'passed': True})
            else:
                verify.assert_not_called()
                self.assertEqual(handler.respond.call_args.args[1], 400)
