"""JAN double-check: confirm a fetched supplier page really is the product.

The user requirement is explicit: before a listing is reported as a buy
candidate, we must verify the supplier page and the sell destination refer to
the SAME product, with no mix-up. We do this conservatively with two signals:

1. JAN match  - the 13-digit JAN appears verbatim in the page text/HTML
                (also tolerant of the JAN split by non-digits like 4902370 553024).
2. Model/name - if the JAN is not printed on the page (common on 量販店 pages),
                fall back to the model number, else a distinctive name token.

The result is a small struct so the digest can show ✅ (jan), 🟡 (model/name
only) or ⚠️ (unverified). Only ✅/🟡 listings are eligible to be buy candidates;
⚠️ ones are shown for discovery but never marked "buy".
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


@dataclass(frozen=True)
class VerifyResult:
    verified: bool
    method: str  # "jan" | "model" | "name" | "none"
    detail: str

    @property
    def badge(self) -> str:
        return {"jan": "✅", "model": "🟡", "name": "🟡"}.get(self.method, "⚠️")


def _digits_only(text: str) -> str:
    return re.sub(r"\D", "", text)


def jan_in_text(jan: str, text: str) -> bool:
    """True if the JAN appears, even when split by spaces/hyphens in the HTML."""
    jan = normalize_jan(jan)
    if not jan or not text:
        return False
    if jan in text:
        return True
    # Tolerate separators by scanning a digits-only projection of a window.
    # (Cheap and avoids huge-page blowups: only check the digit stream.)
    return jan in _digits_only(text)


def _name_tokens(name: str) -> list[str]:
    tokens = re.split(r"[\s　/／\-_,，、（）()]+", name)
    out: list[str] = []
    for tok in tokens:
        low = tok.strip().lower()
        if len(low) >= 3 and low not in _STOPWORDS and not low.isdigit():
            out.append(tok.strip())
    return out


def verify(product: Product, html: str, *, require: bool = True) -> VerifyResult:
    """Verify a fetched page matches ``product``.

    ``require`` False is used for search/discovery pages where a strict match is
    not expected; it still reports the best signal found.
    """
    text = html or ""
    if jan_in_text(product.jan, text):
        return VerifyResult(True, "jan", f"JAN {product.jan} がページ内に一致")

    model = product.model_no.strip()
    if model and (model in text or _digits_only(model) and _digits_only(model) in _digits_only(text)):
        return VerifyResult(True, "model", f"型番 {model} が一致（JANは未掲載）")

    # Require at least two distinctive name tokens to call it a name match.
    hits = [tok for tok in _name_tokens(product.product_name) if tok in text]
    if len(hits) >= 2:
        return VerifyResult(True, "name", f"名称トークン一致: {', '.join(hits[:3])}")

    return VerifyResult(False, "none", "JAN/型番/名称が一致せず（誤マッチの可能性）")
