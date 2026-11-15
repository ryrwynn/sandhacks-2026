import logging
from collections import OrderedDict
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException

from api import db
from api.llm import gemini
from api.rules import ab1482
from api.routers._common import safe
from contracts.api_models import CheckRequest, CheckResponse, Lang, LetterResponse

log = logging.getLogger("rentorknot.api")
router = APIRouter(prefix="/checks", tags=["checks"])

# Recent checks kept in memory so a letter works even when the database write failed.
_recent: "OrderedDict[UUID, tuple[CheckResponse, str, list[str]]]" = OrderedDict()

# Used only when rent_caps can't be read (database down); same figures as docs/PLAN.md.
FALLBACK_CAPS = [
    ab1482.RentCap("san_diego_county", date(2025, 8, 1), date(2026, 7, 31), Decimal("8.80"),
                   "https://www.goodlifemgmt.com/blog/california-rent-cap-2026/"),
    ab1482.RentCap("san_diego_county", date(2026, 8, 1), date(2027, 7, 31), Decimal("8.20"),
                   "https://www.goodlifemgmt.com/blog/california-rent-cap-2026/"),
]


def load_caps() -> list[ab1482.RentCap]:
    loader = getattr(ab1482, "load_caps", None)
    try:
        if loader:
            return _load_with_engine(loader) or FALLBACK_CAPS
        rows = db.read_rent_caps()
    except Exception as e:  # database down, or engine loader not implemented
        log.warning("rent_caps unavailable, using built-in caps: %s", e)
        return FALLBACK_CAPS
    caps = [ab1482.RentCap(r["region"], r["period_start"], r["period_end"], Decimal(str(r["cap_pct"])),
                           r["source_url"]) for r in rows]
    return caps or FALLBACK_CAPS


def _load_with_engine(loader):
    """Lane B's load_caps(conn) takes a connection; borrow one from the pool."""
    with db.get_pool().connection() as conn:
        return loader(conn)


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _figures(r: CheckResponse) -> list[str]:
    out = []
    for v in (r.max_legal_rent, r.overage_monthly, r.overage_yearly):
        if v is not None:
            out.append(_money(v))
    for p in (r.cap_pct, r.increase_pct):
        if p is not None:
            out.append(f"{p:g}%")
    return out


def _f(v):
    return None if v is None else float(v)


@router.post("", response_model=CheckResponse)
def create_check(req: CheckRequest) -> CheckResponse:
    inp = ab1482.CheckInput(
        lowest_rent_12mo=Decimal(str(req.lowest_rent_12mo)), new_rent=Decimal(str(req.new_rent)),
        effective_date=req.effective_date, year_built=req.year_built, property_type=req.property_type,
        got_exemption_notice=req.got_exemption_notice, owner_is_corporate=req.owner_is_corporate,
        other_exemption=req.other_exemption, increases_last_12mo=req.increases_last_12mo)
    try:
        res = ab1482.check_increase(inp, load_caps())
    except NotImplementedError:
        raise HTTPException(503, "The rent-cap check is not available yet")
    inc = _f(res.increase_pct)
    if inc is None:
        inc = round((req.new_rent - req.lowest_rent_12mo) / req.lowest_rent_12mo * 100, 1)
    max_legal = _f(res.max_legal_rent)
    try:
        check_id = db.insert_check(req.address, req.zip, req.lowest_rent_12mo, req.new_rent, req.effective_date,
                                   req.year_built, res.verdict, max_legal, req.is_demo)
    except db.DBUnavailable as e:
        log.warning("rent_checks insert failed, returning an unsaved id: %s", e)
        check_id = uuid4()
    out = CheckResponse(check_id=check_id, verdict=res.verdict, cap_pct=_f(res.cap_pct), max_legal_rent=max_legal,
                        increase_pct=inc, overage_monthly=_f(res.overage_monthly),
                        overage_yearly=_f(res.overage_yearly), third_increase=res.third_increase,
                        reasons=res.reasons)
    _recent[out.check_id] = (out, req.address, list(res.figures) or _figures(out))
    while len(_recent) > 200:
        _recent.popitem(last=False)
    return out


def _find_check(check_id: UUID):
    if check_id in _recent:
        return _recent[check_id]
    try:
        row = db.get_check(check_id)
    except db.DBUnavailable:
        row = None
    if row is None:
        raise HTTPException(404, "Unknown check id")
    lowest, new = float(row["lowest_rent_12mo"]), float(row["new_rent"])
    cap_pct = None
    max_legal = db.num(row["max_legal_rent"])
    if max_legal:
        cap_pct = round((max_legal / lowest - 1) * 100, 1)
    resp = CheckResponse(check_id=check_id, verdict=row["verdict"], cap_pct=cap_pct, max_legal_rent=max_legal,
                         increase_pct=round((new - lowest) / lowest * 100, 1),
                         overage_monthly=round(new - max_legal, 2) if max_legal and new > max_legal else None,
                         reasons=[])
    return resp, row["address"], _figures(resp)


@router.post("/{check_id}/letter", response_model=LetterResponse)
def check_letter(check_id: UUID, lang: Lang = "en") -> LetterResponse:
    resp, address, figures = _find_check(check_id)
    payload = {**resp.model_dump(mode="json"), "figures": figures}
    explanation = letter = None
    try:
        explanation = gemini.explain_verdict(payload, lang)
        letter = gemini.draft_letter(payload, address)
    except Exception as e:  # text is optional: never fail or retry because Gemini did
        log.warning("gemini text unavailable: %s", e)
    return LetterResponse(check_id=check_id, lang=lang, explanation=explanation, letter_en=letter,
                          figures=figures)
