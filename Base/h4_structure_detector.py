"""
Módulo para detectar estructura y objetivos en temporalidad H4
Analiza velas H4 para obtener swing points, estructura y objetivos
"""

import logging
from typing import Dict, Optional, List, Tuple
import MetaTrader5 as mt5
from datetime import datetime


class H4StructureDetector:
    """
    Detector de estructura H4 para obtener objetivos y dirección
    Analiza velas H4 para identificar swing highs/lows y estructura del mercado
    """
    
    def __init__(self):
        """Inicializa el detector de estructura H4"""
        self.logger = logging.getLogger(__name__)
    
    def _parse_timeframe(self, timeframe: str) -> int:
        """Convierte string de temporalidad a constante MT5"""
        timeframe_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
        }
        return timeframe_map.get(timeframe.upper(), mt5.TIMEFRAME_H4)
    
    def get_h4_structure(self, symbol: str, lookback: int = 20) -> Optional[Dict]:
        """
        Analiza estructura H4 para obtener objetivos y dirección
        
        Args:
            symbol: Símbolo a analizar
            lookback: Número de velas H4 a analizar (default: 20)
            
        Returns:
            Dict con información de estructura H4:
            {
                'has_structure': bool,
                'direction': str,  # 'BULLISH', 'BEARISH', o 'NEUTRAL'
                'swing_high': float,  # Swing high más reciente
                'swing_low': float,   # Swing low más reciente
                'current_swing_high': float,  # High de la vela actual
                'current_swing_low': float,   # Low de la vela actual
                'target_high': float,  # Objetivo alcista (swing high anterior o estructura)
                'target_low': float,   # Objetivo bajista (swing low anterior o estructura)
                'structure_type': str,  # 'UPTREND', 'DOWNTREND', 'RANGE'
                'candles': List[Dict],  # Velas H4 analizadas
            }
        """
        try:
            tf = self._parse_timeframe('H4')
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, lookback)
            
            if rates is None or len(rates) < 3:
                return None
            
            # Convertir a lista de diccionarios
            candles = []
            for candle_data in rates:
                candles.append({
                    'time': datetime.fromtimestamp(candle_data['time']),
                    'open': float(candle_data['open']),
                    'high': float(candle_data['high']),
                    'low': float(candle_data['low']),
                    'close': float(candle_data['close']),
                })
            
            # Ordenar por tiempo (más antigua primero)
            candles = sorted(candles, key=lambda x: x['time'])
            
            # Vela actual (más reciente)
            current_candle = candles[-1]
            current_high = current_candle['high']
            current_low = current_candle['low']
            current_close = current_candle['close']
            
            # Encontrar swing highs y lows
            swing_highs = []
            swing_lows = []
            
            # Buscar swing points (máximos y mínimos locales)
            for i in range(1, len(candles) - 1):
                prev_candle = candles[i - 1]
                curr_candle = candles[i]
                next_candle = candles[i + 1]
                
                # Swing high: high mayor que anteriores y siguientes
                if (curr_candle['high'] > prev_candle['high'] and 
                    curr_candle['high'] > next_candle['high']):
                    swing_highs.append({
                        'price': curr_candle['high'],
                        'time': curr_candle['time'],
                        'index': i
                    })
                
                # Swing low: low menor que anteriores y siguientes
                if (curr_candle['low'] < prev_candle['low'] and 
                    curr_candle['low'] < next_candle['low']):
                    swing_lows.append({
                        'price': curr_candle['low'],
                        'time': curr_candle['time'],
                        'index': i
                    })
            
            # Determinar dirección basada en estructura
            direction = 'NEUTRAL'
            structure_type = 'RANGE'
            
            # Si hay swing highs y lows, analizar tendencia
            if swing_highs and swing_lows:
                # Ordenar por tiempo (más reciente primero)
                swing_highs_sorted = sorted(swing_highs, key=lambda x: x['time'], reverse=True)
                swing_lows_sorted = sorted(swing_lows, key=lambda x: x['time'], reverse=True)
                
                latest_high = swing_highs_sorted[0] if swing_highs_sorted else None
                latest_low = swing_lows_sorted[0] if swing_lows_sorted else None
                
                # Determinar tendencia
                if latest_high and latest_low:
                    # Uptrend: swing highs y lows crecientes
                    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
                        prev_high = swing_highs_sorted[1] if len(swing_highs_sorted) > 1 else None
                        prev_low = swing_lows_sorted[1] if len(swing_lows_sorted) > 1 else None
                        
                        if prev_high and prev_low:
                            if (latest_high['price'] > prev_high['price'] and 
                                latest_low['price'] > prev_low['price']):
                                direction = 'BULLISH'
                                structure_type = 'UPTREND'
                            elif (latest_high['price'] < prev_high['price'] and 
                                  latest_low['price'] < prev_low['price']):
                                direction = 'BEARISH'
                                structure_type = 'DOWNTREND'
            
            # Si no hay estructura clara, usar precio actual vs swing points
            if direction == 'NEUTRAL':
                if swing_highs and swing_lows:
                    latest_high = sorted(swing_highs, key=lambda x: x['time'], reverse=True)[0]
                    latest_low = sorted(swing_lows, key=lambda x: x['time'], reverse=True)[0]
                    
                    # Si el precio está cerca del swing high, posible reversión bajista
                    if current_close >= latest_high['price'] * 0.999:  # Dentro del 0.1%
                        direction = 'BEARISH'
                    # Si el precio está cerca del swing low, posible reversión alcista
                    elif current_close <= latest_low['price'] * 1.001:  # Dentro del 0.1%
                        direction = 'BULLISH'
            
            # Calcular objetivos
            target_high = None
            target_low = None
            
            if swing_highs:
                # Objetivo alcista: siguiente swing high o extensión
                sorted_highs = sorted(swing_highs, key=lambda x: x['price'], reverse=True)
                target_high = sorted_highs[0]['price']  # Swing high más alto
            else:
                # Si no hay swing highs, usar high más alto de las velas
                target_high = max(c['high'] for c in candles)
            
            if swing_lows:
                # Objetivo bajista: siguiente swing low o extensión
                sorted_lows = sorted(swing_lows, key=lambda x: x['price'])
                target_low = sorted_lows[0]['price']  # Swing low más bajo
            else:
                # Si no hay swing lows, usar low más bajo de las velas
                target_low = min(c['low'] for c in candles)
            
            # Swing high/low más reciente
            recent_swing_high = swing_highs[-1]['price'] if swing_highs else current_high
            recent_swing_low = swing_lows[-1]['price'] if swing_lows else current_low
            
            return {
                'has_structure': True,
                'direction': direction,
                'swing_high': recent_swing_high,
                'swing_low': recent_swing_low,
                'current_swing_high': current_high,
                'current_swing_low': current_low,
                'target_high': target_high,
                'target_low': target_low,
                'structure_type': structure_type,
                'swing_highs': swing_highs,
                'swing_lows': swing_lows,
                'candles': candles[-5:] if len(candles) >= 5 else candles  # Últimas 5 velas
            }
            
        except Exception as e:
            self.logger.error(f"Error al analizar estructura H4: {e}", exc_info=True)
            return None
    
    def get_h4_targets(self, symbol: str, direction: str = None) -> Optional[Dict]:
        """
        Obtiene objetivos desde H4 basado en estructura
        
        Args:
            symbol: Símbolo a analizar
            direction: Dirección esperada ('BULLISH' o 'BEARISH') - si es None, se detecta automáticamente
            
        Returns:
            Dict con objetivos:
            {
                'direction': str,  # 'BULLISH' o 'BEARISH'
                'target_price': float,  # Precio objetivo (TP)
                'structure': Dict,  # Información de estructura completa
            }
        """
        try:
            structure = self.get_h4_structure(symbol)
            
            if not structure or not structure.get('has_structure'):
                return None
            
            detected_direction = structure.get('direction')
            
            # Si no se especifica dirección, usar la detectada
            if direction is None:
                direction = detected_direction
            
            # Si la dirección detectada es NEUTRAL, usar swing points más cercanos
            if direction == 'NEUTRAL' or detected_direction == 'NEUTRAL':
                current_price = structure.get('current_swing_high', 0)
                swing_high = structure.get('swing_high', 0)
                swing_low = structure.get('swing_low', 0)
                
                # Determinar dirección basada en proximidad a swing points
                dist_to_high = abs(current_price - swing_high)
                dist_to_low = abs(current_price - swing_low)
                
                if dist_to_low < dist_to_high:
                    direction = 'BULLISH'  # Más cerca del swing low, esperamos subida
                    target_price = swing_high
                else:
                    direction = 'BEARISH'  # Más cerca del swing high, esperamos bajada
                    target_price = swing_low
            else:
                # Usar objetivos según dirección
                if direction == 'BULLISH':
                    target_price = structure.get('target_high', structure.get('swing_high'))
                else:  # BEARISH
                    target_price = structure.get('target_low', structure.get('swing_low'))
            
            return {
                'direction': direction,
                'target_price': target_price,
                'structure': structure
            }
            
        except Exception as e:
            self.logger.error(f"Error al obtener objetivos H4: {e}", exc_info=True)
            return None


def get_h4_structure(symbol: str, lookback: int = 20) -> Optional[Dict]:
    """
    Función de conveniencia para obtener estructura H4
    
    Args:
        symbol: Símbolo a analizar
        lookback: Número de velas H4 a analizar
        
    Returns:
        Dict con información de estructura H4 o None
    """
    detector = H4StructureDetector()
    return detector.get_h4_structure(symbol, lookback)


def get_h4_targets(symbol: str, direction: str = None) -> Optional[Dict]:
    """
    Función de conveniencia para obtener objetivos desde H4
    
    Args:
        symbol: Símbolo a analizar
        direction: Dirección esperada ('BULLISH' o 'BEARISH')
        
    Returns:
        Dict con objetivos o None
    """
    detector = H4StructureDetector()
    return detector.get_h4_targets(symbol, direction)
