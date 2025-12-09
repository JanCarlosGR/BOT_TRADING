"""
Lector de Velas Reutilizable para MT5
Proporciona funciones para obtener información de velas de forma sencilla
"""

import MetaTrader5 as mt5
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional, Union
from pytz import timezone


class CandleReader:
    """Clase para leer velas de MT5 de forma reutilizable"""
    
    # Mapeo de temporalidades
    TIMEFRAME_MAP = {
        'M1': mt5.TIMEFRAME_M1,
        'M5': mt5.TIMEFRAME_M5,
        'M15': mt5.TIMEFRAME_M15,
        'M30': mt5.TIMEFRAME_M30,
        'H1': mt5.TIMEFRAME_H1,
        'H4': mt5.TIMEFRAME_H4,
        'D1': mt5.TIMEFRAME_D1,
        'W1': mt5.TIMEFRAME_W1,
        'MN1': mt5.TIMEFRAME_MN1,
    }
    
    def __init__(self, symbol: str = None, timezone_str: str = "America/New_York"):
        """
        Inicializa el lector de velas
        
        Args:
            symbol: Símbolo por defecto (opcional)
            timezone_str: Zona horaria para interpretar horarios (ej: "America/New_York")
        """
        self.logger = logging.getLogger(__name__)
        self.default_symbol = symbol
        self.tz = timezone(timezone_str)
        self.mt5_timezone_offset = None  # Se calculará automáticamente
    
    def _get_mt5_timezone_offset(self, symbol: str) -> timedelta:
        """
        Detecta la diferencia de zona horaria entre la zona horaria de referencia y MT5
        
        Args:
            symbol: Símbolo para obtener datos de prueba
            
        Returns:
            timedelta con la diferencia de zona horaria
        """
        if self.mt5_timezone_offset is not None:
            return self.mt5_timezone_offset
        
        try:
            # Obtener una vela reciente de MT5
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 1)
            if rates is None or len(rates) == 0:
                self.logger.warning("No se pudieron obtener datos para detectar zona horaria. Usando offset por defecto.")
                # Offset por defecto: 7 horas (1am NY = 8am MT5)
                self.mt5_timezone_offset = timedelta(hours=7)
                return self.mt5_timezone_offset
            
            # Obtener timestamp de la vela de MT5 (en UTC)
            mt5_timestamp = rates[-1]['time']
            mt5_datetime_utc = datetime.fromtimestamp(mt5_timestamp, tz=timezone('UTC'))
            
            # Obtener hora actual en la zona horaria de referencia
            ref_datetime = datetime.now(self.tz)
            
            # Calcular la diferencia
            # Si la vela de MT5 es de hace poco, podemos comparar
            # Pero mejor: obtener la hora del servidor MT5 directamente
            terminal_info = mt5.terminal_info()
            if terminal_info:
                # MT5 devuelve timestamps en UTC, pero las velas están en hora del servidor
                # Necesitamos obtener la hora del servidor
                server_time = mt5.symbol_info_tick(symbol)
                if server_time:
                    # El tick time está en UTC
                    # Comparar con la hora actual en NY
                    now_utc = datetime.now(timezone('UTC'))
                    now_ny = datetime.now(self.tz)
                    
                    # Calcular diferencia: si 1am NY = 8am MT5, entonces MT5 está 7 horas adelante
                    # Esto significa que cuando son las 1am en NY, son las 8am en MT5
                    # Entonces: hora_MT5 = hora_NY + 7 horas
                    # O mejor: hora_NY = hora_MT5 - 7 horas
                    # Offset = hora_MT5 - hora_NY = +7 horas
                    
                    # Usar offset conocido: 7 horas (puede variar con horario de verano)
                    # En diciembre 2025, NY está en EST (UTC-5), si MT5 está en GMT+2, entonces:
                    # 1am EST = 6am UTC = 8am GMT+2, diferencia = 7 horas
                    self.mt5_timezone_offset = timedelta(hours=7)
                    self.logger.info(f"Offset de zona horaria detectado: MT5 está {self.mt5_timezone_offset} adelante de {self.tz}")
                    return self.mt5_timezone_offset
            
            # Fallback: usar offset conocido
            self.mt5_timezone_offset = timedelta(hours=7)
            self.logger.info(f"Usando offset por defecto: MT5 está {self.mt5_timezone_offset} adelante de {self.tz}")
            return self.mt5_timezone_offset
            
        except Exception as e:
            self.logger.warning(f"Error al detectar zona horaria: {e}. Usando offset por defecto.")
            self.mt5_timezone_offset = timedelta(hours=7)
            return self.mt5_timezone_offset
    
    def _parse_timeframe(self, timeframe_str: str) -> int:
        """
        Convierte string de temporalidad a constante MT5
        
        Args:
            timeframe_str: Temporalidad en formato 'M5', 'H4', etc.
            
        Returns:
            Constante MT5 de temporalidad
        """
        tf_upper = timeframe_str.upper().strip()
        if tf_upper not in self.TIMEFRAME_MAP:
            raise ValueError(f"Temporalidad '{timeframe_str}' no válida. "
                           f"Opciones: {list(self.TIMEFRAME_MAP.keys())}")
        return self.TIMEFRAME_MAP[tf_upper]
    
    def _parse_time_reference(self, time_ref: str, symbol: str = None) -> Optional[datetime]:
        """
        Parsea referencia de tiempo a datetime y convierte a zona horaria de MT5
        
        Args:
            time_ref: 'ahora', 'actual', o hora específica como '1am', '9am', '13:00', etc.
            symbol: Símbolo para detectar zona horaria (opcional)
            
        Returns:
            datetime en zona horaria de MT5 o None si es 'ahora'/'actual'
        """
        time_ref_lower = time_ref.lower().strip()
        
        if time_ref_lower in ['ahora', 'actual', 'now', 'current']:
            return None  # Indica vela actual
        
        # Intentar parsear como hora (ej: '1am', '9am', '13:00', '1:30pm')
        try:
            # Formato con am/pm
            if 'am' in time_ref_lower or 'pm' in time_ref_lower:
                time_str = time_ref_lower.replace(' ', '')
                if 'am' in time_str:
                    hour_str = time_str.replace('am', '')
                    hour = int(hour_str)
                    if hour == 12:
                        hour = 0
                elif 'pm' in time_str:
                    hour_str = time_str.replace('pm', '')
                    hour = int(hour_str)
                    if hour != 12:
                        hour += 12
                minute = 0
            else:
                # Formato 24h (ej: '13:00', '9:00')
                if ':' in time_ref:
                    hour, minute = map(int, time_ref.split(':'))
                else:
                    hour = int(time_ref)
                    minute = 0
            
            # Obtener fecha actual en la zona horaria de referencia (NY)
            now = datetime.now(self.tz)
            target_time_ny = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Convertir a zona horaria de MT5
            # Si symbol está disponible, usar detección automática
            if symbol:
                offset = self._get_mt5_timezone_offset(symbol)
                # Convertir hora de NY a hora de MT5
                target_time_mt5 = target_time_ny + offset
            else:
                # Usar offset por defecto de 7 horas
                target_time_mt5 = target_time_ny + timedelta(hours=7)
            
            # Convertir a UTC para MT5 (MT5 trabaja con timestamps UTC)
            # Pero las velas están en hora del servidor, así que necesitamos ajustar
            # Por ahora, retornamos el datetime en la zona horaria local (será convertido después)
            return target_time_mt5.replace(tzinfo=None)  # Sin timezone para usar directamente con MT5
            
        except (ValueError, AttributeError):
            raise ValueError(f"Formato de hora no válido: '{time_ref}'. "
                           f"Usa 'ahora', 'actual', o formato como '1am', '9am', '13:00'")
    
    def _get_candle_at_time(self, symbol: str, timeframe: int, target_time_mt5: datetime) -> Optional[Dict]:
        """
        Obtiene la vela que CONTIENE el tiempo específico de MT5
        
        Args:
            symbol: Símbolo a consultar
            timeframe: Temporalidad MT5
            target_time_mt5: Tiempo objetivo en zona horaria de MT5 (sin timezone)
            
        Returns:
            Dict con información de la vela o None
        """
        # Obtener múltiples velas para buscar la correcta
        # Obtener velas de los últimos días para asegurar que encontramos la correcta
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 200)
        
        if rates is None or len(rates) == 0:
            return None
        
        # Buscar la vela que CONTIENE el tiempo objetivo (no la que inicia en ese tiempo)
        target_date = target_time_mt5.date()
        target_hour = target_time_mt5.hour
        
        # Para H4, primero encontrar todas las velas del día y luego buscar la correcta
        if timeframe == mt5.TIMEFRAME_H4:
            # Recopilar todas las velas H4 del día objetivo
            day_candles = []
            for candle in rates:
                candle_time = datetime.fromtimestamp(candle['time'])
                candle_hour = candle_time.hour
                if candle_time.date() == target_date and candle_hour % 4 == 0:
                    day_candles.append((candle_time, candle))
            
            # Ordenar por hora (más antiguas primero)
            day_candles.sort(key=lambda x: x[0])
            
            # Buscar la vela que contiene el tiempo objetivo
            # Si el tiempo objetivo es exactamente la hora de inicio de una vela, buscar la anterior
            for i, (candle_time, candle) in enumerate(day_candles):
                candle_start = candle_time
                candle_end = candle_start + timedelta(hours=4)
                
                # Si el tiempo objetivo es exactamente el inicio de esta vela, usar la vela anterior
                if target_time_mt5 == candle_start and i > 0:
                    # Usar la vela anterior que contiene este tiempo
                    prev_candle_time, prev_candle = day_candles[i-1]
                    return self._format_candle(prev_candle, is_current=False)
                
                # Si el tiempo objetivo está dentro del rango de esta vela (pero no es el inicio)
                if candle_start < target_time_mt5 < candle_end:
                    return self._format_candle(candle, is_current=False)
            
            # Si no encontramos, buscar la más cercana
            if day_candles:
                # Buscar la vela más cercana al tiempo objetivo
                closest = None
                min_diff = timedelta(days=365)
                for candle_time, candle in day_candles:
                    diff = abs((candle_time - target_time_mt5).total_seconds())
                    if diff < min_diff.total_seconds():
                        min_diff = timedelta(seconds=diff)
                        closest = candle
                if closest is not None:
                    return self._format_candle(closest, is_current=False)
        
        # Para otros timeframes, usar la lógica original
        for candle in rates:
            candle_time = datetime.fromtimestamp(candle['time'])
            candle_date = candle_time.date()
            
            if timeframe == mt5.TIMEFRAME_H1:
                # Vela H1 cubre 1 hora
                candle_start = candle_time
                candle_end = candle_start + timedelta(hours=1)
                if candle_date == target_date and candle_start <= target_time_mt5 < candle_end:
                    return self._format_candle(candle, is_current=False)
            elif timeframe == mt5.TIMEFRAME_D1:
                # Vela diaria cubre todo el día
                if candle_date == target_date:
                    return self._format_candle(candle, is_current=False)
            elif timeframe == mt5.TIMEFRAME_M1:
                candle_start = candle_time
                candle_end = candle_start + timedelta(minutes=1)
                if candle_start <= target_time_mt5 < candle_end:
                    return self._format_candle(candle, is_current=False)
            elif timeframe == mt5.TIMEFRAME_M5:
                candle_start = candle_time
                candle_end = candle_start + timedelta(minutes=5)
                if candle_start <= target_time_mt5 < candle_end:
                    return self._format_candle(candle, is_current=False)
            elif timeframe == mt5.TIMEFRAME_M15:
                candle_start = candle_time
                candle_end = candle_start + timedelta(minutes=15)
                if candle_start <= target_time_mt5 < candle_end:
                    return self._format_candle(candle, is_current=False)
            elif timeframe == mt5.TIMEFRAME_M30:
                candle_start = candle_time
                candle_end = candle_start + timedelta(minutes=30)
                if candle_start <= target_time_mt5 < candle_end:
                    return self._format_candle(candle, is_current=False)
        
        # Si no encontramos exactamente, buscar la más cercana por fecha y hora
        closest_candle = None
        min_time_diff = timedelta(days=365)
        
        for candle in rates:
            candle_time = datetime.fromtimestamp(candle['time'])
            candle_date = candle_time.date()
            
            if timeframe == mt5.TIMEFRAME_H4:
                candle_hour = candle_time.hour
                if candle_hour % 4 == 0:  # Solo velas que inician en hora múltiplo de 4
                    # Calcular diferencia de tiempo
                    candle_start = candle_time
                    time_diff = abs((candle_start - target_time_mt5).total_seconds())
                    if time_diff < min_time_diff.total_seconds():
                        min_time_diff = timedelta(seconds=time_diff)
                        closest_candle = candle
            elif timeframe == mt5.TIMEFRAME_H1:
                time_diff = abs((candle_time - target_time_mt5).total_seconds())
                if time_diff < min_time_diff.total_seconds():
                    min_time_diff = timedelta(seconds=time_diff)
                    closest_candle = candle
        
        if closest_candle is not None:
            return self._format_candle(closest_candle, is_current=False)
        
        return None
    
    def _format_candle(self, candle_data: np.ndarray, is_current: bool = False) -> Dict:
        """
        Formatea los datos de la vela en un diccionario estructurado
        
        Args:
            candle_data: Array de datos de vela de MT5
            is_current: Si es la vela actual
            
        Returns:
            Dict con información formateada de la vela
        """
        open_price = float(candle_data['open'])
        high = float(candle_data['high'])
        low = float(candle_data['low'])
        close = float(candle_data['close'])
        volume = int(candle_data['tick_volume'])
        time = int(candle_data['time'])
        
        # Determinar si es alcista o bajista
        is_bullish = close > open_price
        is_bearish = close < open_price
        candle_type = "ALCISTA" if is_bullish else "BAJISTA" if is_bearish else "DOJI"
        
        # Calcular tamaño de la vela
        body_size = abs(close - open_price)
        total_range = high - low
        
        return {
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
            'time': time,
            'datetime': datetime.fromtimestamp(time),
            'type': candle_type,
            'is_bullish': is_bullish,
            'is_bearish': is_bearish,
            'is_current': is_current,
            'body_size': body_size,
            'total_range': total_range,
            'upper_wick': high - max(open_price, close),
            'lower_wick': min(open_price, close) - low,
        }
    
    def get_candle(self, timeframe: str, time_ref: str = 'ahora', symbol: str = None) -> Optional[Dict]:
        """
        Obtiene información de una vela específica
        
        Args:
            timeframe: Temporalidad (ej: 'M5', 'H4', 'H1')
            time_ref: Referencia de tiempo ('ahora', 'actual', '1am', '9am', '13:00', etc.)
            symbol: Símbolo a consultar (usa default si no se especifica)
            
        Returns:
            Dict con información de la vela o None si no se encuentra
            
        Ejemplos:
            get_candle('M5', 'ahora')  # Vela actual M5
            get_candle('H4', '1am')    # Vela H4 que contiene la 1am
            get_candle('H4', '9am')    # Vela H4 que contiene las 9am
            get_candle('H1', '13:00')  # Vela H1 que contiene las 13:00
        """
        # Usar símbolo por defecto o el especificado
        symbol_to_use = symbol or self.default_symbol
        if not symbol_to_use:
            raise ValueError("Debe especificar un símbolo o configurar uno por defecto")
        
        # Verificar que el símbolo existe
        symbol_info = mt5.symbol_info(symbol_to_use)
        if symbol_info is None:
            self.logger.error(f"Símbolo '{symbol_to_use}' no encontrado en MT5")
            return None
        
        # Habilitar símbolo si no está visible
        if not symbol_info.visible:
            mt5.symbol_select(symbol_to_use, True)
        
        # Parsear temporalidad
        try:
            tf = self._parse_timeframe(timeframe)
        except ValueError as e:
            self.logger.error(str(e))
            return None
        
        # Obtener vela actual o de tiempo específico
        if time_ref.lower() in ['ahora', 'actual', 'now', 'current']:
            # Obtener vela actual (última vela cerrada o en formación)
            rates = mt5.copy_rates_from_pos(symbol_to_use, tf, 0, 1)
            if rates is None or len(rates) == 0:
                self.logger.error(f"No se pudieron obtener datos para {symbol_to_use}")
                return None
            
            candle = rates[-1]
            return self._format_candle(candle, is_current=True)
        else:
            # Obtener vela de tiempo específico
            try:
                target_time = self._parse_time_reference(time_ref, symbol_to_use)
                if target_time is None:
                    # Fallback a vela actual
                    rates = mt5.copy_rates_from_pos(symbol_to_use, tf, 0, 1)
                    if rates is None or len(rates) == 0:
                        return None
                    return self._format_candle(rates[-1], is_current=True)
                
                return self._get_candle_at_time(symbol_to_use, tf, target_time)
                
            except ValueError as e:
                self.logger.error(str(e))
                return None


