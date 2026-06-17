"""JAN double-check: confirm a fetched supplier page really is the product.

The user requirement is explicit: before a listing is reported as a buy
candidate, we must verify the supplier page and the sell destination refer to
the SAME product, with no mix-up. We do this conservatively with three signals,
strongest first:

1. JAN match   - the 13-digit JAN appears as a LOCAL run of digits (tolerating a
                 single space/hyphen between groups, e.g. "4902370 553024"), not
                 embedded inside a longer number. We deliberately do NOT match
                 against a whole-page digits-only projection, which would false-
                 positive on unrelated concatenated digit runs / JSON-LD / links.
2. Model match - the normalized alphanumeric model number (e.g. BEE-S-KB6CA ->
                 BEESKB6CA) appears on the page. Requires enough length and at
                 least two letters so it cannot collapse to a stray digit.
3. Name match  - at least two distinctive (non-stopword) name tokens appear.

Badges: ✅ jan / 🟡 model|name / ⚠️ none. Only verified rows can become buy
candidates; ⚠️ rows are shown for discovery but never marked "buy".
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from arb_models import Product, normalize_jan

# Tokens too generic to prove identity on their own.
_STOPWORDS = {
    "nintendo", "switch", "sony", "playstation", "ps5", "セット", "本体",
    "新品", "未開封", "モデル", "the", "for", "版", "国内", "純正",
}

# Separators allowed BETWEEN two JAN digits (single, non-digit). Keeps the match
# local instead of spanning the whole page.
_JAN_SEP = r"[ \t　\-‐－]?"
_MODEL_MIN_LEN = 5
_MODEL_MIN_LETTERS = 2


@dataclass(frozen=True)
class VerifyResult:
    verified: bool
    method: str  # "jan" | "model" | "name" | "none"
    detail: str

    @property
    def badge(self) -> str:
        return {"jan": "✅", "model": "🟡", "name": "🟡"}.get(self.method, "⚠️")


def _alnum_upper(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", text).upper()


def jan_in_text(jan: str, text: str) -> bool:
    """True if the JAN appears locally, tolerant of single separators.

    Matches "4902370553024" and "4902370 553024" / "4902370-553024", but not a
    JAN embedded in a longer digit run and not digits scattered across the page.
    """
    jan = normalize_jan(jan)
    if not jan or not text:
        return False
    # Boundary-anchored: the JAN must not be embedded in a longer digit run, and
    # only a single separator is tolerated between digits (keeps the match local).
    pattern = r"(?<!\d)" + _JAN_SEP.join(re.escape(d) for d in jan) + r"(?!\d)"
    return re.search(pattern, text) is not None


def _model_in_text(model: str, text: str) -> bool:
    model = model.strip()
    if not model:
        return False
    if model in text:  # verbatim model number
        return True
    norm_model = _alnum_upper(model)
    letters = sum(ch.isalpha() for ch in norm_model)
    if len(norm_model) < _MODEL_MIN_LEN or letters < _MODEL_MIN_LETTERS:
        return False
    return norm_model in _alnum_upper(text)


def _name_tokens(name: str) -> list[str]:
    tokens = re.split(r"[\s　/／\-_,，、（）()]+", name)
    out: list[str] = []
    for tok in tokens:
        low = tok.strip().lower()
        if len(low) >= 3 and low not in _STOPWORDS and not low.isdigit():
            out.append(tok.strip())
    return out


def verify(product: Product, html: str, *, require: bool = True) -> VerifyResult:
    """Verify a fetched page matches ``product`` (best signal wins)."""
    text = html or ""
    if jan_in_text(product.jan, text):
        return VerifyResult(True, "jan", f"JAN {product.jan} がページ内に一致")

    if _model_in_text(product.model_no, text):
        return VerifyResult(True, "model", f"型番 {product.model_no} が一致（JANは未掲載）")

    hits = [tok for tok in _name_tokens(product.product_name) if tok in text]
    if len(hits) >= 2:
        return VerifyResult(True, "name", f"名称トークン一致: {', '.join(hits[:3])}")

    return VerifyResult(False, "none", "JAN/型番/名称が一致せず（誤マッチの可能性）")
