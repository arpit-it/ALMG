"""Normalize Crossref bibliographic metadata without fetching publisher content."""
import re
import unicodedata
from urllib.parse import quote


def valid_doi(value):
    return (isinstance(value, str) and re.fullmatch(r"10\.[0-9]{4,9}/[-._;()/:A-Za-z0-9]+", value)
            and not any(part in {".", ".."} for part in value.split("/")))


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
        if (not valid_doi(doi)
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


def abstract_request_url(doi):
    if not valid_doi(doi):
        raise ValueError("Approve a supported Crossref DOI first.")
    return "https://api.crossref.org/works/" + quote(doi, safe="")


def abstract_metadata(payload, doi):
    """Validate a work and preserve license links without inferring abstract rights."""
    from html import unescape
    from urllib.parse import urlsplit
    abstract_request_url(doi)
    work = payload.get("message") if isinstance(payload, dict) and payload.get("status") == "ok" else None
    rows = bibliographic_candidates({"status": "ok", "message": {"items": [work]}}, "", limit=1)
    if len(rows) != 1 or rows[0]["doi"].lower() != doi.lower():
        raise ValueError("Crossref metadata does not match the approved DOI.")
    text = work.get("abstract", "")
    if not isinstance(text, str) or len(text) > 50000:
        raise ValueError("Crossref returned unreadable abstract metadata.")
    text = " ".join(unescape(re.sub(r"<[^>]+>", " ", text)).split())
    if any(unicodedata.category(c) in {"Cc", "Cs"} for c in text):
        raise ValueError("Crossref returned unreadable abstract metadata.")
    licenses = work.get("license", [])
    if not isinstance(licenses, list) or len(licenses) > 20:
        raise ValueError("Crossref returned unreadable license metadata.")
    cleaned = []
    for entry in licenses:
        if not isinstance(entry, dict):
            raise ValueError("Crossref returned unreadable license metadata.")
        url, version = entry.get("URL"), entry.get("content-version", "")
        if (not isinstance(url, str) or not isinstance(version, str) or len(url) > 2000 or len(version) > 100
                or any(unicodedata.category(c) in {"Cc", "Cs"} for c in url + version)):
            raise ValueError("Crossref returned unreadable license metadata.")
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("Crossref returned unreadable license metadata.")
        cleaned.append({"url": url, "content_version": version})
    return {"title": rows[0]["title"], "publisher": rows[0]["publisher"], "work_type": rows[0]["work_type"],
            "abstract": text, "abstract_reviewed": True, "license_statements": cleaned, "reuse_status": "unverified"}
