import unittest
from datetime import date
from unittest.mock import Mock, patch

from app.services.adapters.yahoo import YahooAdapter


class YahooAdapterTest(unittest.TestCase):
    @patch("app.services.adapters.yahoo.httpx.get")
    def test_missing_symbol_returns_no_points(self, get):
        response = Mock(status_code=404)
        get.return_value = response

        points = YahooAdapter().fetch_history("C6E.DE", date(2026, 1, 1), date(2026, 1, 2), "EUR")

        self.assertEqual(points, [])
        response.raise_for_status.assert_not_called()