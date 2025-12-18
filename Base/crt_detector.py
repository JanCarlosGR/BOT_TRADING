"""
Módulo para detectar CRT (Candle Range Theory) - Teoría del Rango de Velas
Detecta barridos de liquidez y patrones Vayas en múltiples temporalidades
"""

import logging
from typing import Dict, Optional, List
from Base.candle_reader import get_candle, CandleReader
import MetaTrader5 as mt5


class CRTDetector:
    """
    Detector de CRT (Candle Range Theory)
    Detecta barridos de liquidez y patrones Vayas en diferentes temporalidades
    """
    
    def __init__(self):
        """Inicializa el detector de CRT"""
        self.logger = logging.getLogger(__name__)
        self.candle_reader = CandleReader()
    
    def detect_liquidity_sweep(self, symbol: str, timeframe: str = 'H4', 
                               lookback: int = 5) -> Optional[Dict]:
        """
        Detecta barridos de liquidez (Liquidity Sweep) según CRT
        
        Un barrido ocurre cuando:
        - El precio rompe temporalmente un extremo (high o low) de una vela anterior
        - Pero luego cierra dentro del rango de esa vela
        
        Args:
            symbol: Símbolo a analizar (ej: 'EURUSD')
            timeframe: Temporalidad para análisis ('H4', 'H1', 'D1', etc.)
            lookback: Número de velas anteriores a verificar (default: 5)
            
        Returns:
            Dict con información del barrido o None:
            {
                'detected': bool,
                'sweep_type': str,  # 'BULLISH_SWEEP' o 'BEARISH_SWEEP'
                'direction': str,   # 'BEARISH' o 'BULLISH' (dirección esperada)
                'swept_candle_index': int,  # Índice de la vela barrida
                'swept_extreme': str,  # 'high' o 'low'
                'target_extreme': str,  # 'high' o 'low' (opuesto)
                'target_price': float,  # Precio objetivo (TP)
                'sweep_price': float,   # Precio del barrido
                'current_candle': Dict,  # Vela actual
                'swept_candle': Dict,    # Vela que fue barrida
            }
        """
        try:
            # Obtener velas recientes
            timeframe_map = {
                'M1': mt5.TIMEFRAME_M1,
                'M5': mt5.TIMEFRAME_M5,
                'M15': mt5.TIMEFRAME_M15,
                'M30': mt5.TIMEFRAME_M30,
                'H1': mt5.TIMEFRAME_H1,
                'H4': mt5.TIMEFRAME_H4,
                'D1': mt5.TIMEFRAME_D1,
            }
            
            tf = timeframe_map.get(timeframe.upper(), mt5.TIMEFRAME_H4)
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, lookback + 1)
            
            if rates is None or len(rates) < 2:
                return None
            
            # La vela actual es la última (posición 0)
            current_candle = rates[0]
            current_high = float(current_candle['high'])
            current_low = float(current_candle['low'])
            current_close = float(current_candle['close'])
            
            # Verificar barridos en velas anteriores
            for i in range(1, min(len(rates), lookback + 1)):
                previous_candle = rates[i]
                prev_high = float(previous_candle['high'])
                prev_low = float(previous_candle['low'])
                prev_close = float(previous_candle['close'])
                
                # Barrido Alcista (Bullish Sweep): rompe máximo pero cierra dentro
                if current_high > prev_high and current_close < prev_high:
                    # El precio barrió el máximo pero cerró dentro del rango
                    # Señal: Reversión bajista esperada hacia el mínimo
                    return {
                        'detected': True,
                        'sweep_type': 'BULLISH_SWEEP',
                        'direction': 'BEARISH',  # Reversión esperada
                        'swept_candle_index': i,
                        'swept_extreme': 'high',
                        'target_extreme': 'low',
                        'target_price': prev_low,  # TP hacia el mínimo
                        'sweep_price': prev_high,  # Precio barrido
                        'current_candle': {
                            'high': current_high,
                            'low': current_low,
                            'close': current_close,
                            'open': float(current_candle['open'])
                        },
                        'swept_candle': {
                            'high': prev_high,
                            'low': prev_low,
                            'close': prev_close,
                            'open': float(previous_candle['open'])
                        },
                        'timeframe': timeframe
                    }
                
                # Barrido Bajista (Bearish Sweep): rompe mínimo pero cierra dentro
                if current_low < prev_low and current_close > prev_low:
                    # El precio barrió el mínimo pero cerró dentro del rango
                    # Señal: Reversión alcista esperada hacia el máximo
                    return {
                        'detected': True,
                        'sweep_type': 'BEARISH_SWEEP',
                        'direction': 'BULLISH',  # Reversión esperada
                        'swept_candle_index': i,
                        'swept_extreme': 'low',
                        'target_extreme': 'high',
                        'target_price': prev_high,  # TP hacia el máximo
                        'sweep_price': prev_low,  # Precio barrido
                        'current_candle': {
                            'high': current_high,
                            'low': current_low,
                            'close': current_close,
                            'open': float(current_candle['open'])
                        },
                        'swept_candle': {
                            'high': prev_high,
                            'low': prev_low,
                            'close': prev_close,
                            'open': float(previous_candle['open'])
                        },
                        'timeframe': timeframe
                    }
            
            # No se detectó barrido
            return {
                'detected': False,
                'timeframe': timeframe
            }
            
        except Exception as e:
            self.logger.error(f"Error al detectar barrido de liquidez: {e}", exc_info=True)
            return None
    
    def detect_vayas_pattern(self, symbol: str, timeframe: str = 'D1', 
                            lookback: int = 3) -> Optional[Dict]:
        """
        Detecta el patrón "Vayas" (cambio de sesgo)
        
        El patrón Vayas indica agotamiento de tendencia:
        - En tendencia alcista: vela no rompe máximo anterior, cierra dentro del rango
        - En tendencia bajista: vela no rompe mínimo anterior, cierra dentro del rango
        
        Args:
            symbol: Símbolo a analizar
            timeframe: Temporalidad para análisis ('D1', 'H4', etc.)
            lookback: Número de velas a analizar (default: 3)
            
        Returns:
            Dict con información del patrón Vayas o None:
            {
                'detected': bool,
                'pattern_type': str,  # 'BULLISH_VAYAS' o 'BEARISH_VAYAS'
                'trend_exhaustion': str,  # 'ALCISTA' o 'BAJISTA'
                'current_candle': Dict,
                'previous_candle': Dict,
            }
        """
        try:
            timeframe_map = {
                'M1': mt5.TIMEFRAME_M1,
                'M5': mt5.TIMEFRAME_M5,
                'M15': mt5.TIMEFRAME_M15,
                'M30': mt5.TIMEFRAME_M30,
                'H1': mt5.TIMEFRAME_H1,
                'H4': mt5.TIMEFRAME_H4,
                'D1': mt5.TIMEFRAME_D1,
            }
            
            tf = timeframe_map.get(timeframe.upper(), mt5.TIMEFRAME_D1)
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, lookback + 1)
            
            if rates is None or len(rates) < 2:
                return None
            
            # Vela actual y anterior
            current_candle = rates[0]
            previous_candle = rates[1]
            
            current_high = float(current_candle['high'])
            current_low = float(current_candle['low'])
            current_close = float(current_candle['close'])
            current_open = float(current_candle['open'])
            
            prev_high = float(previous_candle['high'])
            prev_low = float(previous_candle['low'])
            prev_close = float(previous_candle['close'])
            prev_open = float(previous_candle['open'])
            
            # Vayas en tendencia alcista: vela anterior alcista, actual no rompe máximo
            if prev_close > prev_open:  # Vela anterior alcista
                if current_high <= prev_high and current_close < prev_high:
                    # No rompió el máximo y cerró dentro del rango
                    return {
                        'detected': True,
                        'pattern_type': 'BEARISH_VAYAS',
                        'trend_exhaustion': 'ALCISTA',  # Agotamiento de tendencia alcista
                        'current_candle': {
                            'high': current_high,
                            'low': current_low,
                            'close': current_close,
                            'open': current_open
                        },
                        'previous_candle': {
                            'high': prev_high,
                            'low': prev_low,
                            'close': prev_close,
                            'open': prev_open
                        },
                        'timeframe': timeframe
                    }
            
            # Vayas en tendencia bajista: vela anterior bajista, actual no rompe mínimo
            if prev_close < prev_open:  # Vela anterior bajista
                if current_low >= prev_low and current_close > prev_low:
                    # No rompió el mínimo y cerró dentro del rango
                    return {
                        'detected': True,
                        'pattern_type': 'BULLISH_VAYAS',
                        'trend_exhaustion': 'BAJISTA',  # Agotamiento de tendencia bajista
                        'current_candle': {
                            'high': current_high,
                            'low': current_low,
                            'close': current_close,
                            'open': current_open
                        },
                        'previous_candle': {
                            'high': prev_high,
                            'low': prev_low,
                            'close': prev_close,
                            'open': prev_open
                        },
                        'timeframe': timeframe
                    }
            
            # No se detectó patrón Vayas
            return {
                'detected': False,
                'timeframe': timeframe
            }
            
        except Exception as e:
            self.logger.error(f"Error al detectar patrón Vayas: {e}", exc_info=True)
            return None
    
    def detect_engulfing_candle(self, symbol: str, timeframe: str = 'M15') -> Optional[Dict]:
        """
        Detecta velas envolventes (Engulfing Candles) que pueden confirmar reversiones
        
        Args:
            symbol: Símbolo a analizar
            timeframe: Temporalidad para análisis
            
        Returns:
            Dict con información de la vela envolvente o None
            {
                'detected': bool,
                'engulfing_type': str,  # 'BULLISH_ENGULFING' o 'BEARISH_ENGULFING'
                'current_candle': Dict,
                'previous_candle': Dict,
            }
        """
        try:
            timeframe_map = {
                'M1': mt5.TIMEFRAME_M1,
                'M5': mt5.TIMEFRAME_M5,
                'M15': mt5.TIMEFRAME_M15,
                'M30': mt5.TIMEFRAME_M30,
                'H1': mt5.TIMEFRAME_H1,
                'H4': mt5.TIMEFRAME_H4,
                'D1': mt5.TIMEFRAME_D1,
            }
            
            tf = timeframe_map.get(timeframe.upper(), mt5.TIMEFRAME_M15)
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, 2)
            
            if rates is None or len(rates) < 2:
                return None
            
            current_candle = rates[0]
            previous_candle = rates[1]
            
            current_high = float(current_candle['high'])
            current_low = float(current_candle['low'])
            current_close = float(current_candle['close'])
            current_open = float(current_candle['open'])
            
            prev_high = float(previous_candle['high'])
            prev_low = float(previous_candle['low'])
            prev_close = float(previous_candle['close'])
            prev_open = float(previous_candle['open'])
            
            # Vela envolvente alcista: vela anterior bajista, actual alcista que la envuelve
            if prev_close < prev_open:  # Vela anterior bajista
                if current_close > current_open:  # Vela actual alcista
                    if current_low < prev_low and current_high > prev_high:
                        # La vela actual envuelve completamente la anterior
                        return {
                            'detected': True,
                            'engulfing_type': 'BULLISH_ENGULFING',
                            'current_candle': {
                                'high': current_high,
                                'low': current_low,
                                'close': current_close,
                                'open': current_open
                            },
                            'previous_candle': {
                                'high': prev_high,
                                'low': prev_low,
                                'close': prev_close,
                                'open': prev_open
                            },
                            'timeframe': timeframe
                        }
            
            # Vela envolvente bajista: vela anterior alcista, actual bajista que la envuelve
            if prev_close > prev_open:  # Vela anterior alcista
                if current_close < current_open:  # Vela actual bajista
                    if current_low < prev_low and current_high > prev_high:
                        # La vela actual envuelve completamente la anterior
                        return {
                            'detected': True,
                            'engulfing_type': 'BEARISH_ENGULFING',
                            'current_candle': {
                                'high': current_high,
                                'low': current_low,
                                'close': current_close,
                                'open': current_open
                            },
                            'previous_candle': {
                                'high': prev_high,
                                'low': prev_low,
                                'close': prev_close,
                                'open': prev_open
                            },
                            'timeframe': timeframe
                        }
            
            return {
                'detected': False,
                'timeframe': timeframe
            }
            
        except Exception as e:
            self.logger.error(f"Error al detectar vela envolvente: {e}", exc_info=True)
            return None


