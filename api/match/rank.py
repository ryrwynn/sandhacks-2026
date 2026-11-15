from contracts.api_models import MatchRequest, MatchResponse


def match(req: MatchRequest) -> MatchResponse:
    """Hard filters, then price fit + amenity fit + fair-rent position + semantic similarity. Never demographics."""
    raise NotImplementedError
