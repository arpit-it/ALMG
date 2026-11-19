"""Versioned public contracts for the currently implemented training recipes."""
from copy import deepcopy

SCHEMA_VERSION = 1
_COMMON_PARAMETERS = [
    {"id": "target", "label": "Target score", "type": "number", "minimum_exclusive": 0, "maximum": 1, "default": 0.8},
    {"id": "idle", "label": "Wait for idle time and AC power", "type": "boolean", "default": True},
]
_CONTRACTS = {
    "classifier": {
        "id": "classifier", "version": 1, "name": "Text classification",
        "description": "Compare supervised classifiers and evaluate a held-out split.",
        "dataset": {"format": "JSON rows: text, label, group", "imports": "UTF-8 CSV: text, label, optional group",
                    "modes": {"synthetic": {"label": "Local generated examples", "variant": "classifier"},
                              "local": {"label": "Local generated examples", "variant": "classifier"},
                              "local_csv": {"label": "Imported CSV", "variant": "classifier"},
                              "web": {"label": "Approved web excerpts", "variant": "classifier"}}},
        "hardware": {"training": "CPU; no accelerator required", "planning": "Local Qwen on Apple silicon"},
        "parameters": [*_COMMON_PARAMETERS, {"id": "allow_repair", "label": "One local-example retry", "type": "boolean", "default": False}],
        "metrics": {"classifier": ["validation_macro_f1", "test_macro_f1", "target_macro_f1"]},
        "exports": ["model.joblib: scikit-learn pipeline", "dataset.jsonl: labeled examples and splits", "report.json: evaluation report", "recipe-contract.json: recipe snapshot and execution settings"],
        "resume": "Reuse completed candidate checkpoints; an unfinished fit restarts.",
        "status": "available",
    },
    "text_to_image": {
        "id": "text_to_image", "version": 1, "name": "Text to image (experimental)",
        "description": "Learn 48×48 images from local shape pairs or approved Commons captions.",
        "dataset": {"format": "Local shape rows: text, shape, color, position, mask, rgb, split; Commons rows: text, image, split", "imports": "Local synthetic shapes or separately approved Commons images",
                    "modes": {"synthetic": {"label": "Local generated shapes", "variant": "local shapes"},
                              "local": {"label": "Local generated shapes", "variant": "local shapes"},
                              "web_images": {"label": "Approved Commons images", "variant": "Commons captions"}}},
        "hardware": {"training": "CPU with NumPy and Pillow; no accelerator required", "planning": "Local Qwen on Apple silicon"},
        "parameters": _COMMON_PARAMETERS,
        "metrics": {"local shapes": ["held_out_pixel_accuracy", "target_pixel_accuracy"],
                    "Commons captions": ["held_out_pixel_similarity", "target_pixel_accuracy"]},
        "exports": ["model.json: local image model", "dataset.jsonl: image examples and splits", "report.json: evaluation report", "recipe-contract.json: recipe snapshot and execution settings"],
        "resume": "No partial-fit checkpoint; fitting restarts. Commons models require further runtime and semantic evaluation before release.",
        "status": "experimental",
    },
}


