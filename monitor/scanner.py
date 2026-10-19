from datetime import datetime, timezone
import json
import threading
from typing import Dict, List

from .jd_client import JDClient, fetch_live
from .parser import parse_pack, unit_price
from .storage import Storage


DEMO_ITEMS = [
    {
        "sku_id": "100000000001", "name": "可口可乐 碳酸饮料 330ml×5瓶", "category": "食品酒水",
        "source": "历史低价", "image_url": "", "product_url": "https://item.jd.com/100000000001.html",
        "coupon_url": "https://coupon.jd.com/", "current_price": 9.9, "base_price": 15.9,
        "offer_text": "领券后9.9元 · 5瓶装",
    },
    {
        "sku_id": "100000000002", "name": "五常大米 5kg 东北粳米", "category": "米面粮油",
        "source": "京东超市", "image_url": "", "product_url": "https://item.jd.com/100000000002.html",
        "coupon_url": "", "current_price": 39.9, "base_price": 55.9,
        "offer_text": "PLUS专享价",
    },
    {
        "sku_id": "100000000003", "name": "原生木浆抽纸 100抽×20包", "category": "家庭清洁",
        "source": "实时热销榜", "image_url": "", "product_url": "https://item.jd.com/100000000003.html",
        "coupon_url": "", "current_price": 29.8, "base_price": 39.9,
        "offer_text": "满折 · 京东物流",
    },
    {
        "sku_id": "100000000004", "name": "纯牛奶 250ml×24盒", "category": "食品酒水",
        "source": "秒杀", "image_url": "", "product_url": "https://item.jd.com/100000000004.html",
        "coupon_url": "", "current_price": 44.9, "base_price": 59.9,
        "offer_text": "限时秒杀",
    },
]


