"""GET/PUT /account/saves (night-accounts). Called only by the Next.js server; see contracts (Accounts).
Off (404) unless ACCOUNT_API_TOKEN is set."""
from fastapi import APIRouter, Header

from api.routers._stub import not_built
from contracts.api_models import AccountSavesResponse, PutSavesRequest

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/saves", response_model=AccountSavesResponse)
def get_saves(x_account_token: str | None = Header(default=None),
              x_subject_hash: str | None = Header(default=None)) -> AccountSavesResponse:
    raise not_built("Accounts")


@router.put("/saves", response_model=AccountSavesResponse)
def put_saves(req: PutSavesRequest, x_account_token: str | None = Header(default=None),
              x_subject_hash: str | None = Header(default=None)) -> AccountSavesResponse:
    raise not_built("Accounts")
