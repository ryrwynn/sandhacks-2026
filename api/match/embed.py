"""Fill listing_embeddings for shared-table listings. Run: python -m api.match.embed [max_requests].

Skips listings whose text_hash is already stored, sends BATCH texts per request, and stops at the
requests budget (EMBED_REQUEST_BUDGET, default 900 in total) or the first failure. Never loops on failure.
"""
import hashlib
import logging
import sys

from api import db
from api.llm import gemini
from api.match import store

log = logging.getLogger("rentorknot.embed")
BATCH = 50
MAX_CHARS = 1500


def listing_doc(r: dict) -> str:
    zip_ = (r["zip"] or "").strip()
    area = db.ZIP_NAMES.get(zip_)
    bits = []
    if r.get("beds") is not None:
        bits.append("studio" if r["beds"] == 0 else f"{r['beds']} bedroom")
    if r.get("baths") is not None:
        bits.append(f"{float(r['baths']):g} bath")
    if r.get("sqft"):
        bits.append(f"{r['sqft']} sqft")
    if r.get("property_type"):
        bits.append(str(r["property_type"]).replace("_", " "))
    head = ", ".join(bits)
    body = f"{head}. {r['text_redacted'][:MAX_CHARS]}" if head else r["text_redacted"][:MAX_CHARS]
    return gemini.document_text(area, body)


def embed_missing(max_requests: int = 900, scan: int = 50000) -> dict:
    have = store.stored_hashes(gemini.EMBED_MODEL)
    todo = []
    for r in store.embeddable(scan):
        doc = listing_doc(r)
        h = hashlib.sha256(doc.encode()).hexdigest()
        if have.get(r["listing_id"]) != h:
            todo.append((r["listing_id"], doc, h))
    stored = requests = 0
    for i in range(0, len(todo), BATCH):
        if requests >= max_requests:
            break
        chunk = todo[i:i + BATCH]
        before = gemini.embed_spent()
        vecs = gemini.embed_texts([d for _, d, _ in chunk])
        requests += max(0, gemini.embed_spent() - before)
        if vecs is None:
            break   # budget or quota used up, or a failure: stop, don't retry
        for (lid, _, h), v in zip(chunk, vecs):
            store.put_embedding(lid, gemini.EMBED_MODEL, h, v)
            stored += 1
    return {"pending": len(todo), "stored": stored, "requests": requests, "total_requests": gemini.embed_spent()}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(embed_missing(int(sys.argv[1]) if len(sys.argv) > 1 else 900))
