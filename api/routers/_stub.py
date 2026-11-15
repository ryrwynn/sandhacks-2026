"""Phase 1 stubs: an endpoint whose engine isn't built yet answers 501 instead of 500."""
from fastapi import HTTPException


def not_built(what: str) -> HTTPException:
    return HTTPException(501, f"{what} is not built yet")
