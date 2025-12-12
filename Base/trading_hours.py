"""
Gestor de Horarios Operativos
Maneja la lógica de horarios de trading
"""

import logging
from datetime import datetime, time, timedelta
from pytz import timezone as tz
from typing import Dict, Optional, Tuple
from Base.news_checker import validate_trading_day


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
        
        Valida:
        1. Si es día operativo (lunes a viernes, no feriados)
        2. Si estamos en el rango de horas configurado
        
        Returns:
            True si estamos en horario operativo, False en caso contrario
        """
        if not self.enabled:
            return True  # Si está deshabilitado, siempre permite trading
        
        # Obtener hora actual en la zona horaria configurada
        now_tz = datetime.now(self.tz)
        
        # PRIMERO: Verificar si es día operativo (lunes a viernes, no feriados)
        is_trading_day, day_reason, holidays = validate_trading_day(now_tz)
        if not is_trading_day:
            # No es día operativo (fin de semana o feriado)
            return False
        
        # SEGUNDO: Verificar si la hora actual está entre start_time y end_time
        current_time = now_tz.time()
        if self.start_time <= self.end_time:
            # Horario normal (ej: 09:00 - 13:00)
            is_trading = self.start_time <= current_time <= self.end_time
        else:
            # Horario que cruza medianoche (ej: 22:00 - 02:00)
            is_trading = current_time >= self.start_time or current_time <= self.end_time
        
        return is_trading
    
    def is_trading_day(self) -> Tuple[bool, str, list]:
        """
        Verifica si el día actual es operativo (lunes a viernes, no feriados)
        
        Returns:
            tuple: (is_trading_day: bool, reason: str, holidays: List[Dict])
        """
        now_tz = datetime.now(self.tz)
        return validate_trading_day(now_tz)
    
    def get_next_trading_time(self) -> datetime:
        """
        Obtiene la próxima hora de inicio de trading (considerando días operativos)
        
        Busca el próximo día operativo (lunes a viernes, no feriados) y hora de inicio.
        
        Returns:
            datetime de la próxima hora de inicio en un día operativo
        """
        now_tz = datetime.now(self.tz)
        current_time = now_tz.time()
        
        # Verificar si hoy es día operativo y si ya pasó la hora de inicio
        is_trading_day_today, _, _ = validate_trading_day(now_tz)
        
        # Si hoy es día operativo y aún no ha pasado la hora de inicio, usar hoy
        if is_trading_day_today and current_time < self.start_time:
            return self.tz.localize(datetime.combine(now_tz.date(), self.start_time))
        
        # Si hoy es día operativo pero ya pasó la hora, o si no es día operativo,
        # buscar el próximo día operativo
        next_date = now_tz.date()
        max_days_ahead = 10  # Límite de seguridad para evitar bucle infinito
        
        for _ in range(max_days_ahead):
            next_date = next_date + timedelta(days=1)
            next_datetime = self.tz.localize(datetime.combine(next_date, self.start_time))
            is_trading_day_next, _, _ = validate_trading_day(next_datetime)
            
            if is_trading_day_next:
                return next_datetime
        
        # Si no se encontró día operativo en los próximos 10 días, retornar mañana como fallback
        self.logger.warning("No se encontró día operativo en los próximos 10 días, usando mañana como fallback")
        next_date = now_tz.date() + timedelta(days=1)
        return self.tz.localize(datetime.combine(next_date, self.start_time))
    
    def get_time_until_trading(self) -> str:
        """
        Obtiene tiempo restante hasta el próximo horario operativo
        
        Returns:
            String con tiempo restante formateado o razón por la que no se puede operar
        """
        if self.is_trading_time():
            return "En horario operativo"
        
        # Verificar si es día operativo
        is_trading_day, day_reason, holidays = self.is_trading_day()
        
        if not is_trading_day:
            # No es día operativo - mostrar razón y próximo día operativo
            next_trading = self.get_next_trading_time()
            now_tz = datetime.now(self.tz)
            delta = next_trading - now_tz
            
            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            if days > 0:
                return f"{day_reason} - Próximo día operativo en {days}d {hours}h {minutes}m"
            else:
                return f"{day_reason} - Próximo día operativo en {hours}h {minutes}m"
        
        # Es día operativo pero fuera de horario
        next_trading = self.get_next_trading_time()
        now_tz = datetime.now(self.tz)
        delta = next_trading - now_tz
        
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        return f"{hours}h {minutes}m"

