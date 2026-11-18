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


def entity_reuse_evidence(record, decision):
    """Bind an explicit reuse decision to the reviewed structured entity text."""
    import hashlib
    import time
    identity, title, description = (record.get(key) for key in ("entity_id", "title", "description"))
    basis = decision.get("permission_basis")
    if (not isinstance(identity, str) or not re.fullmatch(r"Q[1-9][0-9]*", identity)
            or record.get("source") != f"https://www.wikidata.org/wiki/{identity}"
            or not isinstance(title, str) or not title or not isinstance(description, str)
            or decision.get("approved_url") != record["source"] or decision.get("confirmed") is not True
            or not isinstance(basis, str) or not 10 <= len(basis.strip()) <= 2000):
        raise ValueError("Review the listed entity and record a reuse permission basis first.")
    text = title + "\n" + description
    return {"source": record["source"], "permission_basis": basis.strip(),
            "entity_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "terms_source": "https://www.wikidata.org/wiki/Wikidata:Copyright", "time": time.time()}
