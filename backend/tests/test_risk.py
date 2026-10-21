import unittest
from datetime import date
from decimal import Decimal

from app.services.risk import risk_metrics, xirr


class RiskTests(unittest.TestCase):
    def test_xirr_one_year_ten_percent(self):
        result = xirr([(date(2025,1,1), Decimal('-1000')), (date(2026,1,1), Decimal('1100'))])
        self.assertAlmostEqual(result, Decimal('0.1'), places=8)

    def test_xirr_same_day_is_unavailable(self):
        self.assertIsNone(xirr([(date(2026,1,1),Decimal('-100')), (date(2026,1,1),Decimal('110'))]))

    def test_max_drawdown(self):
        values = list(map(Decimal,['100','120','90','110']))
        self.assertEqual(Decimal(risk_metrics(values)['max_drawdown_pct']), Decimal('-25'))

    def test_constant_series_has_zero_risk(self):
        result = risk_metrics([Decimal(100)]*10)
        self.assertEqual(result['volatility_pct'],0)
        self.assertEqual(Decimal(result['max_drawdown_pct']),0)

    def test_small_samples_report_unavailable(self):
        self.assertIsNone(risk_metrics([Decimal(100)])['volatility_pct'])

    def test_no_xirr_for_cashflows_with_no_sign_change(self):
        self.assertIsNone(xirr([(date(2025,1,1),Decimal(100)), (date(2026,1,1),Decimal(120))]))


if __name__ == '__main__':
    unittest.main()
