"""Validate Federal Register document search metadata for source review."""
import re
import unicodedata


def document_candidates(payload, query, *, limit=20):
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("Federal Register returned invalid search metadata.")
    rows, seen = [], set()
    for item in results[:limit]:
        if not isinstance(item, dict):
            continue
        number, title, source = (item.get(key) for key in ("document_number", "title", "html_url"))
        if (not isinstance(number, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{5}", number)
                or not isinstance(title, str) or not isinstance(source, str)):
            continue
        if (not re.fullmatch(r"https://www\.federalregister\.gov/documents/[0-9]{4}/[0-9]{2}/[0-9]{2}/"
                             + re.escape(number) + r"/[A-Za-z0-9_-]+/?", source)
                or not title.strip() or len(title) > 2000
                or any(unicodedata.category(c) in {"Cc", "Cs"} for c in title) or number in seen):
            continue
        seen.add(number)
        rows.append({"document_number": number, "title": title.strip(), "source": source,
                     "provider": "federal_register", "approved_query": query, "reuse_status": "unverified"})
    return rows
