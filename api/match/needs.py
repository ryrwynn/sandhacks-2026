from contracts.api_models import ParsedNeeds


def parse_needs(text: str) -> ParsedNeeds:
    """Gemini (cached by text) turns plain language into constraints; a rules fallback when Gemini fails."""
    raise NotImplementedError
