"""Normalize Library of Congress discovery results for source review."""
import re
import unicodedata


def catalog_candidates(payload, query, *, limit):
    """Return catalog links for review without treating access as reuse permission."""
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("The Library of Congress returned an invalid search response.")
    candidates = []
    seen = set()
    for item in results[:limit]:
        if not isinstance(item, dict) or item.get("access-restricted") is not False:
            continue
        source = item.get("id")
        title = item.get("title")
        if not isinstance(source, str) or not isinstance(title, str):
            continue
        item_id = re.fullmatch(r"https?://www\.loc\.gov/item/([A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*)/?", source)
        title = title.strip()
        if not item_id or not title or any(unicodedata.category(c) in {"Cc", "Cs"} for c in title):
            continue
        source = f"https://www.loc.gov/item/{item_id[1]}/"
        if source in seen:
            continue
        seen.add(source)
        candidates.append({
            "source": source,
            "title": title[:255],
            "provider": "loc",
            "approved_query": query,
            "reuse_status": "unverified",
        })
    return candidates


def item_advisories(payload):
    """Preserve item-level advisories as evidence for human reuse review."""
    item = payload.get("item") if isinstance(payload, dict) else None
    if not isinstance(item, dict):
        raise ValueError("The catalog item response has no usable item metadata.")
    advisories = {}
    for field in ("rights_advisory", "rights", "access_advisory"):
        values = item.get(field)
        if values is None:
            continue
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError("The catalog item has unreadable rights metadata.")
        cleaned = []
        for value in values:
            value = value.strip()
            if len(value) > 8000 or any(unicodedata.category(c) == "Cs" for c in value):
                raise ValueError("The catalog item has unreadable rights metadata.")
            if value:
                cleaned.append(value)
        if cleaned:
            advisories[field] = cleaned
    descriptions = item.get("description", [])
    if not isinstance(descriptions, list) or any(not isinstance(value, str) for value in descriptions):
        raise ValueError("The catalog item has unreadable description metadata.")
    text = " ".join(" ".join(descriptions).split())
    if len(text) > 20000 or any(unicodedata.category(c) in {"Cc", "Cs"} for c in text):
        raise ValueError("The catalog item has unreadable description metadata.")
    return {"advisories": advisories, "reuse_status": "unverified", "description": text}
