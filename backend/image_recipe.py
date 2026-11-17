"""Train a compact text-to-image model using procedurally rendered examples."""

import base64
import io
import re
import unicodedata

import numpy as np
from PIL import Image

SIZE = 48
COLORS = {"red": (224, 61, 68), "green": (47, 165, 90), "blue": (58, 111, 223),
          "yellow": (244, 194, 56), "purple": (148, 87, 198)}
SHAPES = ("circle", "square", "triangle")
POSITIONS = ("left", "center", "right")
OFFSETS = (-11, 0, 11)
BACKGROUND = 248


def dataset():
    """Render labeled images and reserve unseen shape and color combinations."""
    y, x = np.mgrid[:SIZE, :SIZE] - (SIZE - 1) / 2
    rows = []
    for shape_index, shape in enumerate(SHAPES):
        for color_index, (color, rgb) in enumerate(COLORS.items()):
            split = "test" if (shape_index + color_index) % len(COLORS) == 0 else "train"
            for position, offset in zip(POSITIONS, OFFSETS):
                dx = x - offset
                if shape == "circle":
                    mask = dx**2 + y**2 <= 9**2
                elif shape == "square":
                    mask = (abs(dx) <= 8) & (abs(y) <= 8)
                else:
                    mask = (y >= -9) & (y <= 9) & (abs(dx) <= (y + 9) / 2)
                rows.append({"text": f"a {color} {shape} on the {position}",
                             "label": f"{color} {shape}", "shape": shape,
                             "color": color, "position": position, "rgb": list(rgb),
                             "mask": mask.astype(np.uint8).ravel().tolist(), "split": split})
    return rows


def train(rows, target, report):
    """Fit independent shape and color weights without pretrained parameters."""
    report("Learning shape masks and color values from the approved dataset.")
    masks, palette = {}, {}
    for shape in SHAPES:
        for position in POSITIONS:
            samples = [row["mask"] for row in rows if row["split"] == "train"
                       and row["shape"] == shape and row["position"] == position]
            masks[f"{shape}:{position}"] = np.mean(samples, axis=0).tolist()
    for color in COLORS:
        palette[color] = np.mean([row["rgb"] for row in rows
                                  if row["split"] == "train" and row["color"] == color],
                                 axis=0).round().astype(int).tolist()
    model = {"format": "almg-shapes-v1", "size": SIZE, "background": BACKGROUND,
             "masks": masks, "palette": palette}
    report("Testing unseen combinations of shapes and colors.")
    held_out = [row for row in rows if row["split"] == "test"]
    scores = []
    for row in held_out:
        rendered = pixels(model, row["text"])
        reference_mask = np.asarray(row["mask"], dtype=bool).reshape(SIZE, SIZE)
        reference = np.full((SIZE, SIZE, 3), BACKGROUND, dtype=np.uint8)
        reference[reference_mask] = row["rgb"]
        foreground = np.any(rendered != BACKGROUND, axis=-1) | reference_mask
        scores.append(float(np.mean(np.all(rendered[foreground] == reference[foreground], axis=-1))))
    score = sum(scores) / len(scores)
    return model, rows, {"algorithm": "Factorized shape and color model",
                         "held_out_pixel_accuracy": score, "target_pixel_accuracy": target,
                         "test_examples": len(scores), "passed": score >= target}


def pixels(model, prompt):
    """Decode a supported text prompt into RGB pixels using only learned weights."""
    clauses = re.split(r"\s+\band\b\s+|\s*,\s*", prompt.strip().lower())
    if len(clauses) > 3:
        raise ValueError("The image model supports up to three shapes per image.")
    defaults = {1: ("center",), 2: ("left", "right"), 3: POSITIONS}
    size = model["size"]
    image = np.full((size, size, 3), model["background"], dtype=np.uint8)
    for index, clause in enumerate(clauses):
        tokens = set(re.findall(r"[a-z]+", clause))
        colors = tokens.intersection(model["palette"])
        shapes = tokens.intersection(key.split(":")[0] for key in model["masks"])
        positions = tokens.intersection(POSITIONS)
        if len(colors) != 1 or len(shapes) != 1 or len(positions) > 1:
            raise ValueError("Describe one supported color and shape per item, e.g. "
                             "a red circle and a blue square.")
        color, shape = next(iter(colors)), next(iter(shapes))
        position = next(iter(positions), defaults[len(clauses)][index])
        mask = np.asarray(model["masks"][f"{shape}:{position}"]).reshape(size, size) >= .5
        image[mask] = model["palette"][color]
    return image


