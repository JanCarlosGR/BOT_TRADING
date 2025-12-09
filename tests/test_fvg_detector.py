"""
Tests para el módulo fvg_detector
"""

import pytest
from Base import detect_fvg


class TestFVGDetector:
    """Tests para la función detect_fvg"""
    
    def test_detect_fvg_basic(self):
        """Test detección básica de FVG"""
        fvg = detect_fvg('EURUSD', 'H4')
        # Puede retornar None si no hay FVG, o un dict si hay
        if fvg:
            assert 'fvg_type' in fvg
            assert fvg['fvg_type'] in ['ALCISTA', 'BAJISTA']
            assert 'fvg_bottom' in fvg
            assert 'fvg_top' in fvg
            assert 'status' in fvg
    
    def test_fvg_structure(self):
        """Test estructura de datos retornada"""
        fvg = detect_fvg('EURUSD', 'M5')
        if fvg:
            required_keys = [
                'fvg_detected', 'fvg_type', 'fvg_bottom', 'fvg_top',
                'current_price', 'entered_fvg', 'exited_fvg', 'status'
            ]
            for key in required_keys:
                assert key in fvg, f"Falta la clave: {key}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

