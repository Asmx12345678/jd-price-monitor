import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from monitor.scanner import Scanner
from monitor.storage import Storage


class ScannerPriceModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temp.name) / "prices.db")
        settings = SimpleNamespace(
            live_ready=False, discovery_pages=1, drop_threshold_percent=30,
            app_key="", app_secret="",
        )
        self.scanner = Scanner(settings, self.storage)
        self.scanner._refresh_activities = lambda: None

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def item(price, base=100):
        return {
            "sku_id": "1", "name": "饮料 500ml×2瓶", "category": "食品",
            "source": "测试", "image_url": "", "product_url": "https://item.jd.com/1.html",
            "coupon_url": "", "current_price": price, "base_price": base,
            "offer_text": "公开活动", "price_type": "promotion_estimate",
        }

    def scan_item(self, item):
        self.scanner._source_items = lambda: [dict(item)]
        return self.scanner.scan()

    def test_first_observation_is_public_offer_not_history(self):
        self.scan_item(self.item(40))
        deal = self.storage.deals()[0]
        self.assertEqual(deal["deal_kind"], "new_public_offer")
        self.assertEqual(deal["historical_drop_percent"], 0)
        self.assertEqual(deal["public_discount_percent"], 60)

    def test_extreme_history_drop_requires_two_confirmations(self):
        self.scan_item(self.item(100))
        self.assertEqual(self.storage.deals(), [])
        self.scan_item(self.item(40, 40))
        self.assertEqual(self.storage.deals(), [])
        self.scan_item(self.item(40, 40))
        deal = self.storage.deals()[0]
        self.assertEqual(deal["deal_kind"], "historical_drop")
        self.assertEqual(deal["confirmation_count"], 2)
        self.assertEqual(deal["historical_drop_percent"], 60)


if __name__ == "__main__":
    unittest.main()
