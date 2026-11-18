"""Normalize a bounded World Bank indicator catalog page for review."""
import re
import unicodedata
from urllib.parse import urlencode


def indicator_candidates(payload, *, limit=20, expected_page=1):
    if (not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[0], dict)
            or type(payload[0].get("page")) is not int or payload[0]["page"] != expected_page
            or type(payload[0].get("pages", expected_page)) is not int
            or payload[0].get("pages", expected_page) < expected_page
            or not isinstance(payload[1], list)):
        raise ValueError("World Bank returned invalid indicator catalog metadata.")
    rows, seen = [], set()
    for item in payload[1][:limit]:
        if not isinstance(item, dict) or not isinstance(item.get("source"), dict):
            continue
        identity, name = item.get("id"), item.get("name")
        source_id, source_name = item["source"].get("id"), item["source"].get("value", "")
        note, organization = item.get("sourceNote", ""), item.get("sourceOrganization", "")
        values = (name, source_name, note, organization)
        if (not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", identity)
                or identity in {".", ".."} or not isinstance(source_id, str) or not re.fullmatch(r"[0-9]+", source_id)
                or any(not isinstance(value, str) or len(value) > 12000
                       or any(unicodedata.category(c) in {"Cc", "Cs"} for c in value) for value in values)
                or not name.strip() or (identity, source_id) in seen):
            continue
        seen.add((identity, source_id))
        rows.append({"indicator_id": identity, "title": name.strip(), "description": note.strip(),
                     "source_id": source_id, "source_name": source_name.strip(), "organization": organization.strip(),
                     "source": f"https://api.worldbank.org/v2/indicator/{identity}?" + urlencode({"source": source_id, "format": "json"}),
                     "provider": "world_bank", "reuse_status": "unverified"})
    return rows


def indicator_metadata_checksum(record):
    """Hash the reviewed description together with its source context."""
    import hashlib
    import json
    fields = {key: record.get(key) for key in ("indicator_id", "title", "description", "source_id", "source_name", "organization")}
    if any(not isinstance(value, str) for value in fields.values()):
        raise ValueError("Review the catalog metadata before recording permission.")
    return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def indicator_reuse_evidence(record, decision):
    """Record human permission for metadata descriptions, separately from observations."""
    import time
    identity, source_id = record.get("indicator_id"), record.get("source_id")
    basis = decision.get("permission_basis")
    if (not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", identity)
            or not isinstance(source_id, str) or not re.fullmatch(r"[0-9]+", source_id)
            or record.get("source") != f"https://api.worldbank.org/v2/indicator/{identity}?" + urlencode({"source": source_id, "format": "json"})
            or decision.get("approved_url") != record["source"] or decision.get("confirmed") is not True
            or decision.get("approved_scope") != "catalog_description"
            or not isinstance(basis, str) or not 10 <= len(basis.strip()) <= 2000):
        raise ValueError("Review the indicator description and record permission for that metadata scope.")
    return {"source": record["source"], "permission_basis": basis.strip(), "scope": "catalog_description",
            "metadata_sha256": indicator_metadata_checksum(record),
            "terms_source": "https://www.worldbank.org/ext/en/legal/terms-conditions", "time": time.time()}


def approved_description_rows(records, approved_urls):
    """Collect only selected metadata descriptions with current, scoped permission."""
    if (not isinstance(approved_urls, list) or not approved_urls
            or any(not isinstance(url, str) for url in approved_urls)
            or len(set(approved_urls)) != len(approved_urls)):
        raise ValueError("Select indicator description URLs before approving collection.")
    selected = [record for record in records if record.get("source") in approved_urls]
    if len(selected) != len(approved_urls):
        raise ValueError("Approve only listed indicator description URLs.")
    rows = []
    for record in selected:
        title, description, approval = record.get("title"), record.get("description"), record.get("reuse_approval")
        if not isinstance(title, str) or not isinstance(description, str):
            raise ValueError("Review the indicator description first.")
        text = title + "\n" + description
        if (len(text) < 40 or record.get("reuse_status") != "user_approved" or not isinstance(approval, dict)
                or approval.get("scope") != "catalog_description" or approval.get("source") != record.get("source")
                or approval.get("metadata_sha256") != indicator_metadata_checksum(record)):
            raise ValueError("Record current permission for each indicator catalog description before collection.")
        rows.append({**record, "provider": "world_bank", "text": text, "group": record["source"],
                     "collection_scope": "catalog_description"})
    return rows
