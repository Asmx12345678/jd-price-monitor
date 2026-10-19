import re
from typing import Dict, Optional, Tuple


MULTIPACK_RE = re.compile(
    r"(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>ml|毫升|l|升|g|克|kg|千克|斤)\s*[xX×*]\s*(?P<count>\d+)",
    re.IGNORECASE,
)
REVERSE_MULTIPACK_RE = re.compile(
    r"(?P<count>\d+)\s*(?:瓶|罐|袋|盒|包|桶|支|片)\s*[xX×*]?\s*(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>ml|毫升|l|升|g|克|kg|千克|斤)",
    re.IGNORECASE,
)
COUNT_MULTIPACK_RE = re.compile(
    r"(?P<per_count>\d+)\s*(?P<per_unit>抽|张|片|枚|粒|支)\s*[xX×*]\s*"
    r"(?P<pack_count>\d+)\s*(?P<pack_unit>包|袋|盒|卷|瓶|罐)",
    re.IGNORECASE,
)
SINGLE_SIZE_RE = re.compile(
    r"(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>ml|毫升|l|升|g|克|kg|千克|斤)",
    re.IGNORECASE,
)
COUNT_RE = re.compile(r"(?P<count>\d+)\s*(?P<count_unit>瓶|罐|袋|盒|包|桶|支|片|张|抽|卷)(?:装)?")


def _canonical_amount(size: float, unit: str, count: int) -> Tuple[float, str]:
    key = unit.lower()
    if key in {"ml", "毫升"}:
        return size * count / 1000.0, "L"
    if key in {"l", "升"}:
        return size * count, "L"
    if key in {"g", "克"}:
        return size * count / 1000.0, "kg"
    if key in {"kg", "千克"}:
        return size * count, "kg"
    if key == "斤":
        return size * count * 0.5, "kg"
    return size * count, "件"


def parse_pack(name: str) -> Dict[str, object]:
    count_multi = COUNT_MULTIPACK_RE.search(name)
    if count_multi:
        count = int(count_multi.group("per_count")) * int(count_multi.group("pack_count"))
        raw_unit = count_multi.group("per_unit")
        normalized = "张" if raw_unit in {"抽", "片", "张"} else raw_unit
        return {
            "count": count, "amount": float(count), "unit": normalized,
            "comparison_key": f"count:{normalized}", "display_unit": normalized,
            "label": count_multi.group(0),
        }

    match = MULTIPACK_RE.search(name) or REVERSE_MULTIPACK_RE.search(name)
    if match:
        size = float(match.group("size"))
        count = int(match.group("count"))
        amount, unit = _canonical_amount(size, match.group("unit"), count)
        key = "volume" if unit == "L" else "mass" if unit == "kg" else ""
        return {
            "count": count, "amount": amount, "unit": unit,
            "comparison_key": key, "display_unit": unit, "label": match.group(0),
        }

    size_match = SINGLE_SIZE_RE.search(name)
    count_match = COUNT_RE.search(name)
    if size_match:
        count = int(count_match.group("count")) if count_match else 1
        amount, unit = _canonical_amount(
            float(size_match.group("size")), size_match.group("unit"), count
        )
        key = "volume" if unit == "L" else "mass" if unit == "kg" else ""
        return {
            "count": count, "amount": amount, "unit": unit,
            "comparison_key": key, "display_unit": unit, "label": size_match.group(0),
        }

    if count_match:
        count = int(count_match.group("count"))
        raw_unit = count_match.group("count_unit")
        normalized = "张" if raw_unit in {"抽", "片", "张"} else raw_unit
        return {
            "count": count, "amount": float(count), "unit": normalized,
            "comparison_key": f"count:{normalized}", "display_unit": normalized,
            "label": count_match.group(0),
        }

    return {
        "count": 1, "amount": 1.0, "unit": "件", "comparison_key": "",
        "display_unit": "件", "label": "单件",
    }


def unit_price(price: float, pack: Dict[str, object]) -> Tuple[Optional[float], str]:
    amount = float(pack.get("amount") or 0)
    unit = str(pack.get("unit") or "件")
    if amount <= 0:
        return None, ""
    value = price / amount
    display_unit = str(pack.get("display_unit") or unit)
    suffix = {"L": "元/L", "kg": "元/kg", "件": "元/件"}.get(display_unit, f"元/{display_unit}")
    return round(value, 2), suffix

