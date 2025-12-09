"""
Módulo para detectar Turtle Soup en temporalidad H4
Estrategia ICT: Detección de barridos de liquidez y objetivos
"""

import logging
from typing import Dict, Optional, Tuple
from Base.candle_reader import get_candle
from datetime import datetime
import pytz


class TurtleSoupDetector:
    """
    Detector de Turtle Soup en temporalidad H4
    Evalúa velas de 1 AM, 5 AM y 9 AM (hora NY) para detectar barridos
    """
    
    def __init__(self):
        """Inicializa el detector de Turtle Soup"""
        self.logger = logging.getLogger(__name__)
        self.ny_tz = pytz.timezone('America/New_York')
    
    def get_h4_key_candles(self, symbol: str) -> Dict[str, Optional[Dict]]:
        """
        Obtiene las velas H4 clave: 1 AM, 5 AM y 9 AM (hora NY)
        
        Args:
            symbol: Símbolo a analizar (ej: 'EURUSD')
            
        Returns:
            Dict con las velas:
            {
                '1am': {...} o None,
                '5am': {...} o None,
                '9am': {...} o None
            }
        """
        candles = {}
        
        try:
            # Obtener vela de 1 AM NY
            candle_1am = get_candle('H4', '1am', symbol)
            candles['1am'] = candle_1am
            
            # Obtener vela de 5 AM NY
            candle_5am = get_candle('H4', '5am', symbol)
            candles['5am'] = candle_5am
            
            # Obtener vela de 9 AM NY
            candle_9am = get_candle('H4', '9am', symbol)
            candles['9am'] = candle_9am
            
            self.logger.debug(f"Velas H4 obtenidas para {symbol}: 1AM={candle_1am is not None}, 5AM={candle_5am is not None}, 9AM={candle_9am is not None}")
            
        except Exception as e:
            self.logger.error(f"Error al obtener velas H4: {e}", exc_info=True)
        
        return candles
    
    def detect_turtle_soup(self, symbol: str) -> Optional[Dict]:
        """
        Detecta Turtle Soup en H4: verifica si la vela de 9 AM barre extremos de 1 AM o 5 AM
        
        Args:
            symbol: Símbolo a analizar
            
        Returns:
            Dict con información del Turtle Soup detectado o None:
            {
                'detected': bool,
                'swept_candle': str,  # '1am' o '5am'
                'swept_extreme': str,  # 'high' o 'low'
                'target_extreme': str,  # 'high' o 'low' (opuesto)
                'target_price': float,  # Precio objetivo (TP)
                'sweep_price': float,   # Precio del barrido
                'candles': Dict,        # Velas H4 usadas
                'direction': str        # 'BULLISH' o 'BEARISH'
            }
        """
        try:
            # Obtener velas clave
            candles = self.get_h4_key_candles(symbol)
            
            candle_1am = candles.get('1am')
            candle_5am = candles.get('5am')
            candle_9am = candles.get('9am')
            
            # Validar que tengamos todas las velas necesarias
            if not candle_9am:
                self.logger.warning("No se pudo obtener la vela de 9 AM")
                return None
            
            if not candle_1am and not candle_5am:
                self.logger.warning("No se pudieron obtener velas de 1 AM ni 5 AM")
                return None
            
            # Verificar si la vela de 9 AM barre extremos
            result = None
            
            # Verificar barrido de vela 1 AM
            if candle_1am:
                result = self._check_sweep(candle_9am, candle_1am, '1am')
                if result:
                    return result
            
            # Verificar barrido de vela 5 AM
            if candle_5am:
                result = self._check_sweep(candle_9am, candle_5am, '5am')
                if result:
                    return result
            
            # No se detectó Turtle Soup
            return {
                'detected': False,
                'candles': candles
            }
            
        except Exception as e:
            self.logger.error(f"Error al detectar Turtle Soup: {e}", exc_info=True)
            return None
    
    def _check_sweep(self, candle_9am: Dict, target_candle: Dict, target_name: str) -> Optional[Dict]:
        """
        Verifica si la vela de 9 AM barre un extremo de la vela objetivo
        
        Args:
            candle_9am: Vela de 9 AM
            target_candle: Vela objetivo (1 AM o 5 AM)
            target_name: Nombre de la vela objetivo ('1am' o '5am')
            
        Returns:
            Dict con información del barrido o None
        """
        try:
            # Obtener extremos de la vela objetivo
            target_high = target_candle.get('high')
            target_low = target_candle.get('low')
            
            # Obtener extremos de la vela de 9 AM
            candle_9am_high = candle_9am.get('high')
            candle_9am_low = candle_9am.get('low')
            
            if target_high is None or target_low is None:
                return None
            
            if candle_9am_high is None or candle_9am_low is None:
                return None
            
            # Verificar si barre el HIGH (barrido alcista)
            if candle_9am_high > target_high:
                # El low de la vela objetivo es el TP
                return {
                    'detected': True,
                    'swept_candle': target_name,
                    'swept_extreme': 'high',
                    'target_extreme': 'low',
                    'target_price': target_low,
                    'sweep_price': target_high,
                    'candles': {
                        '1am': target_candle if target_name == '1am' else None,
                        '5am': target_candle if target_name == '5am' else None,
                        '9am': candle_9am
                    },
                    'direction': 'BEARISH',  # Barrido alcista → esperamos reversión bajista
                    'sweep_type': 'BULLISH_SWEEP'  # El barrido fue alcista
                }
            
            # Verificar si barre el LOW (barrido bajista)
            if candle_9am_low < target_low:
                # El high de la vela objetivo es el TP
                return {
                    'detected': True,
                    'swept_candle': target_name,
                    'swept_extreme': 'low',
                    'target_extreme': 'high',
                    'target_price': target_high,
                    'sweep_price': target_low,
                    'candles': {
                        '1am': target_candle if target_name == '1am' else None,
                        '5am': target_candle if target_name == '5am' else None,
                        '9am': candle_9am
                    },
                    'direction': 'BULLISH',  # Barrido bajista → esperamos reversión alcista
                    'sweep_type': 'BEARISH_SWEEP'  # El barrido fue bajista
                }
            
            # No hay barrido
            return None
            
        except Exception as e:
            self.logger.error(f"Error al verificar barrido: {e}", exc_info=True)
            return None


def detect_turtle_soup_h4(symbol: str) -> Optional[Dict]:
    """
    Función de conveniencia para detectar Turtle Soup en H4
    
    Args:
        symbol: Símbolo a analizar
        
    Returns:
        Dict con información del Turtle Soup o None
    """
    detector = TurtleSoupDetector()
    return detector.detect_turtle_soup(symbol)

