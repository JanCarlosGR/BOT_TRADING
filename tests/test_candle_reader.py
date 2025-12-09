"""
Tests para el módulo candle_reader
"""

import pytest
from Base import get_candle


class TestCandleReader:
    """Tests para la función get_candle"""
    
    def test_get_current_candle(self):
        """Test obtener vela actual"""
        candle = get_candle('M5', 'ahora', 'EURUSD')
        assert candle is not None
        assert 'open' in candle
        assert 'high' in candle
        assert 'low' in candle
        assert 'close' in candle
        assert candle['is_current'] is True
    
    def test_get_candle_at_time(self):
        """Test obtener vela en horario específico"""
        candle = get_candle('H4', '1am', 'EURUSD')
        if candle:
            assert 'open' in candle
            assert 'type' in candle
    
    def test_candle_structure(self):
        """Test estructura de datos retornada"""
        candle = get_candle('M5', 'ahora', 'EURUSD')
        if candle:
            required_keys = ['open', 'high', 'low', 'close', 'type', 'is_current']
            for key in required_keys:
                assert key in candle, f"Falta la clave: {key}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