class RecipeRegistry:
    """Validate and snapshot trusted local recipe registrations before discovery.

    Registration is an application startup operation, never an API accepting
    downloaded code. A contract alone does not enable an execution backend.
    """

    def __init__(self, dependency_available=None):
        from importlib.util import find_spec
        self._contracts = {}
        self._initializers = {}
        self._dependency_available = dependency_available or (lambda name: find_spec(name) is not None)

    def register(self, contract, *, dependencies=(), initializer=None):
        import json
        import re
        if not isinstance(contract, dict):
            raise ValueError('Recipe contract must be an object.')
        recipe_id = contract.get('id')
        if not isinstance(recipe_id, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', recipe_id):
            raise ValueError('Recipe ID must be a stable lowercase identifier.')
        if recipe_id in self._contracts:
            raise ValueError('Recipe ID is already registered: ' + recipe_id)
        if type(contract.get('version')) is not int or contract['version'] < 1:
            raise ValueError('Recipe version must be a positive integer.')
        schema = contract.get('schema_version', SCHEMA_VERSION)
        if type(schema) is not int or schema != SCHEMA_VERSION:
            raise ValueError('Unsupported recipe contract schema.')
        for field in ('name', 'description', 'resume', 'status'):
            if not isinstance(contract.get(field), str) or not contract[field].strip():
                raise ValueError('Recipe requires ' + field + '.')
        for field, kind in (('dataset', dict), ('hardware', dict), ('parameters', list),
                            ('metrics', dict), ('exports', list)):
            if not isinstance(contract.get(field), kind) or not contract[field]:
                raise ValueError('Recipe requires a nonempty ' + field + '.')
        if not isinstance(dependencies, (tuple, list)) or any(
                not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name)
                for name in dependencies):
            raise ValueError('Recipe dependencies must be top-level Python module names.')
        missing = [name for name in dependencies if not self._dependency_available(name)]
        if missing:
            raise ValueError('Recipe dependencies are unavailable: ' + ', '.join(missing))
        snapshot = {'schema_version': SCHEMA_VERSION, **deepcopy(contract)}
        try:
            json.dumps(snapshot, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError('Recipe contract must contain finite JSON values.') from error
        if 'pipeline' in snapshot:
            decoder_recipe.validate_pipeline(snapshot['pipeline'])
        planning = snapshot.get('planning')
        if planning is not None:
            if (not isinstance(planning, dict) or set(planning) != {'workflow', 'approaches', 'scopes'}
                    or not isinstance(planning['workflow'], str)
                    or not re.fullmatch(r'[a-z][a-z0-9_]*', planning['workflow'])
                    or any(not isinstance(planning[key], list) or not planning[key]
                           or any(not isinstance(value, str) or not value.strip() for value in planning[key])
                           for key in ('approaches', 'scopes'))
                    or any(value not in ('from_scratch', 'fine_tuning', 'distillation', 'retrieval')
                           for value in planning['approaches'])):
                raise ValueError('Recipe planning capabilities require a workflow, approaches and scopes.')
        if initializer is not None and not callable(initializer):
            raise ValueError('Recipe initializer must be callable.')
        self._contracts[recipe_id] = snapshot
        if initializer is not None:
            self._initializers[recipe_id] = initializer

    def initialize(self, recipe_id, config):
        self.contract(recipe_id)
        initializer = self._initializers.get(recipe_id)
        if initializer is None:
            raise ValueError('Recipe has no registered initializer.')
        return initializer(deepcopy(config))

    def contract(self, recipe_id):
        if not isinstance(recipe_id, str) or recipe_id not in self._contracts:
            raise ValueError('Unknown training recipe.')
        return deepcopy(self._contracts[recipe_id])

    def catalog(self):
        return [self.contract(recipe_id) for recipe_id in self._contracts]


_REGISTRY = RecipeRegistry()
for _contract in _CONTRACTS.values():
    _REGISTRY.register(_contract)

if __package__:
    from . import decoder_recipe
else:
    import decoder_recipe
_REGISTRY.register(decoder_recipe.CONTRACT, dependencies=['numpy'], initializer=decoder_recipe.Decoder)


def initialize_recipe(recipe_id, config):
    return _REGISTRY.initialize(recipe_id, config)


def recipe_contract(recipe_id):
    """Return an independent contract snapshot for a supported recipe ID."""
    return _REGISTRY.contract(recipe_id)


def recipe_catalog():
    """Discover validated, trusted local registrations in registration order."""
    return [contract for contract in _REGISTRY.catalog() if contract['status'] in ('available', 'experimental')]


def planning_catalog(workflow):
    """Discover registered capabilities for a workflow without enabling job execution."""
    return [contract for contract in _REGISTRY.catalog()
            if contract.get('planning', {}).get('workflow') == workflow]


def training_parameters(recipe_id, values, snapshot=None):
    """Validate approved execution settings against a supported recipe contract."""
    import math
    contract = recipe_contract(recipe_id)
    if snapshot is not None and (not isinstance(snapshot, dict)
            or type(snapshot.get('schema_version')) is not int or snapshot['schema_version'] != SCHEMA_VERSION
            or snapshot.get('id') != recipe_id or type(snapshot.get('version')) is not int
            or snapshot['version'] != contract['version']):
        raise ValueError('This job uses an unsupported recipe contract. Create a new training plan.')
    if not isinstance(values, dict):
        raise ValueError('Training parameters must be an object.')
    supplied = dict(values)
    # Older image clients always sent this classifier-only switch as false.
    if recipe_id == 'text_to_image' and supplied.get('allow_repair') is False:
        supplied.pop('allow_repair')
    allowed = {parameter['id'] for parameter in contract['parameters']}
    if set(supplied) - allowed:
        raise ValueError('Unsupported training parameters: ' + ', '.join(sorted(set(supplied) - allowed)))
    if 'target' not in supplied:
        raise ValueError('Approve a target score before starting training.')
    result = {}
    for parameter in contract['parameters']:
        value = supplied.get(parameter['id'], parameter['default'])
        if parameter['type'] == 'boolean':
            if type(value) is not bool:
                raise ValueError(parameter['label'] + ' must be true or false.')
        elif parameter['type'] == 'number':
            if (type(value) not in (int, float) or value <= parameter['minimum_exclusive']
                    or value > parameter['maximum'] or not math.isfinite(value)):
                raise ValueError(parameter['label'] + ' must be a finite number greater than 0 and at most 1.')
            value = float(value)
        result[parameter['id']] = value
    result.setdefault('allow_repair', False)
    return result


def execution_variant(recipe_id, mode):
    """Resolve only the existing recipe/source combinations, including legacy local jobs."""
    modes = recipe_contract(recipe_id)['dataset']['modes']
    selected = 'synthetic' if mode is None else mode
    if not isinstance(selected, str) or selected not in modes:
        raise ValueError('Dataset mode is not supported by this training recipe.')
    return modes[selected]['variant']


def validate_metrics(recipe_id, mode, metrics, target):
    """Reject invalid evaluation output before saving a preview candidate."""
    import math
    contract = recipe_contract(recipe_id)
    variant = execution_variant(recipe_id, mode)
    if not isinstance(metrics, dict) or type(metrics.get('passed')) is not bool:
        raise ValueError('Recipe evaluation must include a boolean passed result.')
    keys = contract['metrics'][variant]
    for key in keys:
        value = metrics.get(key)
        if type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value):
            raise ValueError('Recipe evaluation requires a finite score between 0 and 1: ' + key)
    target_key = next(key for key in keys if key.startswith('target_'))
    if metrics[target_key] != target:
        raise ValueError('Recipe evaluation target does not match the approved target.')
    if metrics['passed'] and any(metrics[key] < target for key in keys if key != target_key):
        raise ValueError('Recipe evaluation passed despite a score below the approved target.')


