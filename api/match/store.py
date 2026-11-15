"""Database reads and writes for matching (embeddings, listing text). Everything else goes through api/db.py."""
import json
import math

from api import db


def candidates(limit: int = 2000) -> list[dict]:
    """Rows from db.listing_page: one per rental listing with its latest price."""
    return db.listing_page(limit=limit, sort="recent")


def texts(ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = db.fetch("SELECT listing_id, text_redacted FROM listings WHERE listing_id = ANY(%s)", (ids,))
    return {r["listing_id"]: r["text_redacted"] or "" for r in rows}


def _vec_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def cosines(query: list[float], ids: list[int], model: str) -> dict[int, float]:
    """Cosine similarity of the query to each stored listing vector. pgvector does the work; if the
    operator is missing, the vectors come back as text and Python does it."""
    if not ids:
        return {}
    try:
        rows = db.fetch("SELECT listing_id, 1 - (embedding <=> %s::vector) AS cos FROM listing_embeddings "
                        "WHERE model = %s AND listing_id = ANY(%s)", (_vec_literal(query), model, ids))
        return {r["listing_id"]: float(r["cos"]) for r in rows}
    except db.DBUnavailable:
        raise
    except Exception:
        rows = db.fetch("SELECT listing_id, embedding::text AS v FROM listing_embeddings "
                        "WHERE model = %s AND listing_id = ANY(%s)", (model, ids))
        qn = math.sqrt(sum(x * x for x in query)) or 1.0
        out = {}
        for r in rows:
            v = json.loads(r["v"])
            vn = math.sqrt(sum(x * x for x in v)) or 1.0
            out[r["listing_id"]] = sum(a * b for a, b in zip(query, v)) / (qn * vn)
        return out


def stored_hashes(model: str) -> dict[int, str]:
    rows = db.fetch("SELECT listing_id, text_hash FROM listing_embeddings WHERE model = %s", (model,))
    return {r["listing_id"]: r["text_hash"] for r in rows}


def put_embedding(listing_id: int, model: str, text_hash: str, vec: list[float]) -> None:
    db.execute("INSERT INTO listing_embeddings (listing_id, model, text_hash, embedding) "
               "VALUES (%s, %s, %s, %s::vector) ON CONFLICT (listing_id, model) DO UPDATE "
               "SET text_hash = EXCLUDED.text_hash, embedding = EXCLUDED.embedding, created_at = now()",
               (listing_id, model, text_hash, _vec_literal(vec)))


def embeddable(limit: int) -> list[dict]:
    """Shared-table rental listings that have text, newest first."""
    return db.fetch(
        "SELECT l.listing_id, l.zip, l.beds, l.baths, l.sqft, l.text_redacted, p.property_type "
        "FROM listings l LEFT JOIN properties p ON p.property_id = l.property_id "
        "WHERE l.listing_type = 'rent' AND l.text_redacted IS NOT NULL AND length(l.text_redacted) > 20 "
        "ORDER BY l.last_seen DESC LIMIT %s", (limit,))
