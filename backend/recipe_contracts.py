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
        "dataset": {"format": "JSON rows: text, label, group", "imports": "UTF-8 CSV: text, label, optional group"},
        "hardware": {"training": "CPU; no accelerator required", "planning": "Local Qwen on Apple silicon"},
        "parameters": [*_COMMON_PARAMETERS, {"id": "allow_repair", "label": "One local-example retry", "type": "boolean", "default": False}],
        "metrics": {"classifier": ["validation_macro_f1", "test_macro_f1", "target_macro_f1"]},
        "exports": ["model.joblib: scikit-learn pipeline", "dataset.jsonl: labeled examples and splits", "report.json: evaluation report"],
        "resume": "Reuse completed candidate checkpoints; an unfinished fit restarts.",
        "status": "available",
    },
    "text_to_image": {
        "id": "text_to_image", "version": 1, "name": "Text to image (experimental)",
        "description": "Learn 48×48 images from local shape pairs or approved Commons captions.",
        "dataset": {"format": "Local shape rows: text, shape, color, position, mask, rgb, split; Commons rows: text, image, split", "imports": "Local synthetic shapes or separately approved Commons images"},
        "hardware": {"training": "CPU with NumPy and Pillow; no accelerator required", "planning": "Local Qwen on Apple silicon"},
        "parameters": _COMMON_PARAMETERS,
        "metrics": {"local shapes": ["held_out_pixel_accuracy", "target_pixel_accuracy"],
                    "Commons captions": ["held_out_pixel_similarity", "target_pixel_accuracy"]},
        "exports": ["model.json: local image model", "dataset.jsonl: image examples and splits", "report.json: evaluation report"],
        "resume": "No partial-fit checkpoint; fitting restarts. Commons models require further runtime and semantic evaluation before release.",
        "status": "experimental",
    },
}


def recipe_contract(recipe_id):
    """Return an independent contract snapshot for a supported recipe ID."""
    if not isinstance(recipe_id, str) or recipe_id not in _CONTRACTS:
        raise ValueError("Unknown training recipe.")
    return {"schema_version": SCHEMA_VERSION, **deepcopy(_CONTRACTS[recipe_id])}


def recipe_catalog():
    """List implemented recipes only; future recipes require separate validation."""
    return [recipe_contract(recipe_id) for recipe_id in _CONTRACTS]


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
