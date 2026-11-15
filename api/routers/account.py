"""GET/PUT /account/saves (night-accounts). Called only by the Next.js server; see contracts (Accounts).

Off (404) unless ACCOUNT_API_TOKEN is set. The caller proves itself with X-Account-Token and names the user
with X-Subject-Hash (sha256 hex of AUTH_SECRET + Google subject). No email or name ever reaches this API."""
import hmac
import os
import re

from fastapi import APIRouter, Header, HTTPException

from api import db
from contracts.api_models import AccountSavesResponse, PutSavesRequest, SavedItem

router = APIRouter(prefix="/account", tags=["account"])

MAX_ITEMS = 500
_HASH = re.compile(r"^[0-9a-f]{64}$")


def _auth(token: str | None, subject_hash: str | None) -> str:
    expected = os.environ.get("ACCOUNT_API_TOKEN")
    if not expected:
        raise HTTPException(404, "Accounts are off")
    if not token or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(401, "Bad account token")
    if not subject_hash or not _HASH.match(subject_hash):
        raise HTTPException(400, "Bad subject hash")
    return subject_hash


def _load(h: str) -> list[SavedItem]:
    rows = db.fetch(
        "SELECT listing_id, saved_at, price_at_save, target FROM user_saves "
        "WHERE subject_hash = %s ORDER BY saved_at DESC", (h,))
    return [SavedItem(listing_id=r["listing_id"], saved_at=r["saved_at"],
                      price_at_save=db.num(r["price_at_save"]), target=db.num(r["target"])) for r in rows]


def _store(h: str, items: list[SavedItem], replace: bool) -> None:
    """Upsert the items; with replace, drop every stored row not in the list. One transaction."""
    try:
        with db.get_pool().connection() as conn:
            with conn.transaction():
                if replace:
                    conn.execute("DELETE FROM user_saves WHERE subject_hash = %s AND NOT (listing_id = ANY(%s))",
                                 (h, [i.listing_id for i in items]))
                for i in items:
                    conn.execute(
                        "INSERT INTO user_saves (subject_hash, listing_id, saved_at, price_at_save, target) "
                        "VALUES (%s, %s, %s, %s, %s) "
                        "ON CONFLICT (subject_hash, listing_id) DO UPDATE SET "
                        "saved_at = EXCLUDED.saved_at, price_at_save = EXCLUDED.price_at_save, target = EXCLUDED.target",
                        (h, i.listing_id, i.saved_at,
                         None if i.price_at_save is None else round(i.price_at_save),
                         None if i.target is None else round(i.target)))
    except db.DBUnavailable:
        raise
    except Exception as e:
        raise db.DBUnavailable(str(e)) from e


def _merge(stored: list[SavedItem], incoming: list[SavedItem]) -> list[SavedItem]:
    """Union by listing; the incoming copy wins a clash, but the older saved_at is kept."""
    out = {s.listing_id: s for s in stored}
    for i in incoming:
        old = out.get(i.listing_id)
        if old and old.saved_at < i.saved_at:
            i = i.model_copy(update={"saved_at": old.saved_at})
        out[i.listing_id] = i
    return sorted(out.values(), key=lambda s: s.saved_at, reverse=True)


def _db_call(fn, *a):
    try:
        return fn(*a)
    except db.DBUnavailable as e:
        raise HTTPException(503, "Saves are unavailable right now") from e


@router.get("/saves", response_model=AccountSavesResponse)
def get_saves(x_account_token: str | None = Header(default=None),
              x_subject_hash: str | None = Header(default=None)) -> AccountSavesResponse:
    h = _auth(x_account_token, x_subject_hash)
    return AccountSavesResponse(items=_db_call(_load, h))


@router.put("/saves", response_model=AccountSavesResponse)
def put_saves(req: PutSavesRequest, x_account_token: str | None = Header(default=None),
              x_subject_hash: str | None = Header(default=None)) -> AccountSavesResponse:
    h = _auth(x_account_token, x_subject_hash)
    if len(req.items) > MAX_ITEMS:
        raise HTTPException(413, f"At most {MAX_ITEMS} saves")
    items = list({i.listing_id: i for i in req.items}.values())
    if req.merge:
        items = _merge(_db_call(_load, h), items)
        if len(items) > MAX_ITEMS:
            raise HTTPException(413, f"At most {MAX_ITEMS} saves")
    _db_call(_store, h, items, True)  # the full resulting list replaces the stored one
    return AccountSavesResponse(items=_db_call(_load, h))
