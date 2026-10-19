import hashlib
import json
from datetime import datetime
from typing import Dict, List
from urllib import parse, request
from zoneinfo import ZoneInfo


API_URL = "https://api.jd.com/routerjson"


def _deep_values(value):
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                yield from _deep_values(json.loads(stripped))
            except json.JSONDecodeError:
                pass
        return
    if isinstance(value, dict):
        has_identifier = any(value.get(k) not in (None, "") for k in ("skuId", "spuid", "itemId"))
        if has_identifier and "skuName" in value and any(
            k in value for k in ("priceInfo", "purchasePriceInfo", "wlprice", "price")
        ):
            yield value
        for child in value.values():
            yield from _deep_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _deep_values(child)


def _first_number(*values):
    for value in values:
        try:
            if value is not None and value != "":
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _url(value: str, sku_id: str) -> str:
    if not value:
        return f"https://item.jd.com/{sku_id}.html"
    if value.startswith("//"):
        return "https:" + value
    if not value.startswith(("http://", "https://")):
        return "https://" + value.lstrip("/")
    return value


def _valid_jd_product_url(value: str) -> bool:
    try:
        parsed = parse.urlparse(value)
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and (host == "jd.com" or host.endswith(".jd.com"))
    except ValueError:
        return False


class JDClient:
    def __init__(self, app_key: str, app_secret: str, timeout: int = 20):
        self.app_key = app_key
        self.app_secret = app_secret
        self.timeout = timeout

    def _sign(self, params: Dict[str, str]) -> str:
        joined = "".join(f"{key}{params[key]}" for key in sorted(params))
        raw = f"{self.app_secret}{joined}{self.app_secret}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()

    def call(self, method: str, business: Dict[str, object]) -> Dict[str, object]:
        params = {
            "360buy_param_json": json.dumps(business, ensure_ascii=False, separators=(",", ":")),
            "app_key": self.app_key,
            "format": "json",
            "method": method,
            "sign_method": "md5",
            "timestamp": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S"),
            "v": "1.0",
        }
        params["sign"] = self._sign(params)
        req = request.Request(
            API_URL,
            data=parse.urlencode(params).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def rank(self, rank_id: int, category: str, sort_type: int = 1) -> List[Dict[str, object]]:
        payload = self.call(
            "jd.union.open.goods.rank.query",
            {"rankGoodsReq": {"rankId": rank_id, "sortType": sort_type, "pageIndex": 1, "pageSize": 20}},
        )
        return self._normalize(payload, category, "实时热销榜")

    def jingfen(self, elite_id: int, category: str, page_index: int = 1) -> List[Dict[str, object]]:
        payload = self.call(
            "jd.union.open.goods.jingfen.query",
            {"goodsReq": {"eliteId": elite_id, "pageIndex": page_index, "pageSize": 50}},
        )
        return self._normalize(payload, category, "京粉精选")

    def _normalize(self, payload: Dict[str, object], category: str, source: str) -> List[Dict[str, object]]:
        items = []
        seen = set()
        for raw in _deep_values(payload):
            # Newer Union responses expose the real JD product id as ``spuid``
            # while older responses use ``skuId``. ``itemId`` can be an opaque
            # Jingfen id, so only use it as a last resort.
            sku_id = str(raw.get("skuId") or raw.get("spuid") or raw.get("itemId") or "").strip()
            if not sku_id or sku_id in seen:
                continue
            seen.add(sku_id)
            price_info = raw.get("priceInfo") or {}
            purchase = raw.get("purchasePriceInfo") or {}
            coupons = purchase.get("couponList") or (raw.get("couponInfo") or {}).get("couponList") or []
            coupon = coupons[0] if coupons and isinstance(coupons[0], dict) else {}
            current = _first_number(
                purchase.get("purchasePrice"), price_info.get("lowestCouponPrice"),
                price_info.get("lowestPrice"), price_info.get("price"), raw.get("wlprice"), raw.get("price"),
            )
            base = _first_number(raw.get("wlprice"), price_info.get("price"), current)
            if current is None:
                continue
            image_info = raw.get("imageInfo") or {}
            white_image = image_info.get("whiteImage") or ""
            if isinstance(white_image, dict):
                white_image = white_image.get("url") or ""
            image_list = image_info.get("imageList") or []
            first_image = image_list[0].get("url", "") if image_list and isinstance(image_list[0], dict) else ""
            promotion_labels = purchase.get("promotionLabelInfoList") or []
            label_names = [
                str(x.get("labelName") or x.get("promotionLabel") or x.get("label"))
                for x in promotion_labels
                if isinstance(x, dict) and (x.get("labelName") or x.get("promotionLabel") or x.get("label"))
            ]
            for coupon_item in coupons:
                if isinstance(coupon_item, dict) and coupon_item.get("discount"):
                    label_names.append(f"满{coupon_item.get('quota', 0)}减{coupon_item['discount']}券")
            purchase_num = int(_first_number(purchase.get("purchaseNum"), 1) or 1)
            if purchase_num > 1:
                label_names.append(f"需买{purchase_num}件")
            for tag in raw.get("skuTagList") or []:
                if isinstance(tag, dict) and tag.get("name"):
                    tag_name = str(tag["name"])
                    if tag_name.lower() in {"plus", "自营"}:
                        label_names.append("PLUS标识" if tag_name.lower() == "plus" else "京东自营")
            category_info = raw.get("categoryInfo") or {}
            actual_category = str(category_info.get("cid1Name") or category)
            actual_source = category if source == "京粉精选" else source
            product_url = _url(str(raw.get("materialUrl") or ""), sku_id)
            if not _valid_jd_product_url(product_url):
                continue
            # Preserve order while removing duplicate promotion labels.
            label_names = list(dict.fromkeys(label_names))
            coupon_discount = _first_number(coupon.get("discount"))
            coupon_quota = _first_number(coupon.get("quota"))
            if coupon_discount and coupon.get("link"):
                price_type = "coupon_estimate"
            elif base is not None and current < base:
                price_type = "promotion_estimate"
            else:
                price_type = "listed"
            items.append({
                "sku_id": sku_id,
                "source_item_id": str(raw.get("itemId") or ""),
                "name": str(raw.get("skuName") or f"京东商品 {sku_id}"),
                "category": actual_category,
                "source": actual_source,
                "image_url": _url(str(raw.get("imageUrl") or white_image or first_image), sku_id) if (raw.get("imageUrl") or white_image or first_image) else "",
                # New Union responses may only expose ``spuid``. A spuid is a
                # same-product group id and is not guaranteed to be a valid
                # item.jd.com SKU. The API-provided landing page is canonical
                # and resolves to the currently purchasable item.
                "product_url": product_url,
                "coupon_url": _url(str(coupon.get("link") or ""), sku_id) if coupon.get("link") else "",
                "promotion_url": _url(str((raw.get("promotionInfo") or {}).get("clickURL") or ""), sku_id)
                if (raw.get("promotionInfo") or {}).get("clickURL") else "",
                "current_price": current,
                "base_price": base,
                "price_type": price_type,
                "coupon_discount": coupon_discount,
                "coupon_quota": coupon_quota,
                "offer_text": " · ".join(label_names) or source,
            })
        return items

    def material(self, elite_id: int, category: str, page_index: int = 1) -> List[Dict[str, object]]:
        payload = self.call(
            "jd.union.open.goods.material.query",
            {"goodsReq": {"eliteId": elite_id, "pageIndex": page_index, "pageSize": 50}},
        )
        return self._normalize(payload, category, "京东商品素材")

    def activities(self, page_index: int = 1) -> List[Dict[str, object]]:
        payload = self.call(
            "jd.union.open.activity.query",
            {"activityReq": {"pageIndex": page_index, "pageSize": 20}},
        )
        result = []
        for value in _walk(payload):
            if not isinstance(value, dict) or not value.get("title") or not value.get("id"):
                continue
            result.append({
                "id": str(value["id"]), "title": str(value["title"]),
                "advantage": str(value.get("advantage") or ""),
                "url": str(value.get("urlM") or value.get("urlPC") or ""),
                "start_time": value.get("startTime"), "end_time": value.get("endTime"),
                "status": value.get("actStatus"),
            })
        return result

    def bigfields(self, item_ids: List[str]) -> Dict[str, str]:
        if not item_ids:
            return {}
        payload = self.call(
            "jd.union.open.goods.bigfield.query",
            {"goodsReq": {"sceneId": 1, "itemIds": item_ids[:10]}},
        )
        result = {}
        for value in _walk(payload):
            if not isinstance(value, dict) or not value.get("itemId"):
                continue
            base = value.get("baseBigFieldInfo") or {}
            specification = str(base.get("wareQD") or "").strip()
            if specification:
                result[str(value["itemId"])] = specification
        return result

    def promotion_link(self, material_id: str, site_id: str, position_id: str = "") -> str:
        request_data = {"materialId": material_id, "siteId": site_id}
        if position_id:
            request_data["positionId"] = position_id
        payload = self.call(
            "jd.union.open.promotion.common.get",
            {"promotionCodeReq": request_data},
        )
        for value in _walk(payload):
            if isinstance(value, dict):
                url = value.get("clickURL") or value.get("shortURL")
                if url:
                    return str(url)
        return ""


def _walk(value):
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                yield from _walk(json.loads(stripped))
            except json.JSONDecodeError:
                pass
        return
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def fetch_live(client: JDClient, page_index: int = 1) -> tuple[List[Dict[str, object]], List[str]]:
    # Keep the radar focused on things commonly sold by a supermarket rather
    # than letting general JD deal feeds fill it with sofas, computers, etc.
    excluded_categories = {
        "工业品", "电脑、办公", "家装建材", "箱包皮具", "家具", "数码",
        "手机通讯", "汽车用品", "农资园艺", "钟表", "珠宝首饰", "鞋靴",
        "服饰内衣", "图书", "家用电器", "厨房卫浴", "床上用品",
        "钟表眼镜", "玩具乐器", "运动户外", "灯饰照明",
        "本地生活/旅游出行", "文娱",
    }
    channels = [
        (1, "好券商品"),
        (10, "9.9专区"),
        (22, "实时热销"),
        (25, "京东超市"),
        (26, "母婴玩具"),
        (27, "家具日用"),
        (28, "美妆穿搭"),
        (33, "京东秒杀"),
        (41, "自营热卖"),
        (108, "秒杀进行中"),
        (110, "京东自营"),
        (112, "京东爆品"),
        (153, "历史低价"),
    ]
    result = []
    errors = []
    for elite_id, label in channels:
        try:
            result.extend(client.jingfen(elite_id, label, page_index))
        except Exception as exc:
            errors.append(f"频道{elite_id}: {exc}")
    for elite_id, label in ((25, "京东超市素材"), (153, "历史低价素材")):
        try:
            result.extend(client.material(elite_id, label, page_index))
        except Exception as exc:
            errors.append(f"素材频道{elite_id}: {exc}")
    if not result and errors:
        raise RuntimeError("；".join(errors[:3]))
    deduped = {}
    for item in result:
        if item.get("category") in excluded_categories:
            continue
        prior = deduped.get(item["sku_id"])
        if (
            not prior or item["current_price"] < prior["current_price"]
            or (item["current_price"] == prior["current_price"] and item.get("source") == "京东商品素材")
        ):
            deduped[item["sku_id"]] = item
    items = list(deduped.values())
    # bigfield scene 1 accepts opaque material itemIds (not ordinary SKU ids).
    # Enrich a bounded set each round so package-size changes can be compared
    # without making the scan unreasonably slow.
    spec_candidates = sorted(items, key=lambda x: x.get("source") != "京东商品素材")
    opaque_ids = [str(x.get("source_item_id") or "") for x in spec_candidates if x.get("source_item_id")]
    specs = {}
    for offset in range(0, min(len(opaque_ids), 100), 10):
        try:
            specs.update(client.bigfields(opaque_ids[offset:offset + 10]))
        except Exception as exc:
            errors.append(f"商品规格: {exc}")
            break
    for item in items:
        item["spec_text"] = specs.get(str(item.get("source_item_id") or ""), "")
    return items, errors