def detect_crt_sweep(symbol: str, timeframe: str = 'H4', lookback: int = 5) -> Optional[Dict]:
    """
    Función de conveniencia para detectar barridos de liquidez CRT
    
    Args:
        symbol: Símbolo a analizar
        timeframe: Temporalidad ('H4', 'H1', 'D1', etc.)
        lookback: Número de velas anteriores a verificar
        
    Returns:
        Dict con información del barrido o None
    """
    detector = CRTDetector()
    return detector.detect_liquidity_sweep(symbol, timeframe, lookback)


def detect_crt_vayas(symbol: str, timeframe: str = 'D1', lookback: int = 3) -> Optional[Dict]:
    """
    Función de conveniencia para detectar patrón Vayas
    
    Args:
        symbol: Símbolo a analizar
        timeframe: Temporalidad ('D1', 'H4', etc.)
        lookback: Número de velas a analizar
        
    Returns:
        Dict con información del patrón Vayas o None
    """
    detector = CRTDetector()
    return detector.detect_vayas_pattern(symbol, timeframe, lookback)


def detect_engulfing(symbol: str, timeframe: str = 'M15') -> Optional[Dict]:
    """
    Función de conveniencia para detectar velas envolventes
    
    Args:
        symbol: Símbolo a analizar
        timeframe: Temporalidad
        
    Returns:
        Dict con información de la vela envolvente o None
    """
    detector = CRTDetector()
    return detector.detect_engulfing_candle(symbol, timeframe)
