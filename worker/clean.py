"""Clean step: redact personal data from text, normalize addresses and bedroom counts."""
import hashlib
import json
import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<!\w)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
URL = re.compile(r"https?://\S+|www\.\S+")
# "Contact Maria", "call Mr. Lee", "ask for Jo Smith", "listed by ...": the capitalized words after a cue.
NAME_CUE = re.compile(
    r"(?i:\b(?:contact|call|text|ask for|ask|message|msg|dm|email|reach|listed by|listing agent|agent|manager|"
    r"owner|landlord|attn|attention)\b[:\s]+(?:(?i:mr|mrs|ms|dr)\.?\s+)?)"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
)

ABBREV = {
    "street": "st", "avenue": "ave", "boulevard": "blvd", "drive": "dr", "road": "rd", "court": "ct",
    "lane": "ln", "place": "pl", "terrace": "ter", "way": "way", "highway": "hwy", "parkway": "pkwy",
    "circle": "cir", "north": "n", "south": "s", "east": "e", "west": "w",
}
UNIT_TAIL = re.compile(r"[\s,]+(?:apt|apartment|unit|ste|suite|#)\s*[\w-]+$", re.I)


def redact_text(text: str | None) -> str | None:
    if not text:
        return text
    text = EMAIL.sub("[email removed]", text)
    text = PHONE.sub("[phone removed]", text)
    text = URL.sub("[link removed]", text)
    text = NAME_CUE.sub(lambda m: m.group(0)[: m.start(1) - m.start(0)] + "[name removed]", text)
    return text


def normalize_address(addr: str | None) -> str | None:
    if not addr:
        return None
    a = addr.strip().lower()
    a = UNIT_TAIL.sub("", a)
    a = re.sub(r"[.,]", " ", a)
    a = re.sub(r"\s+#\S*$", "", a)
    words = [ABBREV.get(w, w) for w in a.split()]
    return " ".join(words) or None


def normalize_unit(unit) -> str | None:
    if unit is None:
        return None
    u = re.sub(r"(?i)^(apt|apartment|unit|ste|suite|#)\s*", "", str(unit).strip())
    return u.upper() or None


def beds_from(value) -> int | None:
    """'studio' is 0 bedrooms; numbers pass through."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        v = value.strip().lower()
        if "studio" in v:
            return 0
        m = re.search(r"\d+", v)
        return int(m.group()) if m else None
    return int(value)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def content_hash(payload: dict, ignore: list[str] | None = None) -> str:
    p = {k: v for k, v in payload.items() if k not in set(ignore or [])}
    return sha256_text(json.dumps(p, sort_keys=True, default=str, separators=(",", ":")))
