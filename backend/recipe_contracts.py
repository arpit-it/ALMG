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
