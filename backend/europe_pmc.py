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


def abstract_request_url(source):
    """Build one metadata request from a supported, previously reviewed publication URL."""
    from urllib.parse import urlencode
    match = re.fullmatch(r"https://europepmc\.org/article/(MED/[0-9]+|PMC/PMC[0-9]+)", source) if isinstance(source, str) else None
    if not match:
        raise ValueError("Approve a supported publication URL first.")
    database, identity = match[1].split("/")
    return "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urlencode({
        "query": f"EXT_ID:{identity} AND SRC:{database}", "format": "json", "resultType": "core", "pageSize": 1,
    })


def publication_abstract(payload, source):
    """Validate publication identity and return display text without reuse permission."""
    from html import unescape
    abstract_request_url(source)
    results = payload.get("resultList", {}).get("result") if isinstance(payload, dict) and isinstance(payload.get("resultList"), dict) else None
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        raise ValueError("Europe PMC returned invalid abstract metadata.")
    record = results[0]
    if f"https://europepmc.org/article/{record.get('source')}/{record.get('id')}" != source:
        raise ValueError("The abstract metadata does not match the approved publication.")
    text = record.get("abstractText", "")
    if not isinstance(text, str) or len(text) > 50000:
        raise ValueError("Europe PMC returned unreadable abstract metadata.")
    text = " ".join(unescape(re.sub(r"<[^>]+>", " ", text)).split())
    if any(unicodedata.category(c) in {"Cc", "Cs"} for c in text):
        raise ValueError("Europe PMC returned unreadable abstract metadata.")
    return {"abstract": text, "abstract_reviewed": True, "reuse_status": "unverified"}


def abstract_reuse_evidence(record, decision):
    """Record an explicit human permission decision tied to the reviewed abstract."""
    import hashlib
    import time
    basis = decision.get("permission_basis")
    text = record.get("abstract")
    if (decision.get("approved_url") != record.get("source")
            or decision.get("confirmed") is not True
            or not isinstance(basis, str) or not 10 <= len(basis.strip()) <= 2000
            or record.get("abstract_reviewed") is not True
            or not isinstance(text, str) or not text):
        raise ValueError("Review the abstract and record a reuse permission basis first.")
    return {"source": record["source"], "permission_basis": basis.strip(),
            "abstract_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "time": time.time()}


def approved_abstract_rows(records, approved_urls):
    """Validate collection consent and permission against the current abstract text."""
    import hashlib
    if (not isinstance(approved_urls, list) or not approved_urls
            or any(not isinstance(url, str) for url in approved_urls)
            or len(set(approved_urls)) != len(approved_urls)):
        raise ValueError("Select publication URLs before approving collection.")
    selected = [record for record in records if record.get("source") in approved_urls]
    if len(selected) != len(approved_urls):
        raise ValueError("Approve only listed publication URLs.")
    rows = []
    for record in selected:
        text, approval = record.get("abstract"), record.get("reuse_approval")
        if (record.get("abstract_reviewed") is not True or record.get("reuse_status") != "user_approved"
                or not isinstance(text, str) or len(text) < 40 or not isinstance(approval, dict)
                or approval.get("source") != record["source"]
                or approval.get("abstract_sha256") != hashlib.sha256(text.encode("utf-8")).hexdigest()):
            raise ValueError("Review the abstract and record current reuse permission before collection.")
        rows.append({**record, "provider": "europe_pmc", "text": text, "group": record["source"]})
    return rows