def validate_model(recipe_id, mode, model):
    """Check the existing runtime/export format before candidate persistence."""
    execution_variant(recipe_id, mode)
    if recipe_id == 'classifier':
        from sklearn.pipeline import Pipeline
        if not isinstance(model, Pipeline) or not callable(getattr(model, 'predict', None)):
            raise ValueError('Classifier recipe must return a scikit-learn pipeline.')
    else:
        import json
        expected = 'almg-caption-ridge-v1' if mode == 'web_images' else 'almg-shapes-v1'
        if not isinstance(model, dict) or model.get('format') != expected or type(model.get('size')) is not int or model['size'] != 48:
            raise ValueError('Image recipe returned an unsupported model format or size: expected ' + expected)
        try:
            json.dumps(model, allow_nan=False)
        except (ValueError, TypeError) as error:
            raise ValueError('Image recipe model must contain finite JSON values.') from error

        import numpy as np

        def numeric_array(value, shape, minimum=None, maximum=None):
            try:
                array = np.asarray(value)
                return (array.shape == shape and array.dtype.kind in 'iuf'
                        and bool(np.isfinite(array).all())
                        and (minimum is None or bool((array >= minimum).all()))
                        and (maximum is None or bool((array <= maximum).all())))
            except (ValueError, TypeError):
                return False

        if mode == 'web_images':
            vocabulary = model.get('vocabulary')
            if (not isinstance(vocabulary, list) or len(vocabulary) > 256
                    or not all(isinstance(word, str) and word for word in vocabulary)
                    or len(set(vocabulary)) != len(vocabulary)
                    or not numeric_array(model.get('weights'), (len(vocabulary) + 1, 48 * 48 * 3))):
                raise ValueError('Caption image model has invalid vocabulary or coefficient dimensions.')
        else:
            masks, palette = model.get('masks'), model.get('palette')
            if (type(model.get('background')) is not int or not 0 <= model['background'] <= 255
                    or not isinstance(masks, dict) or not isinstance(palette, dict)
                    or any(not numeric_array(masks.get(shape + ':' + position), (48 * 48,), 0, 1)
                           for shape in ('circle', 'square', 'triangle') for position in ('left', 'center', 'right'))
                    or any(not numeric_array(palette.get(color), (3,), 0, 255)
                           for color in ('red', 'green', 'blue', 'yellow', 'purple'))):
                raise ValueError('Shape image model has invalid masks, colors or background.')


def export_metadata(job):
    """Preserve approval provenance; identify catalog fallback for legacy jobs."""
    snapshot = job.get('recipe_contract')
    contract = deepcopy(snapshot) if snapshot is not None else recipe_contract(job.get('recipe', 'classifier'))
    keys = [parameter['id'] for parameter in contract['parameters']]
    return {'schema_version': 1,
            'origin': 'approved_job_snapshot' if snapshot is not None else 'legacy_catalog_fallback',
            'contract': contract,
            'parameters': {key: deepcopy(job[key]) for key in keys if key in job}}


