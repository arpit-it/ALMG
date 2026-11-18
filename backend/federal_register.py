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


def summary_request_url(source):
    """Build one document metadata request from an approved review URL."""
    from urllib.parse import urlencode
    match = re.fullmatch(r"https://www\.federalregister\.gov/documents/[0-9]{4}/[0-9]{2}/[0-9]{2}/([0-9]{4}-[0-9]{5})/[A-Za-z0-9_-]+/?", source) if isinstance(source, str) else None
    if not match:
        raise ValueError("Approve a supported document URL first.")
    return f"https://www.federalregister.gov/api/v1/documents/{match[1]}.json?" + urlencode([
        ("fields[]", field) for field in ("title", "document_number", "html_url", "abstract")
    ])


def document_summary(payload, source):
    """Validate identity and display summary metadata without granting reuse."""
    from html import unescape
    summary_request_url(source)
    candidates = document_candidates({"results": [payload]}, "", limit=1)
    if len(candidates) != 1 or candidates[0]["source"] != source:
        raise ValueError("Summary metadata does not match the approved document URL.")
    text = payload.get("abstract")
    if text is None:
        text = ""
    if not isinstance(text, str) or len(text) > 30000:
        raise ValueError("Federal Register returned unreadable summary metadata.")
    text = " ".join(unescape(re.sub(r"<[^>]+>", " ", text)).split())
    if any(unicodedata.category(c) in {"Cc", "Cs"} for c in text):
        raise ValueError("Federal Register returned unreadable summary metadata.")
    return {"title": candidates[0]["title"], "summary": text, "summary_reviewed": True, "reuse_status": "unverified"}


def summary_reuse_evidence(record, decision):
    """Bind an explicit human reuse decision to a reviewed document summary."""
    import hashlib
    import time
    source = record.get("source")
    summary_request_url(source)
    title, summary, basis = record.get("title"), record.get("summary"), decision.get("permission_basis")
    if (record.get("summary_reviewed") is not True or not isinstance(title, str)
            or not isinstance(summary, str) or not summary
            or decision.get("approved_url") != source or decision.get("confirmed") is not True
            or decision.get("approved_scope") != "document_summary"
            or not isinstance(basis, str) or not 10 <= len(basis.strip()) <= 2000):
        raise ValueError("Review the summary and record permission for that summary scope first.")
    return {"source": source, "scope": "document_summary", "permission_basis": basis.strip(),
            "summary_sha256": hashlib.sha256((title + "\n" + summary).encode("utf-8")).hexdigest(), "time": time.time()}
