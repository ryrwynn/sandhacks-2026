import logging

from fastapi import APIRouter, HTTPException

from api import db
from api.llm import gemini
from api.ml import scoring
from api.routers._common import score_rows, zip_data
from contracts.api_models import RankedZip, RankRequest, RankResponse

log = logging.getLogger("rentorknot.api")
router = APIRouter(prefix="/neighborhoods", tags=["neighborhoods"])
SUMMARY_TOP_N = 3   # Gemini quota: "why this ZIP" for the top 3 only


@router.post("/rank", response_model=RankResponse)
def rank(req: RankRequest) -> RankResponse:
    data = zip_data()
    rows = score_rows(data, req.beds if req.persona == "starter" else None)
    try:
        res = scoring.score_zips(rows, req.persona, req.budget_usd, req.weights)
    except NotImplementedError:
        raise HTTPException(503, "Neighborhood scoring is not available yet")

    def build(items, rank_from: int, summarize: bool) -> list[RankedZip]:
        out = []
        for i, it in enumerate(items):
            z = it["zip"]
            summary = None
            if summarize and i < SUMMARY_TOP_N:
                try:
                    summary = gemini.zip_summary(db.ZIP_NAMES.get(z, z), req.persona, it["top_contributions"])
                except Exception as e:  # optional text: no retry
                    log.warning("zip_summary failed: %s", e)
            out.append(RankedZip(rank=rank_from + i, zip=z, name=db.ZIP_NAMES.get(z, z),
                                 score=round(it["score"], 1), price_usd=it.get("price_usd"),
                                 top_contributions=it["top_contributions"], summary=summary))
        return out

    ranked = build(res["ranked"], 1, True)
    stretch = build(res["stretch"], len(ranked) + 1, False)
    return RankResponse(persona=req.persona, budget_usd=req.budget_usd, beds=req.beds, weights=res["weights"],
                        ranked=ranked, stretch=stretch)
