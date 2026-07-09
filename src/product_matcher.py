"""Triple-check product matching for Enoking products and supplier offers."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Mapping

COLOR_WORDS = {
    "black": {"black", "ブラック", "黒", "グレー", "gray", "grey"},
    "white": {"white", "ホワイト", "白"},
    "red": {"red", "レッド", "赤", "マリオレッド"},
    "blue": {"blue", "ブルー", "青", "ディープブルー", "ネオンブルー"},
    "yellow": {"yellow", "イエロー", "黄"},
    "pink": {"pink", "ピンク", "コーラル"},
    "orange": {"orange", "オレンジ", "コズミックオレンジ"},
    "silver": {"silver", "シルバー", "銀"},
    "gold": {"gold", "ゴールド", "金"},
    "neon": {"ネオン", "neon", "ネオンブルー", "ネオンレッド"},
}

STOP_TOKENS = {
    "新品",
    "未使用",
    "本体",
    "セット",
    "モデル",
    "版",
    "the",
    "and",
    "for",
    "with",
    "apple",
    "nintendo",
    "switch",
    "playstation",
}


@dataclass(frozen=True)
class MatchCheck:
    check_name: str
    passed: bool
    evidence: str


@dataclass(frozen=True)
class MatchResult:
    jan_exact: bool
    title_model_match: bool
    variant_safe: bool
    score: int
    status: str
    checks: list[MatchCheck]
    warning: str

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["checks"] = [asdict(check) for check in self.checks]
        return data


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.casefold().replace("　", " ")
    value = re.sub(r"[\[\]（）()【】,，:：/・\\|_-]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def tokens(value: str | None) -> set[str]:
    text = normalize_text(value)
    raw_tokens = set(re.findall(r"[a-z0-9]+|[ぁ-んァ-ン一-龥ー]+", text))
    return {token for token in raw_tokens if len(token) >= 2 and token not in STOP_TOKENS}


def model_codes(value: str | None) -> set[str]:
    text = normalize_text(value).upper()
    return set(re.findall(r"\b[A-Z]{2,}[A-Z0-9-]{3,}\b|\b[A-Z]{1,5}-?\d{3,}[A-Z0-9-]*\b", text))


def capacities(value: str | None) -> set[str]:
    text = normalize_text(value).upper().replace(" ", "")
    return set(re.findall(r"\d+(?:GB|TB)", text))


def colors(value: str | None) -> set[str]:
    text = normalize_text(value)
    found: set[str] = set()
    for canonical, variants in COLOR_WORDS.items():
        if any(normalize_text(variant) in text for variant in variants):
            found.add(canonical)
    return found


def overlap_score(left: str | None, right: str | None) -> float:
    left_tokens = tokens(left)
    right_tokens = tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), 1)


def first_mapping_value(mapping: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return str(value)
    return ""


def triple_check_product(enoking_product: Mapping[str, object], supplier_offer: Mapping[str, object]) -> MatchResult:
    enoking_jan = first_mapping_value(enoking_product, "jan", "JAN").strip()
    supplier_jan = first_mapping_value(supplier_offer, "jan", "JAN", "supplier_jan").strip()
    enoking_name = first_mapping_value(enoking_product, "product_name", "name", "title")
    supplier_name = first_mapping_value(supplier_offer, "product_name", "supplier_product_name", "title", "itemName")
    supplier_url = first_mapping_value(supplier_offer, "url", "itemUrl")
    supplier_blob = " ".join([supplier_jan, supplier_name, supplier_url])

    jan_exact = bool(enoking_jan and (supplier_jan == enoking_jan or enoking_jan in supplier_blob))

    title_score = overlap_score(enoking_name, supplier_name)
    enoking_codes = model_codes(enoking_name)
    supplier_codes = model_codes(supplier_name)
    code_match = bool(enoking_codes and supplier_codes and enoking_codes <= supplier_codes)
    title_model_match = jan_exact or title_score >= 0.55 or code_match

    enoking_capacities = capacities(enoking_name)
    supplier_capacities = capacities(supplier_name)
    capacity_conflict = bool(enoking_capacities and supplier_capacities and enoking_capacities != supplier_capacities)

    enoking_colors = colors(enoking_name)
    supplier_colors = colors(supplier_name)
    color_conflict = bool(enoking_colors and supplier_colors and enoking_colors.isdisjoint(supplier_colors))
    variant_safe = not capacity_conflict and not color_conflict

    score = sum([3 if jan_exact else 0, 2 if title_model_match else 0, 2 if variant_safe else 0])
    if jan_exact and title_model_match and variant_safe:
        status = "VERIFIED_EXACT_TRIPLE_CHECKED"
        warning = "JAN・名称/型番・バリエーションの3点チェック済み"
    elif score >= 4 and variant_safe:
        status = "LIKELY_MATCH_NEEDS_MANUAL_JAN_CONFIRM"
        warning = "類似度は高いがJAN未確認。購入前にJANまたは型番を目視確認してください。"
    else:
        status = "REJECT_OR_MANUAL_REVIEW"
        warning = "JAN/名称/色/容量/型番のいずれかが不一致または未確認です。"

    checks = [
        MatchCheck("1_JAN_EXACT", jan_exact, f"enoking_jan={enoking_jan or 'N/A'} supplier_jan={supplier_jan or 'N/A'}"),
        MatchCheck(
            "2_TITLE_MODEL",
            title_model_match,
            f"title_overlap={title_score:.2f} enoking_codes={sorted(enoking_codes)} supplier_codes={sorted(supplier_codes)}",
        ),
        MatchCheck(
            "3_VARIANT_SAFE",
            variant_safe,
            (
                f"capacity_conflict={capacity_conflict} color_conflict={color_conflict} "
                f"enoking_capacities={sorted(enoking_capacities)} supplier_capacities={sorted(supplier_capacities)} "
                f"enoking_colors={sorted(enoking_colors)} supplier_colors={sorted(supplier_colors)}"
            ),
        ),
    ]
    return MatchResult(
        jan_exact=jan_exact,
        title_model_match=title_model_match,
        variant_safe=variant_safe,
        score=score,
        status=status,
        checks=checks,
        warning=warning,
    )
