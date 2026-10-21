"""Run with pytest, or with stdlib unittest even without third-party packages."""
import unittest
from dataclasses import dataclass
from decimal import Decimal, getcontext

from app.services.accounting import replay

getcontext().prec = 120
D = Decimal


@dataclass
class Entry:
    kind: str
    quantity: Decimal = D("0")
    price: Decimal = D("0")
    cash_delta: Decimal = D("0")
    fx_rate: Decimal = D("1")
    symbol: str = "GOLD"


class AccountingTests(unittest.TestCase):
    def test_golden_buy_then_fifo_sell(self):
        rows = [Entry("DEPOSIT", cash_delta=D("10000")), Entry("BUY", D("10"), D("100"), D("-1000")), Entry("BUY", D("10"), D("120"), D("-1200"))]
        book = replay(rows)
        position = book.position("GOLD", D("130"))
        self.assertEqual(position["average_cost"], D("110"))
        self.assertEqual(position["unrealized"], D("400"))
        self.assertEqual(position["return_pct"].quantize(D("0.01")), D("18.18"))
        rows.append(Entry("SELL", D("15"), D("130"), D("1950")))
        book = replay(rows)
        position = book.position("GOLD", D("130"))
        self.assertEqual(book.realized, D("350"))
        self.assertEqual(position["quantity"], D("5"))
        self.assertEqual(position["cost"], D("600"))
        self.assertEqual(position["value"], D("650"))
        self.assertEqual(position["unrealized"], D("50"))
        self.assertEqual(book.realized + position["unrealized"], D("400"))
        self.assertEqual(book.cash, D("9750"))

    def test_fractional_shares_are_decimal_exact(self):
        book = replay([Entry("BUY", D("0.1"), D("0.2"), D("-0.02")), Entry("BUY", D("0.2"), D("0.2"), D("-0.04"))])
        self.assertEqual(book.position("GOLD", D("0.3"))["unrealized"], D("0.03"))
        self.assertEqual(book.cash, D("-0.06"))

    def test_fx_realized_and_unrealized_use_acquisition_fx(self):
        book = replay([Entry("BUY", D("2"), D("100"), D("-16000"), D("80")), Entry("SELL", D("1"), D("110"), D("9240"), D("84"))])
        self.assertEqual(book.realized, D("1240"))
        self.assertEqual(book.realized_native["GOLD"], D("10"))
        self.assertEqual(book.position("GOLD", D("110"), D("84"))["unrealized_inr"], D("1240"))

    def test_multiple_sell_orders_continue_fifo(self):
        rows = [Entry("BUY", D("10"), D("100")), Entry("BUY", D("10"), D("120")), Entry("SELL", D("5"), D("130")), Entry("SELL", D("10"), D("130"))]
        book = replay(rows)
        self.assertEqual(book.realized, D("350"))
        self.assertEqual(book.position("GOLD", D("130"))["cost"], D("600"))

    def test_full_exit_has_zero_position(self):
        book = replay([Entry("BUY", D("2"), D("100")), Entry("SELL", D("2"), D("120"))])
        self.assertEqual(book.position("GOLD", D("120"))["quantity"], 0)
        self.assertEqual(book.realized, D("40"))

    def test_corrupt_oversell_is_rejected(self):
        with self.assertRaises(ValueError):
            replay([Entry("SELL", D("1"), D("100"))])

    def test_import_does_not_spend_virtual_cash(self):
        book = replay([Entry("IMPORT", D("5"), D("120"))])
        self.assertEqual(book.cash, 0)
        self.assertEqual(book.imported_cost, D("600"))
        self.assertEqual(book.position("GOLD", D("130"))["unrealized"], D("50"))

    def test_independent_symbols(self):
        rows = [Entry("BUY", D("10"), D("100")), Entry("BUY", D("1"), D("200"), symbol="OTHER"), Entry("SELL", D("1"), D("210"), symbol="OTHER")]
        book = replay(rows)
        self.assertEqual(book.realized, D("10"))
        self.assertEqual(book.position("GOLD", D("100"))["quantity"], D("10"))

    def test_large_values_preserve_small_fraction(self):
        book = replay([Entry("BUY", D("99999999.12345678"), D("123456.12345678"))])
        p = book.position("GOLD", D("123456.12345679"))
        self.assertEqual(p["unrealized"], D("0.9999999912345678"))


if __name__ == "__main__":
    unittest.main()
