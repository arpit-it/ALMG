"""Normalize Crossref bibliographic metadata without fetching publisher content."""
import re
import unicodedata
from urllib.parse import quote


def bibliographic_candidates(payload, query, *, limit=20):
    message = payload.get("message") if isinstance(payload, dict) and payload.get("status") == "ok" else None
    results = message.get("items") if isinstance(message, dict) else None
    if not isinstance(results, list):
        raise ValueError("Crossref returned invalid bibliographic metadata.")
    rows, seen = [], set()
    for item in results[:limit]:
        if not isinstance(item, dict):
            continue
        doi, titles = item.get("DOI"), item.get("title")
        publisher, kind = item.get("publisher", ""), item.get("type", "")
        if (not isinstance(doi, str) or not re.fullmatch(r"10\.[0-9]{4,9}/[-._;()/:A-Za-z0-9]+", doi)
                or any(part in {".", ".."} for part in doi.split("/"))
                or not isinstance(titles, list) or not titles or not isinstance(titles[0], str)
                or not isinstance(publisher, str) or not isinstance(kind, str)):
            continue
        title = titles[0].strip()
        if (not title or len(title) > 2000 or len(publisher) > 1000 or len(kind) > 100
                or any(unicodedata.category(c) in {"Cc", "Cs"} for c in title + publisher + kind)
                or doi.lower() in seen):
            continue
        seen.add(doi.lower())
        rows.append({"doi": doi, "title": title, "publisher": publisher, "work_type": kind,
                     "source": "https://doi.org/" + quote(doi, safe=""), "provider": "crossref",
                     "approved_query": query, "reuse_status": "unverified"})
    return rows