def validate_dataset(recipe_id, mode, rows, labels=()):
    """Validate the existing recipe's row structure before invoking a trainer."""
    execution_variant(recipe_id, mode)
    if not isinstance(rows, list) or not rows:
        raise ValueError('Recipe dataset must be a nonempty list of examples.')
    for index, row in enumerate(rows):
        prefix = 'Dataset example ' + str(index + 1) + ': '
        if not isinstance(row, dict) or not isinstance(row.get('text'), str) or not row['text'].strip():
            raise ValueError(prefix + 'a nonempty text field is required.')
        if recipe_id == 'classifier':
            if (not isinstance(row.get('label'), str) or row['label'] not in labels
                    or not isinstance(row.get('group'), str) or not row['group'].strip()):
                raise ValueError(prefix + 'an approved label and nonempty group are required.')
        else:
            if row.get('split') not in ('train', 'test'):
                raise ValueError(prefix + 'split must be train or test.')
            if mode == 'web_images':
                if not isinstance(row.get('image'), str) or not row['image']:
                    raise ValueError(prefix + 'an encoded image is required.')
                import base64
                import io
                from PIL import Image
                try:
                    if len(row['image']) > 100_000:
                        raise ValueError('Encoded image is too large.')
                    content = base64.b64decode(row['image'], validate=True)
                    with Image.open(io.BytesIO(content)) as image:
                        if image.format != 'PNG' or image.size != (48, 48) or image.mode != 'RGB':
                            raise ValueError('Expected a prepared 48x48 RGB PNG.')
                        image.load()
                except (ValueError, OSError) as error:
                    raise ValueError(prefix + 'a valid prepared 48x48 RGB PNG is required.') from error
            elif (row.get('shape') not in ('circle', 'square', 'triangle')
                    or row.get('color') not in ('red', 'green', 'blue', 'yellow', 'purple')
                    or row.get('position') not in ('left', 'center', 'right')
                    or not isinstance(row.get('mask'), list) or len(row['mask']) != 48 * 48
                    or not isinstance(row.get('rgb'), list) or len(row['rgb']) != 3):
                raise ValueError(prefix + 'valid shape, color, position, mask and RGB fields are required.')
            elif (any(type(value) not in (int, float) or not 0 <= value <= 1 for value in row['mask'])
                  or any(type(value) is not int or not 0 <= value <= 255 for value in row['rgb'])):
                raise ValueError(prefix + 'mask values must be between 0 and 1 and RGB channels must be integers from 0 to 255.')
    if recipe_id == 'text_to_image' and {row['split'] for row in rows} != {'train', 'test'}:
        raise ValueError('Image recipe requires both training and held-out examples.')

    if recipe_id == 'text_to_image' and mode != 'web_images':
        training = [row for row in rows if row['split'] == 'train']
        combinations = {(row['shape'], row['position']) for row in training}
        colors = {row['color'] for row in training}
        if (any((shape, position) not in combinations for shape in ('circle', 'square', 'triangle')
                for position in ('left', 'center', 'right'))
                or not {'red', 'green', 'blue', 'yellow', 'purple'} <= colors):
            raise ValueError('Shape training requires every shape/position combination and every color.')


def execute(recipe_id, mode, rows, parameters, *, trainers, labels=(), report,
            repair=None, checkpoint_path=None, snapshot=None):
    """Run an existing recipe through one validated input/output boundary.

    Trainers are supplied by orchestration so this contract module does not
    own job state, scheduling, cancellation, model loading or network access.
    """
    settings = training_parameters(recipe_id, parameters, snapshot)
    variant = execution_variant(recipe_id, mode)
    validate_dataset(recipe_id, mode, rows, labels)
    trainer = trainers.get(variant)
    if not callable(trainer):
        raise ValueError('No local trainer is registered for this recipe variant.')
    if variant == 'classifier':
        result = trainer(rows, labels, settings['target'], report=report,
                         repair=repair if settings['allow_repair'] else None,
                         checkpoint_path=checkpoint_path)
    else:
        result = trainer(rows, settings['target'], report)
    if not isinstance(result, tuple) or len(result) != 3:
        raise ValueError('Recipe trainer must return model, dataset and metrics.')
    model, evaluated_rows, metrics = result
    validate_dataset(recipe_id, mode, evaluated_rows, labels)
    validate_metrics(recipe_id, mode, metrics, settings['target'])
    validate_model(recipe_id, mode, model)
    return model, evaluated_rows, metrics
