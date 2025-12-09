"""
Tests para el módulo news_checker
"""

import pytest
from Base import can_trade_now, get_daily_news_summary, validate_trading_day


class TestNewsChecker:
    """Tests para las funciones de news_checker"""
    
    def test_can_trade_now(self):
        """Test verificación si se puede operar"""
        can_trade, reason, next_news = can_trade_now('EURUSD')
        assert isinstance(can_trade, bool)
        assert isinstance(reason, str)
        # next_news puede ser None o un dict
        if next_news:
            assert isinstance(next_news, dict)
    
    def test_validate_trading_day(self):
        """Test validación de día operativo"""
        is_trading, reason, holidays = validate_trading_day()
        assert isinstance(is_trading, bool)
        assert isinstance(reason, str)
        assert isinstance(holidays, list)
    
    def test_get_daily_news_summary(self):
        """Test resumen de noticias del día"""
        summary = get_daily_news_summary('EURUSD')
        assert isinstance(summary, str)
        # Debe contener información sobre noticias o indicar que no hay


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