def preview(model, prompt):
    """Encode the generated image for ALMG's preview chat."""
    with io.BytesIO() as output:
        rendered = web_pixels(model, prompt) if model["format"] == "almg-caption-ridge-v1" else pixels(model, prompt)
        Image.fromarray(rendered).save(output, format="PNG")
        return {"image": base64.b64encode(output.getvalue()).decode("ascii")}


def web_dataset(candidates, read_image, report):
    """Normalize approved images and split distinct examples for evaluation."""
    import hashlib

    rows, seen = [], set()
    for candidate in candidates:
        try:
            contents = read_image(candidate["url"])
            with Image.open(io.BytesIO(contents)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"} or image.width * image.height > 24_000_000:
                    raise ValueError("Unsupported image format or dimensions.")
                thumbnail = image.convert("RGB").resize((SIZE, SIZE), Image.Resampling.LANCZOS)
            caption = re.sub(r"_+", " ", candidate["title"].rsplit(".", 1)[0]).strip()
            if not any(character.isalpha() for character in caption):
                report(f"Skipped {candidate['title']}: filename has no caption text.")
                continue
            signature = hashlib.sha256(thumbnail.tobytes()).hexdigest()
            if signature in seen:
                report(f"Skipped {candidate['title']}: duplicate image.")
                continue
            seen.add(signature)
            with io.BytesIO() as output:
                thumbnail.save(output, format="PNG")
                encoded = base64.b64encode(output.getvalue()).decode("ascii")
            row = {"text": caption, "label": "Commons filename caption",
                         "source": candidate["url"], "sha256": hashlib.sha256(contents).hexdigest(),
                         "image": encoded, "license": candidate.get("license"),
                         "title": candidate["title"]}
            if "approved_query" in candidate:
                row["approved_query"] = candidate["approved_query"]
            for field in ("license_url", "artist", "credit", "attribution_required", "restrictions"):
                if field in candidate:
                    row[field] = candidate[field]
            rows.append(row)
            report(f"Prepared image {len(rows)}: {caption}")
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            report(f"Skipped {candidate['title']}: {error}")
    if len(rows) < 5:
        raise ValueError("At least five distinct captioned images are needed. Try a broader query.")
    rows.sort(key=lambda row: row["sha256"])
    # Hold punctuation and Unicode formatting variants together across the split.
    groups = [
        tuple(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", row["text"]).casefold()))
        for row in rows
    ]
    test_captions = set(list(dict.fromkeys(groups))[::5])
    for row, group in zip(rows, groups):
        row["split"] = "test" if group in test_captions else "train"
    if sum(row["split"] == "train" for row in rows) < 3:
        raise ValueError("Need more distinct captions for training and evaluation.")
    return rows


def caption_features(prompt, vocabulary):
    """Encode vocabulary overlap from words in a caption."""
    words = set(re.findall(r"[a-z0-9]+", prompt.lower()))
    return np.array([1., *(float(word in words) for word in vocabulary)])


def train_web(rows, target, report):
    """Fit a text-to-RGB ridge regression baseline from approved examples."""
    training = [row for row in rows if row["split"] == "train"]
    test = [row for row in rows if row["split"] == "test"]
    vocabulary = sorted(set(re.findall(r"[a-z0-9]+", " ".join(row["text"] for row in training).lower())))[:256]

    def decode(row):
        with Image.open(io.BytesIO(base64.b64decode(row["image"]))) as image:
            return np.asarray(image, dtype=float).ravel()

    report("Fitting a caption-to-pixel regression model from scratch.")
    features = np.stack([caption_features(row["text"], vocabulary) for row in training])
    targets = np.stack([decode(row) for row in training])
    weights = features.T @ np.linalg.solve(features @ features.T + np.eye(len(training)), targets)
    model = {"format": "almg-caption-ridge-v1", "size": SIZE, "vocabulary": vocabulary,
             "weights": weights.round(5).tolist()}
    report(f"Evaluating on {len(test)} held-out captions.")
    errors = [np.mean(np.abs(web_pixels(model, row["text"]).ravel() - decode(row))) / 255 for row in test]
    score = float(1 - np.mean(errors))
    return model, rows, {"algorithm": "Caption-to-pixel ridge regression",
                         "held_out_pixel_similarity": score, "target_pixel_accuracy": target,
                         "test_prompts": [row["text"] for row in test], "passed": score >= target}


def web_pixels(model, prompt):
    """Predict RGB channels from caption features and trained coefficients."""
    features = caption_features(prompt, model["vocabulary"])
    return np.clip(features @ np.asarray(model["weights"]), 0, 255).astype(np.uint8).reshape(SIZE, SIZE, 3)
