"""Normalize Europe PMC publication metadata without granting reuse rights."""
import re
import unicodedata


def publication_candidates(payload, query, *, limit=20):
    results = payload.get("resultList", {}).get("result") if isinstance(payload, dict) and isinstance(payload.get("resultList"), dict) else None
    if not isinstance(results, list):
        raise ValueError("Europe PMC returned invalid publication metadata.")
    candidates = []
    seen = set()
    for result in results[:limit]:
        if not isinstance(result, dict):
            continue
        source, identity, title = (result.get(key) for key in ("source", "id", "title"))
        if not isinstance(identity, str) or not isinstance(title, str):
            continue
        if not ((source == "MED" and re.fullmatch(r"[0-9]+", identity))
                or (source == "PMC" and re.fullmatch(r"PMC[0-9]+", identity))):
            continue
        title = title.strip()
        if not title or any(unicodedata.category(c) in {"Cc", "Cs"} for c in title):
            continue
        url = f"https://europepmc.org/article/{source}/{identity}"
        if url in seen:
            continue
        seen.add(url)
        candidates.append({"source": url, "title": title[:500], "provider": "europe_pmc",
                           "approved_query": query, "reuse_status": "unverified"})
    return candidates