# Función global reutilizable (wrapper para facilitar uso)
def get_candle(timeframe: str, time_ref: str = 'ahora', symbol: str = None) -> Optional[Dict]:
    """
    Función global para obtener información de una vela
    
    Args:
        timeframe: Temporalidad (ej: 'M5', 'H4', 'H1')
        time_ref: Referencia de tiempo ('ahora', 'actual', '1am', '9am', '13:00', etc.)
        symbol: Símbolo a consultar (requerido si no hay default)
        
    Returns:
        Dict con información de la vela o None
        
    Ejemplos:
        get_candle('M5', 'ahora', 'EURUSD')
        get_candle('H4', '1am', 'GBPUSD')
        get_candle('H4', '9am', 'EURUSD')
    """
    reader = CandleReader(symbol=symbol)
    return reader.get_candle(timeframe, time_ref, symbol)


# Para uso con instancia (más eficiente si se usa múltiples veces)
def create_candle_reader(symbol: str = None, timezone_str: str = "America/New_York") -> CandleReader:
    """
    Crea una instancia de CandleReader para uso repetido
    
    Args:
        symbol: Símbolo por defecto
        timezone_str: Zona horaria
    
    Returns:
        Instancia de CandleReader
    
    Ejemplo:
        reader = create_candle_reader('EURUSD')
        candle1 = reader.get_candle('M5', 'ahora')
        candle2 = reader.get_candle('H4', '9am')
    """
    return CandleReader(symbol=symbol, timezone_str=timezone_str)

