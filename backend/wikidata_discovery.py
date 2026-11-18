"""Normalize Wikidata item search results for source review."""
import re
import unicodedata


def entity_candidates(payload, query, *, limit=20):
    results = payload.get("search") if isinstance(payload, dict) else None
    if not isinstance(results, list) or payload.get("error"):
        raise ValueError("Wikidata returned invalid entity search metadata.")
    rows, seen = [], set()
    for item in results[:limit]:
        if not isinstance(item, dict):
            continue
        identity, label, description = item.get("id"), item.get("label"), item.get("description", "")
        if (not isinstance(identity, str) or not re.fullmatch(r"Q[1-9][0-9]*", identity)
                or not isinstance(label, str) or not isinstance(description, str)):
            continue
        label, description = label.strip(), description.strip()
        if (not label or len(label) > 500 or len(description) > 4000
                or any(unicodedata.category(c) in {"Cc", "Cs"} for c in label + description)
                or identity in seen):
            continue
        seen.add(identity)
        rows.append({"entity_id": identity, "title": label, "description": description,
                     "source": f"https://www.wikidata.org/wiki/{identity}",
                     "provider": "wikidata", "approved_query": query, "reuse_status": "unverified"})
    return rows