class Scanner:
    def __init__(self, settings, storage: Storage):
        self.settings = settings
        self.storage = storage
        self.lock = threading.Lock()
        self.running = False
        self.last_error = ""
        if self.storage.get_state("unit_key_migration_v1") != "done":
            removed = self.storage.deactivate_unit_price_deals()
            self.storage.set_state("unit_key_migration_v1", "done")
            self.storage.set_state("unit_key_migration_removed", str(removed))
        if self.storage.get_state("deal_model_v2") != "done":
            removed = self.storage.deactivate_legacy_deals()
            self.storage.set_state("deal_model_v2", "done")
            self.storage.set_state("deal_model_v2_removed", str(removed))

    @staticmethod
    def _confidence(item: Dict[str, object]) -> str:
        offer = str(item.get("offer_text") or "").lower()
        if any(word in offer for word in ("plus", "需买", "会员", "新人", "定向")):
            return "conditional"
        if item.get("price_type") == "coupon_estimate":
            return "medium" if item.get("coupon_url") else "conditional"
        return "high"

    def _source_items(self) -> List[Dict[str, object]]:
        if self.settings.live_ready:
            saved_page = self.storage.get_state("discovery_page")
            page = max(1, min(self.settings.discovery_pages, int(saved_page or "1")))
            items, errors = fetch_live(JDClient(self.settings.app_key, self.settings.app_secret), page)
            self.storage.set_state("source_warnings", "；".join(errors[:5]))
            return items
        self.storage.set_state("source_warnings", "")
        return [dict(item) for item in DEMO_ITEMS]

    def _refresh_activities(self) -> None:
        if not self.settings.live_ready:
            return
        try:
            activities = JDClient(self.settings.app_key, self.settings.app_secret).activities()
            self.storage.set_state("activities", json.dumps(activities[:20], ensure_ascii=False))
            self.storage.set_state("activity_error", "")
        except Exception as exc:
            self.storage.set_state("activity_error", str(exc))

    def scan(self) -> Dict[str, object]:
        if not self.lock.acquire(blocking=False):
            return {"ok": False, "message": "扫描正在进行中"}
        self.running = True
        try:
            saved_page = self.storage.get_state("discovery_page")
            discovery_page = max(1, min(self.settings.discovery_pages, int(saved_page or "1")))
            tracked_before = self.storage.tracked_count()
            items = self._source_items()
            self._refresh_activities()
            deal_count = 0
            saved_threshold = self.storage.get_state("drop_threshold_percent")
            threshold = float(saved_threshold) if saved_threshold is not None else self.settings.drop_threshold_percent
            now = datetime.now(timezone.utc).isoformat()
            for item in items:
                sku_id = str(item["sku_id"])
                previous_snapshot = self.storage.previous_snapshot(sku_id)
                previous = float(previous_snapshot["current_price"]) if previous_snapshot else None
                current = float(item["current_price"])
                base = float(item.get("base_price") or current)
                # Prefer JD's structured wareQD specification. Falling back to
                # the title avoids combining two conflicting pack descriptions.
                spec_text = str(item.get("spec_text") or "").strip()
                pack = parse_pack(spec_text if spec_text else str(item["name"]))
                price_per_unit, unit_label = unit_price(current, pack)
                unit_key = str(pack.get("comparison_key") or "")
                item.update({
                    "unit_price": price_per_unit,
                    "unit_label": unit_label,
                    "unit_key": unit_key,
                    "pack_label": str(pack.get("label") or "单件"),
                    "captured_at": now,
                })
                previous_unit = (
                    float(previous_snapshot["unit_price"])
                    if previous_snapshot and previous_snapshot.get("unit_price") is not None
                    and unit_key and previous_snapshot.get("unit_key") == unit_key else None
                )
                public_drop = round((base - current) / base * 100, 1) if base > current else 0.0
                total_drop = round((previous - current) / previous * 100, 1) if previous and previous > current else 0.0
                unit_drop = round((previous_unit - price_per_unit) / previous_unit * 100, 1) if (
                    previous_unit and price_per_unit is not None and previous_unit > price_per_unit
                ) else 0.0
                self.storage.add_snapshot(item)
                comparison_kind = "unit_price" if unit_drop > total_drop else "total_price"
                historical_drop = max(total_drop, unit_drop)
                reference = previous_unit if comparison_kind == "unit_price" else previous
                deal_kind = "unit_drop" if comparison_kind == "unit_price" else "historical_drop"
                confirmations = 1

                # An extreme historical change is shown only after the same low
                # price is observed twice. A pending candidate survives the
                # immediately preceding equal-price snapshot.
                pending = self.storage.candidate(sku_id)
                if historical_drop >= 50:
                    confirmations = self.storage.confirm_candidate(
                        sku_id, comparison_kind, float(reference), current,
                        historical_drop, previous_unit,
                    )
                    if confirmations < 2:
                        self.storage.deactivate(sku_id)
                        continue
                elif pending and abs(float(pending["current_price"]) - current) < 0.01:
                    historical_drop = float(pending["drop_percent"])
                    comparison_kind = str(pending["comparison_kind"])
                    reference = float(pending["reference_price"])
                    previous_unit = pending.get("reference_unit_price")
                    deal_kind = "unit_drop" if comparison_kind == "unit_price" else "historical_drop"
                    confirmations = self.storage.confirm_candidate(
                        sku_id, comparison_kind, reference, current,
                        historical_drop, previous_unit,
                    )

                if historical_drop >= threshold and confirmations >= (2 if historical_drop >= 50 else 1):
                    self.storage.clear_candidate(sku_id)
                    if deal_kind == "unit_drop":
                        old_pack = str(previous_snapshot.get("pack_label") or "原包装")
                        reason = (
                            f"真实历史单位价下降{historical_drop}%：{old_pack} → {item['pack_label']}；"
                            f"当前 {price_per_unit} {unit_label}"
                        )
                    else:
                        label = str(item.get("offer_text") or "")
                        reason = f"真实历史总价下降{historical_drop}%" + (f" · {label}" if label else "")
                    self.storage.upsert_deal(
                        sku_id, float(reference), current, historical_drop, reason,
                        comparison_kind, previous_unit, deal_kind, public_drop,
                        historical_drop, self._confidence(item), confirmations,
                    )
                    deal_count += 1
                elif (
                    (existing_deal := self.storage.active_deal(sku_id))
                    and existing_deal.get("deal_kind") in {"historical_drop", "unit_drop"}
                    and abs(float(existing_deal["current_price"]) - current) < 0.01
                ):
                    # Preserve a newly detected historical event instead of
                    # relabelling it on the next equal-price observation.
                    deal_count += 1
                elif public_drop >= threshold:
                    self.storage.clear_candidate(sku_id)
                    label = str(item.get("offer_text") or "公开优惠")
                    reason = f"首次/当前公开优惠比参考价低{public_drop}% · {label}"
                    self.storage.upsert_deal(
                        sku_id, base, current, public_drop, reason, "public_offer",
                        None, "new_public_offer", public_drop, 0,
                        self._confidence(item), 1,
                    )
                    deal_count += 1
                else:
                    self.storage.clear_candidate(sku_id)
                    self.storage.deactivate(sku_id)
            # Pages rotate across scans, so deals absent from this single page
            # must not be removed immediately. They expire if unseen for a day.
            self.storage.deactivate_stale(24)
            next_page = discovery_page % self.settings.discovery_pages + 1
            tracked_after = self.storage.tracked_count()
            self.storage.set_state("discovery_page", str(next_page))
            self.storage.set_state("last_scan_count", str(len(items)))
            self.storage.set_state("last_scan_page", str(discovery_page))
            self.storage.set_state("last_new_count", str(max(0, tracked_after - tracked_before)))
            self.last_error = ""
            self.storage.set_state("last_scan", now)
            self.storage.set_state("last_error", "")
            return {
                "ok": True,
                "scanned": len(items),
                "deals": deal_count,
                "page": discovery_page,
                "next_page": next_page,
                "tracked": tracked_after,
                "new": max(0, tracked_after - tracked_before),
            }
        except Exception as exc:
            self.last_error = str(exc)
            self.storage.set_state("last_error", self.last_error)
            return {"ok": False, "message": self.last_error}
        finally:
            self.running = False
            self.lock.release()

