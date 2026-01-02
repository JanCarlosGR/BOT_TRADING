"""
Detector de Niveles Diarios (Previous Daily High/Low)
Detecta cuando el precio toma (alcanza) los altos o bajos diarios de días anteriores
Útil para identificar niveles de liquidez y zonas de interés en trading ICT/SMC
"""

import MetaTrader5 as mt5
import logging
from typing import Dict, Optional, List, Tuple
from datetime import datetime, date, timedelta
from pytz import timezone as tz


class DailyLevelsDetector:
    """
    Detector de niveles diarios (Previous Daily High/Low)
    Identifica cuando el precio alcanza o toma los extremos de días anteriores
    """
    
    def __init__(self, timezone_str: str = "America/New_York"):
        """
        Inicializa el detector de niveles diarios
        
        Args:
            timezone_str: Zona horaria para determinar días (default: "America/New_York")
        """
        self.logger = logging.getLogger(__name__)
        self.tz = tz(timezone_str)
    
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
            'W1': mt5.TIMEFRAME_W1,
        }
        return timeframe_map.get(timeframe.upper(), mt5.TIMEFRAME_D1)
    
    def _get_daily_candle(self, symbol: str, days_ago: int = 1) -> Optional[Dict]:
        """
        Obtiene la vela diaria (D1) de N días atrás
        
        Args:
            symbol: Símbolo a analizar
            days_ago: Días hacia atrás (1 = ayer, 2 = anteayer, etc.)
            
        Returns:
            Dict con información de la vela diaria o None
        """
        try:
            # Obtener velas D1
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, days_ago + 1)
            
            if rates is None or len(rates) < days_ago + 1:
                return None
            
            # La posición 0 es la vela actual, posición 1 es ayer, posición 2 es anteayer, etc.
            # Para days_ago=1, necesitamos posición 1 (ayer)
            candle_data = rates[days_ago]
            
            candle_time = datetime.fromtimestamp(candle_data['time'])
            
            return {
                'time': candle_time,
                'date': candle_time.date(),
                'open': float(candle_data['open']),
                'high': float(candle_data['high']),
                'low': float(candle_data['low']),
                'close': float(candle_data['close']),
                'volume': int(candle_data['tick_volume']),
            }
        except Exception as e:
            self.logger.error(f"Error al obtener vela diaria de {days_ago} días atrás: {e}", exc_info=True)
            return None
    
    def get_previous_daily_levels(self, symbol: str, lookback_days: int = 5) -> Optional[Dict]:
        """
        Obtiene los niveles HIGH y LOW de los días anteriores
        
        Args:
            symbol: Símbolo a analizar
            lookback_days: Número de días anteriores a revisar (default: 5)
            
        Returns:
            Dict con información de niveles diarios:
            {
                'previous_highs': List[Dict],  # Lista de HIGHs de días anteriores
                'previous_lows': List[Dict],   # Lista de LOWs de días anteriores
                'highest_high': float,         # El HIGH más alto de los días revisados
                'lowest_low': float,           # El LOW más bajo de los días revisados
                'highest_high_date': date,     # Fecha del HIGH más alto
                'lowest_low_date': date,       # Fecha del LOW más bajo
            }
        """
        try:
            previous_highs = []
            previous_lows = []
            
            # Obtener velas D1 de los últimos N días (incluyendo hoy)
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, lookback_days + 1)
            
            if rates is None or len(rates) < 2:
                return None
            
            # Procesar días anteriores (saltar el día actual, posición 0)
            for i in range(1, min(len(rates), lookback_days + 1)):
                candle_data = rates[i]
                candle_time = datetime.fromtimestamp(candle_data['time'])
                candle_date = candle_time.date()
                
                high = float(candle_data['high'])
                low = float(candle_data['low'])
                
                previous_highs.append({
                    'date': candle_date,
                    'high': high,
                    'time': candle_time,
                })
                
                previous_lows.append({
                    'date': candle_date,
                    'low': low,
                    'time': candle_time,
                })
            
            if not previous_highs or not previous_lows:
                return None
            
            # Encontrar el HIGH más alto y el LOW más bajo
            highest_high_item = max(previous_highs, key=lambda x: x['high'])
            lowest_low_item = min(previous_lows, key=lambda x: x['low'])
            
            return {
                'previous_highs': previous_highs,
                'previous_lows': previous_lows,
                'highest_high': highest_high_item['high'],
                'lowest_low': lowest_low_item['low'],
                'highest_high_date': highest_high_item['date'],
                'lowest_low_date': lowest_low_item['date'],
                'lookback_days': lookback_days,
            }
            
        except Exception as e:
            self.logger.error(f"Error al obtener niveles diarios: {e}", exc_info=True)
            return None
    
    def detect_daily_level_touch(self, symbol: str, lookback_days: int = 5, 
                                 tolerance_pips: float = 1.0) -> Optional[Dict]:
        """
        Detecta si el precio actual está tocando o alcanzando un nivel diario previo
        
        IMPORTANTE: Detecta incluso si el precio toma el nivel por solo 1 pip.
        Un "take" ocurre cuando el precio alcanza o supera el nivel (incluso mínimamente).
        
        Args:
            symbol: Símbolo a analizar
            lookback_days: Número de días anteriores a revisar (default: 5)
            tolerance_pips: Tolerancia en pips para considerar que el precio "tocó" el nivel (default: 1.0)
                           - Para HIGH: precio >= (high - tolerance)
                           - Para LOW: precio <= (low + tolerance)
            
        Returns:
            Dict con información del nivel tocado o None:
            {
                'level_touched': bool,         # True si se tocó algún nivel
                'level_type': str,             # 'HIGH' o 'LOW' o None
                'level_price': float,          # Precio del nivel tocado
                'level_date': date,            # Fecha del día del nivel
                'current_price': float,        # Precio actual
                'distance_pips': float,        # Distancia en pips desde el nivel
                'is_taking': bool,             # True si el precio está "tomando" el nivel
                'has_taken': bool,             # True si el precio ya tomó el nivel (lo alcanzó o superó)
                'previous_highs': List[Dict], # Lista de HIGHs revisados
                'previous_lows': List[Dict],   # Lista de LOWs revisados
            }
        """
        try:
            # Obtener niveles diarios
            levels = self.get_previous_daily_levels(symbol, lookback_days)
            if not levels:
                return None
            
            # Obtener precio actual
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            
            current_price = float(tick.bid)
            
            # Obtener información del símbolo para calcular pips
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return None
            
            point = symbol_info.point
            pip_value = point * 10 if symbol_info.digits == 5 else point * 1
            tolerance_price = tolerance_pips * pip_value
            
            # ⚠️ IMPORTANTE: Detectar cuando el precio TOMA el nivel (incluso por 1 pip)
            # Para HIGH: precio >= (high - tolerance) → El precio alcanzó o superó el HIGH
            # Para LOW: precio <= (low + tolerance) → El precio alcanzó o cayó por debajo del LOW
            
            # Verificar si el precio está tomando algún HIGH previo
            # Un HIGH se considera "tomado" si: current_price >= (high_price - tolerance)
            # Esto significa que el precio alcanzó o superó el HIGH (incluso por 1 pip)
            taken_high = None
            taken_high_distance = None
            
            for high_item in levels['previous_highs']:
                high_price = high_item['high']
                # Para HIGH: el precio toma si está en o por encima del HIGH (con tolerancia)
                # Si current_price >= (high_price - tolerance), el HIGH fue tomado
                if current_price >= (high_price - tolerance_price):
                    distance = current_price - high_price  # Puede ser negativo si está por encima
                    distance_pips_val = distance / pip_value
                    
                    # Si no hay otro HIGH tomado, o este está más cerca, usarlo
                    if taken_high is None or abs(distance_pips_val) < abs(taken_high_distance):
                        taken_high = {
                            'price': high_price,
                            'date': high_item['date'],
                            'distance': distance,
                            'distance_pips': distance_pips_val,
                        }
                        taken_high_distance = distance_pips_val
            
            # Verificar si el precio está tomando algún LOW previo
            # Un LOW se considera "tomado" si: current_price <= (low_price + tolerance)
            # Esto significa que el precio alcanzó o cayó por debajo del LOW (incluso por 1 pip)
            taken_low = None
            taken_low_distance = None
            
            for low_item in levels['previous_lows']:
                low_price = low_item['low']
                # Para LOW: el precio toma si está en o por debajo del LOW (con tolerancia)
                # Si current_price <= (low_price + tolerance), el LOW fue tomado
                if current_price <= (low_price + tolerance_price):
                    distance = current_price - low_price  # Puede ser positivo si está por encima
                    distance_pips_val = distance / pip_value
                    
                    # Si no hay otro LOW tomado, o este está más cerca, usarlo
                    if taken_low is None or abs(distance_pips_val) < abs(taken_low_distance):
                        taken_low = {
                            'price': low_price,
                            'date': low_item['date'],
                            'distance': distance,
                            'distance_pips': distance_pips_val,
                        }
                        taken_low_distance = distance_pips_val
            
            # Determinar qué nivel fue tomado (prioridad: el que está más cerca del nivel exacto)
            level_touched = False
            level_type = None
            level_price = None
            level_date = None
            distance_pips = None
            is_taking = False
            has_taken = False
            
            if taken_high and taken_low:
                # Ambos fueron tomados, usar el que está más cerca del nivel exacto
                if abs(taken_high_distance) <= abs(taken_low_distance):
                    # HIGH está más cerca del nivel exacto
                    level_touched = True
                    level_type = 'HIGH'
                    level_price = taken_high['price']
                    level_date = taken_high['date']
                    distance_pips = taken_high_distance
                    is_taking = True
                    has_taken = current_price >= taken_high['price']  # True si superó el HIGH
                else:
                    # LOW está más cerca del nivel exacto
                    level_touched = True
                    level_type = 'LOW'
                    level_price = taken_low['price']
                    level_date = taken_low['date']
                    distance_pips = taken_low_distance
                    is_taking = True
                    has_taken = current_price <= taken_low['price']  # True si cayó por debajo del LOW
            elif taken_high:
                # Solo HIGH fue tomado
                level_touched = True
                level_type = 'HIGH'
                level_price = taken_high['price']
                level_date = taken_high['date']
                distance_pips = taken_high_distance
                is_taking = True
                has_taken = current_price >= taken_high['price']  # True si superó el HIGH
            elif taken_low:
                # Solo LOW fue tomado
                level_touched = True
                level_type = 'LOW'
                level_price = taken_low['price']
                level_date = taken_low['date']
                distance_pips = taken_low_distance
                is_taking = True
                has_taken = current_price <= taken_low['price']  # True si cayó por debajo del LOW
            
            return {
                'level_touched': level_touched,
                'level_type': level_type,
                'level_price': level_price,
                'level_date': level_date,
                'current_price': current_price,
                'distance_pips': distance_pips,
                'is_taking': is_taking,
                'has_taken': has_taken,  # True si el precio realmente tomó el nivel (lo alcanzó o superó)
                'previous_highs': levels['previous_highs'],
                'previous_lows': levels['previous_lows'],
                'highest_high': levels['highest_high'],
                'lowest_low': levels['lowest_low'],
                'highest_high_date': levels['highest_high_date'],
                'lowest_low_date': levels['lowest_low_date'],
            }
            
        except Exception as e:
            self.logger.error(f"Error al detectar toque de nivel diario: {e}", exc_info=True)
            return None
    
    def detect_daily_high_take(self, symbol: str, lookback_days: int = 5, 
                               tolerance_pips: float = 1.0) -> Optional[Dict]:
        """
        Detecta específicamente si el precio está tomando un HIGH diario previo
        
        IMPORTANTE: Detecta incluso si el precio toma el HIGH por solo 1 pip.
        Un HIGH se considera "tomado" si: current_price >= (high_price - tolerance)
        
        Args:
            symbol: Símbolo a analizar
            lookback_days: Número de días anteriores a revisar
            tolerance_pips: Tolerancia en pips (default: 1.0)
            
        Returns:
            Dict con información del HIGH tomado o None
        """
        touch_info = self.detect_daily_level_touch(symbol, lookback_days, tolerance_pips)
        
        if touch_info and touch_info.get('level_type') == 'HIGH' and touch_info.get('is_taking'):
            return touch_info
        
        return None
    
    def detect_daily_low_take(self, symbol: str, lookback_days: int = 5, 
                              tolerance_pips: float = 1.0) -> Optional[Dict]:
        """
        Detecta específicamente si el precio está tomando un LOW diario previo
        
        IMPORTANTE: Detecta incluso si el precio toma el LOW por solo 1 pip.
        Un LOW se considera "tomado" si: current_price <= (low_price + tolerance)
        
        Args:
            symbol: Símbolo a analizar
            lookback_days: Número de días anteriores a revisar
            tolerance_pips: Tolerancia en pips (default: 1.0)
            
        Returns:
            Dict con información del LOW tomado o None
        """
        touch_info = self.detect_daily_level_touch(symbol, lookback_days, tolerance_pips)
        
        if touch_info and touch_info.get('level_type') == 'LOW' and touch_info.get('is_taking'):
            return touch_info
        
        return None
    
    def get_yesterday_levels(self, symbol: str) -> Optional[Dict]:
        """
        Obtiene los niveles HIGH y LOW del día anterior (ayer)
        
        Args:
            symbol: Símbolo a analizar
            
        Returns:
            Dict con HIGH y LOW de ayer o None:
            {
                'date': date,          # Fecha de ayer
                'high': float,         # HIGH de ayer
                'low': float,          # LOW de ayer
                'open': float,         # OPEN de ayer
                'close': float,        # CLOSE de ayer
            }
        """
        candle = self._get_daily_candle(symbol, days_ago=1)
        
        if not candle:
            return None
        
        return {
            'date': candle['date'],
            'high': candle['high'],
            'low': candle['low'],
            'open': candle['open'],
            'close': candle['close'],
        }
    
    def is_price_near_daily_level(self, symbol: str, level_price: float, 
                                  tolerance_pips: float = 5.0) -> Tuple[bool, float]:
        """
        Verifica si el precio actual está cerca de un nivel específico
        
        Args:
            symbol: Símbolo a analizar
            level_price: Precio del nivel a verificar
            tolerance_pips: Tolerancia en pips
            
        Returns:
            Tuple: (is_near: bool, distance_pips: float)
        """
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return False, float('inf')
            
            current_price = float(tick.bid)
            
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return False, float('inf')
            
            point = symbol_info.point
            pip_value = point * 10 if symbol_info.digits == 5 else point * 1
            tolerance_price = tolerance_pips * pip_value
            
            distance = abs(current_price - level_price)
            distance_pips = distance / pip_value
            
            is_near = distance <= tolerance_price
            
            return is_near, distance_pips
            
        except Exception as e:
            self.logger.error(f"Error al verificar proximidad a nivel: {e}", exc_info=True)
            return False, float('inf')


