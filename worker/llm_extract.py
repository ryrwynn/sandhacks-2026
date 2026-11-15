"""Gemini extraction for fields a template left empty.

Calls only api.llm.gemini.parse_listing (it caches, so the same text is never parsed twice). Quota rules:
- ask only for fields the template left empty, only when there is text to read (and, if the template
  sets `only_if_text_matches`, only when the text matches it);
- at most LLM_EXTRACT_MAX_PER_RUN calls per run (default 40), newest listings first; the rest wait;
- a None answer means the listing is stored with its mapped fields; never retried in this run.
"""
import os
import re

from api.llm.gemini import parse_listing

DEFAULT_MAX = 40
CONFIDENCE = 0.6


class LlmBudget:
    def __init__(self, max_calls: int | None = None):
        if max_calls is None:
            try:
                max_calls = int(os.environ.get("LLM_EXTRACT_MAX_PER_RUN", DEFAULT_MAX))
            except ValueError:
                max_calls = DEFAULT_MAX
        self.max_calls = max_calls
        self.used = 0
        self.empty = 0      # calls that returned nothing

    def take(self) -> bool:
        if self.used >= self.max_calls:
            return False
        self.used += 1
        return True


def missing_fields(template: dict, draft: dict) -> list[str]:
    spec = template.get("llm_extract") or {}
    return [f for f in spec.get("fields", []) if draft.get(f) is None and f != "is_rental_offer"]


def needs_llm(template: dict, draft: dict) -> bool:
    spec = template.get("llm_extract")
    if not spec:
        return False
    text = draft.get("text_redacted")
    if not text:
        return False
    pattern = spec.get("only_if_text_matches")
    if pattern and not re.search(pattern, text):
        return False
    return bool(missing_fields(template, draft)) or bool(spec.get("keep_if"))


def fill_missing(template: dict, draft: dict, budget: LlmBudget) -> bool:
    """Fill empty fields in `draft` from Gemini. Returns False when the template's keep_if rejects the post."""
    if not needs_llm(template, draft):
        return True
    spec = template["llm_extract"]
    if not budget.take():
        return not spec.get("keep_if")      # unread posts wait for the next run; listing sites keep mapped fields
    parsed = parse_listing(draft["text_redacted"])   # text is already redacted: no names or phones leave
    if parsed is None:
        budget.empty += 1
        return not spec.get("keep_if")
    draft.setdefault("extras", {})["llm_parsed"] = True     # later runs skip this listing
    values = parsed.model_dump()
    keep = spec.get("keep_if")
    if keep and values.get(keep) is False:
        return False
    if keep and values.get(keep) is None:
        return False
    for f in missing_fields(template, draft):
        v = values.get(f)
        if v is not None:
            draft[f] = v
            draft["field_confidence"][f] = CONFIDENCE
    return True
