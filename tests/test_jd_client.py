import unittest

from monitor.jd_client import JDClient, _valid_jd_product_url


class JDClientNormalizationTests(unittest.TestCase):
    def test_spuid_uses_api_material_url_instead_of_fake_sku_url(self):
        payload = {
            "response": {
                "queryResult": {
                    "data": [{
                        "spuid": 10034843591732,
                        "itemId": "opaque-item-id",
                        "skuName": "五常大米 5kg",
                        "materialUrl": "jingfen.jd.com/detail/opaque-item-id.html",
                        "priceInfo": {"price": 69.9, "lowestCouponPrice": 26.9},
                        "categoryInfo": {"cid1Name": "粮油调味"},
                    }]
                }
            }
        }

        items = JDClient("key", "secret")._normalize(payload, "历史低价", "京粉精选")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["sku_id"], "10034843591732")
        self.assertEqual(
            items[0]["product_url"],
            "https://jingfen.jd.com/detail/opaque-item-id.html",
        )

    def test_rejects_non_jd_product_url(self):
        self.assertFalse(_valid_jd_product_url("https://example.com/item/1"))
        self.assertTrue(_valid_jd_product_url("https://item.jd.com/1.html"))

    def test_collects_public_promotion_labels(self):
        payload = {"response": {"data": [{
            "spuid": 1, "itemId": "opaque", "skuName": "饮料 500ml×2瓶",
            "materialUrl": "jingfen.jd.com/detail/opaque.html",
            "priceInfo": {"price": 20},
            "purchasePriceInfo": {
                "purchasePrice": 10, "purchaseNum": 2,
                "promotionLabelInfoList": [{"promotionLabel": "满2件5折"}],
                "couponList": [{"quota": 20, "discount": 5}],
            },
            "skuTagList": [{"name": "plus"}, {"name": "自营"}],
        }]}}
        item = JDClient("key", "secret")._normalize(payload, "京东超市", "京粉精选")[0]
        self.assertIn("满2件5折", item["offer_text"])
        self.assertIn("满20减5券", item["offer_text"])
        self.assertIn("需买2件", item["offer_text"])
        self.assertIn("PLUS标识", item["offer_text"])


if __name__ == "__main__":
    unittest.main()