# Funciones globales de conveniencia
def get_previous_daily_levels(symbol: str, lookback_days: int = 5) -> Optional[Dict]:
    """
    Obtiene los niveles HIGH y LOW de los días anteriores
    
    Args:
        symbol: Símbolo a analizar
        lookback_days: Número de días anteriores a revisar
        
    Returns:
        Dict con información de niveles diarios
    """
    detector = DailyLevelsDetector()
    return detector.get_previous_daily_levels(symbol, lookback_days)


def detect_daily_level_touch(symbol: str, lookback_days: int = 5, 
                             tolerance_pips: float = 1.0) -> Optional[Dict]:
    """
    Detecta si el precio actual está tocando o alcanzando un nivel diario previo
    
    Args:
        symbol: Símbolo a analizar
        lookback_days: Número de días anteriores a revisar
        tolerance_pips: Tolerancia en pips para considerar que el precio "tocó" el nivel
        
    Returns:
        Dict con información del nivel tocado o None
    """
    detector = DailyLevelsDetector()
    return detector.detect_daily_level_touch(symbol, lookback_days, tolerance_pips)


def detect_daily_high_take(symbol: str, lookback_days: int = 5, 
                           tolerance_pips: float = 1.0) -> Optional[Dict]:
    """
    Detecta específicamente si el precio está tomando un HIGH diario previo
    
    Args:
        symbol: Símbolo a analizar
        lookback_days: Número de días anteriores a revisar
        tolerance_pips: Tolerancia en pips
        
    Returns:
        Dict con información del HIGH tomado o None
    """
    detector = DailyLevelsDetector()
    return detector.detect_daily_high_take(symbol, lookback_days, tolerance_pips)


