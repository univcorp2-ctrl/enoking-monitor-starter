"""Data model for the expanded arbitrage engine.

This module defines the catalog used by the daily digest:

- ``Product``        one tradable item, keyed by 13-digit JAN.
- ``SellDest``       a sell destination (買取店 持込 or フリマ flip) for a JAN.
                     There can be MANY per JAN; the engine picks the best net.
- ``BuySource``      a supplier page (仕入れ先) for a JAN, with point-reward and
                     shipping so an effective (実質) cost can be computed.

Economics live as methods on the dataclasses so the rules stay close to the data:
points lower the effective purchase cost, while フリマ手数料 and 送料 lower the
net sale proceeds. The buy threshold is "any positive gap" (see arb_engine).

These configs are intentionally separate from the legacy ``products_sample.csv`` /
``supplier_urls.csv`` used by ``monitor.py`` so the other workflows
(daily-monitor, restock-watch) keep working unchanged.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"

KAITORI = "kaitori"
FRIMA = "frima"


def _to_int(value: str | None) -> int | None:
    text = str(value or "").strip().replace(",", "").replace("円", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_rate(value: str | None, default: float = 0.0) -> float:
    """Parse a fee/point rate robustly into a 0..1 fraction.

    Accepts '0.10', '10%', or a bare '10' (treated as percent). Anything > 1 is
    assumed to be a percent typo and divided by 100, so '10' and '10%' and '0.10'
    all yield 0.10. This prevents catastrophic mis-pricing from natural input.
    """
    text = str(value or "").strip()
    if not text:
        return default
    has_pct = "%" in text
    try:
        num = float(text.replace("%", ""))
    except ValueError:
        return default
    if has_pct or num > 1:
        return num / 100.0
    return num


def _to_bool(value: str | None, default: bool = True) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "on"}


def normalize_jan(value: str | None) -> str:
    """Keep digits only. Returns '' when no usable code is present."""
    return "".join(ch for ch in str(value or "") if ch.isdigit())


@dataclass(frozen=True)
class Product:
    jan: str
    product_name: str
    category: str = ""
    required_condition: str = "new"
    model_no: str = ""
    notes: str = ""


@dataclass(frozen=True)
class SellDest:
    jan: str
    channel: str  # KAITORI | FRIMA
    shop: str
    price_yen: int
    url: str = ""
    fee_rate: float = 0.0      # フリマ手数料 (e.g. 0.10 for メルカリ)
    shipping_yen: int = 0      # こちら負担の発送料 (フリマ時)
    condition: str = "new"
    enabled: bool = True
    manual_only: bool = False  # 確定価格でない（要相談/トップページ等）。候補根拠から除外
    notes: str = ""

    @property
    def net_yen(self) -> int:
        """Cash actually received after channel fees / shipping."""
        if self.channel == FRIMA:
            return round(self.price_yen * (1.0 - self.fee_rate)) - self.shipping_yen
        return self.price_yen  # 買取持込: full cash on hand, no fee/shipping

    @property
    def channel_label(self) -> str:
        return "フリマ" if self.channel == FRIMA else "買取"


@dataclass(frozen=True)
class BuySource:
    jan: str
    shop: str
    url: str
    list_price_yen: int | None = None
    point_rate: float = 0.0    # 実質値引きとして扱うポイント還元率 (e.g. 0.10)
    shipping_yen: int = 0      # こちら負担の受取送料 (送料込みなら0)
    parser_hint: str = "generic"
    condition: str = "new"
    enabled: bool = True
    notes: str = ""

    def point_value(self, price: int | None = None) -> int:
        base = self.list_price_yen if price is None else price
        if base is None:
            return 0
        return round(base * self.point_rate)

    def effective_cost(self, price: int | None = None) -> int | None:
        """実質仕入れコスト = 価格 − ポイント分 + 受取送料."""
        base = self.list_price_yen if price is None else price
        if base is None:
            return None
        return base - self.point_value(base) + self.shipping_yen


def load_products(path: Path = CONFIG_DIR / "products.csv") -> dict[str, Product]:
    products: dict[str, Product] = {}
    if not path.exists():
        return products
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            jan = normalize_jan(row.get("jan"))
            if not jan:
                continue
            products[jan] = Product(
                jan=jan,
                product_name=(row.get("product_name") or "").strip(),
                category=(row.get("category") or "").strip(),
                required_condition=(row.get("required_condition") or "new").strip(),
                model_no=(row.get("model_no") or "").strip(),
                notes=(row.get("notes") or "").strip(),
            )
    return products


def load_sell_destinations(
    path: Path = CONFIG_DIR / "sell_destinations.csv",
) -> dict[str, list[SellDest]]:
    dests: dict[str, list[SellDest]] = {}
    if not path.exists():
        return dests
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            jan = normalize_jan(row.get("jan"))
            price = _to_int(row.get("sell_price_yen"))
            if not jan or price is None:
                continue
            dest = SellDest(
                jan=jan,
                channel=(row.get("channel") or KAITORI).strip().lower(),
                shop=(row.get("shop") or "").strip(),
                price_yen=price,
                url=(row.get("url") or "").strip(),
                fee_rate=parse_rate(row.get("fee_rate")),
                shipping_yen=_to_int(row.get("shipping_yen")) or 0,
                condition=(row.get("condition") or "new").strip(),
                enabled=_to_bool(row.get("enabled"), True),
                manual_only=_to_bool(row.get("manual_only"), False),
                notes=(row.get("notes") or "").strip(),
            )
            dests.setdefault(jan, []).append(dest)
    return dests


def load_buy_sources(path: Path = CONFIG_DIR / "buy_sources.csv") -> list[BuySource]:
    sources: list[BuySource] = []
    if not path.exists():
        return sources
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            jan = normalize_jan(row.get("jan"))
            url = (row.get("url") or "").strip()
            if not jan or not url:
                continue
            sources.append(
                BuySource(
                    jan=jan,
                    shop=(row.get("shop") or "").strip(),
                    url=url,
                    list_price_yen=_to_int(row.get("list_price_yen")),
                    point_rate=parse_rate(row.get("point_rate")),
                    shipping_yen=_to_int(row.get("shipping_yen")) or 0,
                    parser_hint=(row.get("parser_hint") or "generic").strip(),
                    condition=(row.get("condition") or "new").strip(),
                    enabled=_to_bool(row.get("enabled"), True),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return sources


def best_sell_destination(
    jan: str,
    dests: dict[str, list[SellDest]],
    required_condition: str = "new",
) -> SellDest | None:
    """Highest net-proceeds sell destination for a JAN (買取/フリマ横断).

    Only confirmed, enabled destinations matching the required condition are
    eligible: ``manual_only`` (e.g. 要相談/トップページ) and disabled rows, and
    condition mismatches (中古/開封済み価格) are excluded so the gap is not
    inflated by a price that does not actually apply to a new unit.
    """
    options = [
        d
        for d in (dests.get(jan) or [])
        if d.enabled and not d.manual_only and d.condition == required_condition
    ]
    if not options:
        return None
    return max(options, key=lambda d: d.net_yen)
