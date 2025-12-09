"""
Gestor de Horarios Operativos
Maneja la lógica de horarios de trading
"""

import logging
from datetime import datetime, time
from pytz import timezone as tz
from typing import Dict


class TradingHoursManager:
    """Gestiona los horarios operativos del bot"""
    
    def __init__(self, config: Dict):
        """
        Inicializa el gestor de horarios
        
        Args:
            config: Configuración de horarios desde config.yaml
        """
        self.logger = logging.getLogger(__name__)
        self.enabled = config.get('enabled', True)
        self.timezone_str = config.get('timezone', 'America/New_York')
        self.tz = tz(self.timezone_str)
        
        # Parsear horas de inicio y fin
        start_str = config.get('start_time', '09:00')
        end_str = config.get('end_time', '13:00')
        
        self.start_time = self._parse_time(start_str)
        self.end_time = self._parse_time(end_str)
        
        self.logger.info(f"Horario operativo configurado: {start_str} - {end_str} ({self.timezone_str})")
    
    def _parse_time(self, time_str: str) -> time:
        """Convierte string 'HH:MM' a objeto time"""
        try:
            hour, minute = map(int, time_str.split(':'))
            return time(hour, minute)
        except ValueError:
            self.logger.error(f"Formato de hora inválido: {time_str}. Usando 09:00 por defecto")
            return time(9, 0)
    
    def is_trading_time(self) -> bool:
        """
        Verifica si estamos en horario operativo
        
        Returns:
            True si estamos en horario operativo, False en caso contrario
        """
        if not self.enabled:
            return True  # Si está deshabilitado, siempre permite trading
        
        # Obtener hora actual en la zona horaria configurada
        now_tz = datetime.now(self.tz)
        current_time = now_tz.time()
        
        # Verificar si la hora actual está entre start_time y end_time
        if self.start_time <= self.end_time:
            # Horario normal (ej: 09:00 - 13:00)
            is_trading = self.start_time <= current_time <= self.end_time
        else:
            # Horario que cruza medianoche (ej: 22:00 - 02:00)
            is_trading = current_time >= self.start_time or current_time <= self.end_time
        
        return is_trading
    
    def get_next_trading_time(self) -> datetime:
        """
        Obtiene la próxima hora de inicio de trading
        
        Returns:
            datetime de la próxima hora de inicio
        """
        now_tz = datetime.now(self.tz)
        current_time = now_tz.time()
        
        # Si ya pasó la hora de inicio hoy, usar mañana
        if current_time > self.start_time:
            next_date = now_tz.date()
            # Si el horario termina después de medianoche y ya pasó, usar hoy
            if self.start_time > self.end_time and current_time <= self.end_time:
                next_date = now_tz.date()
            else:
                from datetime import timedelta
                next_date = (now_tz + timedelta(days=1)).date()
        else:
            next_date = now_tz.date()
        
        next_datetime = self.tz.localize(datetime.combine(next_date, self.start_time))
        return next_datetime
    
    def get_time_until_trading(self) -> str:
        """
        Obtiene tiempo restante hasta el próximo horario operativo
        
        Returns:
            String con tiempo restante formateado
        """
        if self.is_trading_time():
            return "En horario operativo"
        
        next_trading = self.get_next_trading_time()
        now_tz = datetime.now(self.tz)
        delta = next_trading - now_tz
        
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        return f"{hours}h {minutes}m"

