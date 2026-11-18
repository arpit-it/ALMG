"""Normalize a bounded World Bank indicator catalog page for review."""
import re
import unicodedata
from urllib.parse import urlencode


def indicator_candidates(payload, *, limit=20):
    if (not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[0], dict)
            or payload[0].get("page") != 1 or not isinstance(payload[1], list)):
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
