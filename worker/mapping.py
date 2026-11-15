"""Map step: apply a source template to a raw payload and build a CanonicalListing.

Two stages so Gemini can sit between them: `map_payload` -> draft dict (mapped fields only),
worker.llm_extract fills the fields the template left empty, `build_listing` validates.
"""
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from contracts.canonical import CanonicalListing
from worker.clean import beds_from, normalize_address, normalize_unit, redact_text, sha256_text

ROOT = Path(__file__).resolve().parent.parent


def load_template(source_key: str) -> dict:
    text = (ROOT / "sources" / f"{source_key}.yaml").read_text()
    text = re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), text)
    return yaml.safe_load(text)


def load_zips(path: str = "data/zips.txt") -> list[str]:
    lines = (ROOT / path).read_text().splitlines()[1:]
    return [ln.split(",")[0].strip() for ln in lines if ln.strip()]


def get_path(obj, path: str):
    """'a.b.c' lookup; the first of 'a|b' that is not empty wins."""
    for alt in path.split("|"):
        cur = obj
        for part in alt.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is None:
                break
        if cur not in (None, "", []):
            return cur
    return None


def _num(v, cast):
    if v is None or v == "":
        return None
    try:
        if isinstance(v, str):
            v = re.sub(r"[^\d.\-]", "", v)
        return cast(float(v))
    except (ValueError, TypeError):
        return None


def explode(template: dict, payload: dict) -> list[dict]:
    """One payload per floor plan (apartments_com); everything else is one record."""
    field = template.get("explode")
    if not field:
        return [payload]
    items = payload.get(field) or []
    base = {k: v for k, v in payload.items() if k != field}
    out = []
    for i, item in enumerate(items):
        rec = dict(base, floor_plan=item)
        rec["id"] = f"{payload.get('id')}#{item.get('id', i)}"
        out.append(rec)
    return out


def keep_payload(template: dict, payload: dict) -> bool:
    for field, allowed in (template.get("keep_if") or {}).items():
        if payload.get(field) not in allowed:
            return False
    return True


def parse_observed(v, default: datetime) -> datetime:
    if not v:
        return default
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return default


def map_history(template: dict, payload: dict) -> list[dict]:
    h = template.get("history")
    if not h:
        return []
    rows = get_path(payload, h["path"])
    if not isinstance(rows, list):
        return []   # off-market homes come back with null history: never invent one
    keep = set(h.get("keep_events") or [])
    out, seen = [], set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        ev, d, p = r.get(h["event"]), r.get(h["date"]), _num(r.get(h["price"]), int)
        if not d or not p or p <= 0 or (keep and ev not in keep):
            continue
        key = (str(d)[:10], p)
        if key in seen:
            continue
        seen.add(key)
        out.append({"date": str(d)[:10], "price_usd": p, "event": str(ev).lower().replace(" ", "_")})
    return sorted(out, key=lambda x: x["date"])


def map_payload(template: dict, payload: dict, observed_at: datetime) -> dict | None:
    """Mapped fields as a draft dict, or None when the record is out of scope (wrong status or ZIP)."""
    if not keep_payload(template, payload):
        return None
    m = template["map"]
    d: dict = {"source_key": template["source_key"], "listing_type": template["listing_type"]}
    ext = get_path(payload, m["external_id"])
    if ext is None:
        return None
    d["external_id_hash"] = sha256_text(str(ext))
    d["observed_at"] = parse_observed(get_path(payload, m["observed_at"]), observed_at) if "observed_at" in m else observed_at
    conf: dict[str, float] = {}

    def put(field, value):
        if value is not None:
            d[field] = value
            conf[field] = 1.0

    put("price_usd", _num(get_path(payload, m["price_usd"]), int) if "price_usd" in m else None)
    put("price_max_usd", _num(get_path(payload, m["price_max_usd"]), int) if "price_max_usd" in m else None)
    put("beds", beds_from(get_path(payload, m["beds"])) if "beds" in m else None)
    put("baths", _num(get_path(payload, m["baths"]), float) if "baths" in m else None)
    put("sqft", _num(get_path(payload, m["sqft"]), int) if "sqft" in m else None)
    put("year_built", _num(get_path(payload, m["year_built"]), int) if "year_built" in m else None)
    if "property_type" in m:
        raw = get_path(payload, m["property_type"])
        put("property_type", (template.get("property_types") or {}).get(raw, str(raw).lower() if raw else None))
    if "address_norm" in m:
        put("address_norm", normalize_address(get_path(payload, m["address_norm"])))
    if "unit_label" in m:
        put("unit_label", normalize_unit(get_path(payload, m["unit_label"])))
    if "zip" in m:
        z = get_path(payload, m["zip"])
        put("zip", str(z)[:5] if z else None)
    put("neighborhood", get_path(payload, m["neighborhood"]) if "neighborhood" in m else None)
    put("lat", _num(get_path(payload, m["lat"]), float) if "lat" in m else None)
    put("lng", _num(get_path(payload, m["lng"]), float) if "lng" in m else None)
    if "text" in m:
        put("text_redacted", redact_text(get_path(payload, m["text"])))

    z_filter = template.get("zip_filter")
    if z_filter and d.get("zip") and d["zip"] not in load_zips(z_filter):
        return None

    extras = {}
    for name, path in (template.get("extras_map") or {}).items():
        v = get_path(payload, path)
        if v is not None:
            extras[name] = v
    d["extras"] = extras
    d["field_confidence"] = conf
    d["location_precision"] = template["location_precision"] if d.get("address_norm") or template["location_precision"] != "address" else "zip"
    d["price_history"] = map_history(template, payload)
    return d


def build_listing(draft: dict) -> CanonicalListing | None:
    """Validate a draft into a CanonicalListing; None when there is no price to carry."""
    if not draft.get("price_usd"):
        return None
    d = dict(draft)
    conf = d.get("field_confidence", {})
    llm = [k for k, v in conf.items() if v < 1.0]
    mapped = [k for k, v in conf.items() if v >= 1.0 and k != "text_redacted"]   # the text is input, not a fact
    d["extraction"] = "mapped" if not llm else ("llm" if not mapped else "mixed")
    return CanonicalListing(**d)


def drop_building_level_history(listings: list[CanonicalListing]) -> int:
    """A rental's history is kept only if no other unit at the same address carries the same history.
    Identical histories across units describe the building, never one unit. Returns how many were dropped."""
    groups: dict[tuple, list[CanonicalListing]] = {}
    for l in listings:
        if l.price_history and l.address_norm:
            key = (l.zip, l.address_norm, tuple((h["date"], h["price_usd"], h["event"]) for h in l.price_history))
            groups.setdefault(key, []).append(l)
    n = 0
    for members in groups.values():
        if len({m.external_id_hash for m in members}) > 1:
            for m in members:
                m.price_history = []
                n += 1
    return n
