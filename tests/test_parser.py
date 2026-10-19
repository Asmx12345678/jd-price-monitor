import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitor.parser import parse_pack, unit_price


class PackParserTests(unittest.TestCase):
    def test_drink_multipack(self):
        pack = parse_pack("可口可乐 330ml×5瓶")
        self.assertEqual(pack["count"], 5)
        self.assertAlmostEqual(pack["amount"], 1.65)
        self.assertEqual(pack["unit"], "L")
        price, label = unit_price(9.9, pack)
        self.assertEqual(price, 6.0)
        self.assertEqual(label, "元/L")

    def test_rice_weight(self):
        pack = parse_pack("五常大米 5kg")
        self.assertAlmostEqual(pack["amount"], 5.0)
        price, label = unit_price(39.9, pack)
        self.assertEqual(price, 7.98)
        self.assertEqual(label, "元/kg")

    def test_reverse_pack(self):
        pack = parse_pack("牛奶24盒×250ml")
        self.assertEqual(pack["count"], 24)
        self.assertAlmostEqual(pack["amount"], 6.0)

    def test_sheet_multipack_uses_total_sheet_count(self):
        pack = parse_pack("湿巾 80片*3包")
        self.assertEqual(pack["amount"], 240.0)
        self.assertEqual(pack["comparison_key"], "count:张")
        price, label = unit_price(24, pack)
        self.assertEqual(price, 0.1)
        self.assertEqual(label, "元/张")

    def test_different_count_units_are_not_comparable(self):
        bottles = parse_pack("可乐 5瓶装")
        bags = parse_pack("纸巾 5包装")
        self.assertNotEqual(bottles["comparison_key"], bags["comparison_key"])

    def test_single_item_has_no_comparison_key(self):
        self.assertEqual(parse_pack("普通拖把")["comparison_key"], "")


if __name__ == "__main__":
    unittest.main()