def detect_daily_low_take(symbol: str, lookback_days: int = 5, 
                          tolerance_pips: float = 1.0) -> Optional[Dict]:
    """
    Detecta específicamente si el precio está tomando un LOW diario previo
    
    Args:
        symbol: Símbolo a analizar
        lookback_days: Número de días anteriores a revisar
        tolerance_pips: Tolerancia en pips
        
    Returns:
        Dict con información del LOW tomado o None
    """
    detector = DailyLevelsDetector()
    return detector.detect_daily_low_take(symbol, lookback_days, tolerance_pips)


def get_yesterday_levels(symbol: str) -> Optional[Dict]:
    """
    Obtiene los niveles HIGH y LOW del día anterior (ayer)
    
    Args:
        symbol: Símbolo a analizar
        
    Returns:
        Dict con HIGH y LOW de ayer o None
    """
    detector = DailyLevelsDetector()
    return detector.get_yesterday_levels(symbol)


def is_price_near_daily_level(symbol: str, level_price: float, 
                              tolerance_pips: float = 5.0) -> Tuple[bool, float]:
    """
    Verifica si el precio actual está cerca de un nivel específico
    
    Args:
        symbol: Símbolo a analizar
        level_price: Precio del nivel a verificar
        tolerance_pips: Tolerancia en pips
        
    Returns:
        Tuple: (is_near: bool, distance_pips: float)
    """
    detector = DailyLevelsDetector()
    return detector.is_price_near_daily_level(symbol, level_price, tolerance_pips)

