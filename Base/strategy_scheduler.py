"""
Scheduler de Estrategias por Jornada
Gestiona el cambio de estrategias según horarios configurados
"""

import logging
from datetime import datetime, time
from typing import Dict, Optional, List
from pytz import timezone as tz


class StrategyScheduler:
    """Gestiona qué estrategia usar según la hora del día"""
    
    def __init__(self, config: Dict):
        """
        Inicializa el scheduler de estrategias
        
        Args:
            config: Configuración completa del bot
        """
        self.logger = logging.getLogger(__name__)
        self.config = config
        
        # Verificar si el sistema de jornadas está habilitado
        schedule_config = config.get('strategy_schedule', {})
        self.enabled = schedule_config.get('enabled', False)
        
        if not self.enabled:
            # Modo retrocompatible: usar estrategia única
            self.current_mode = 'single'
            self.single_strategy = config.get('strategy', {}).get('name', 'default')
            self.logger.info(f"Modo estrategia única: {self.single_strategy}")
            return
        
        # Modo jornadas: configurar sesiones
        self.current_mode = 'schedule'
        self.timezone_str = schedule_config.get('timezone', 'America/New_York')
        self.tz = tz(self.timezone_str)
        self.sessions = self._parse_sessions(schedule_config.get('sessions', []))
        
        if not self.sessions:
            self.logger.warning("No hay sesiones configuradas, usando estrategia única como fallback")
            self.enabled = False
            self.current_mode = 'single'
            self.single_strategy = config.get('strategy', {}).get('name', 'default')
            return
        
        # Validar sesiones
        self._validate_sessions()
        
        # Ordenar sesiones por hora de inicio
        self.sessions.sort(key=lambda s: s['start_time'])
        
        self.logger.info(f"Sistema de jornadas habilitado: {len(self.sessions)} sesión(es) configurada(s)")
        for i, session in enumerate(self.sessions, 1):
            self.logger.info(
                f"  {i}. {session['name']}: {session['start_time']} - {session['end_time']} → "
                f"Estrategia: {session['strategy']}"
            )
        
        # Trackear última sesión para detectar cambios
        self._last_session = None
        self._last_strategy = None
    
    def _parse_sessions(self, sessions_config: List[Dict]) -> List[Dict]:
        """
        Parsea y normaliza las sesiones de configuración
        
        Args:
            sessions_config: Lista de sesiones desde config.yaml
            
        Returns:
            Lista de sesiones normalizadas con objetos time
        """
        parsed_sessions = []
        
        for session in sessions_config:
            try:
                name = session.get('name', 'Sesión sin nombre')
                start_str = session.get('start_time', '09:00')
                end_str = session.get('end_time', '23:59')
                strategy = session.get('strategy', 'default')
                description = session.get('description', '')
                
                # Parsear horas
                start_time = self._parse_time(start_str)
                end_time = self._parse_time(end_str)
                
                parsed_sessions.append({
                    'name': name,
                    'start_time': start_time,
                    'end_time': end_time,
                    'start_time_str': start_str,
                    'end_time_str': end_str,
                    'strategy': strategy,
                    'description': description
                })
                
            except Exception as e:
                self.logger.error(f"Error al parsear sesión: {session} - {e}")
                continue
        
        return parsed_sessions
    
    def _parse_time(self, time_str: str) -> time:
        """Convierte string 'HH:MM' a objeto time"""
        try:
            hour, minute = map(int, time_str.split(':'))
            return time(hour, minute)
        except ValueError:
            self.logger.error(f"Formato de hora inválido: {time_str}. Usando 09:00 por defecto")
            return time(9, 0)
    
    def _validate_sessions(self):
        """Valida que las sesiones estén correctamente configuradas"""
        if not self.sessions:
            return
        
        # Verificar que no haya solapamientos
        for i, session1 in enumerate(self.sessions):
            for j, session2 in enumerate(self.sessions):
                if i >= j:
                    continue
                
                # Verificar solapamiento
                if self._sessions_overlap(session1, session2):
                    self.logger.warning(
                        f"⚠️  Solapamiento detectado entre sesiones: "
                        f"'{session1['name']}' y '{session2['name']}'"
                    )
        
        # Verificar que las estrategias referenciadas existan
        # Las estrategias se validarán cuando se use (en StrategyManager)
        # Por ahora solo logueamos advertencia
        for session in self.sessions:
            self.logger.debug(
                f"Sesión '{session['name']}' configurada con estrategia: '{session['strategy']}'"
            )
    
    def _sessions_overlap(self, session1: Dict, session2: Dict) -> bool:
        """Verifica si dos sesiones se solapan"""
        s1_start = session1['start_time']
        s1_end = session1['end_time']
        s2_start = session2['start_time']
        s2_end = session2['end_time']
        
        # Caso normal: no cruza medianoche
        if s1_start <= s1_end and s2_start <= s2_end:
            return not (s1_end <= s2_start or s2_end <= s1_start)
        
        # Caso con cruce de medianoche (complejo, simplificado)
        # Por ahora, asumimos que no hay solapamiento si cruza medianoche
        return False
    
    def get_current_strategy(self) -> str:
        """
        Obtiene la estrategia activa según la hora actual
        
        Returns:
            Nombre de la estrategia a usar
        """
        if not self.enabled or self.current_mode == 'single':
            return self.single_strategy
        
        # Obtener hora actual en la zona horaria configurada
        now_tz = datetime.now(self.tz)
        current_time = now_tz.time()
        
        # Buscar sesión activa
        active_session = self._find_active_session(current_time)
        
        if active_session:
            strategy = active_session['strategy']
            
            # Detectar cambio de sesión
            if self._last_session != active_session['name']:
                if self._last_session is not None:
                    self.logger.info(
                        f"🔄 Cambio de sesión: '{self._last_session}' → '{active_session['name']}' | "
                        f"Estrategia: '{self._last_strategy}' → '{strategy}'"
                    )
                else:
                    self.logger.info(
                        f"📅 Sesión activa: '{active_session['name']}' | Estrategia: '{strategy}'"
                    )
                
                self._last_session = active_session['name']
                self._last_strategy = strategy
            
            return strategy
        
        # No hay sesión activa - usar fallback
        self.logger.warning(
            f"⚠️  No hay sesión activa para la hora {current_time.strftime('%H:%M')}. "
            f"Usando estrategia por defecto"
        )
        return self.single_strategy or 'default'
    
    def _find_active_session(self, current_time: time) -> Optional[Dict]:
        """
        Encuentra la sesión activa para la hora actual
        
        Args:
            current_time: Hora actual (objeto time)
            
        Returns:
            Sesión activa o None si no hay ninguna
        """
        for session in self.sessions:
            start = session['start_time']
            end = session['end_time']
            
            # Caso normal: no cruza medianoche
            if start <= end:
                if start <= current_time <= end:
                    return session
            else:
                # Caso que cruza medianoche (ej: 22:00 - 02:00)
                if current_time >= start or current_time <= end:
                    return session
        
        return None
    
    def get_current_session_info(self) -> Optional[Dict]:
        """
        Obtiene información de la sesión actual
        
        Returns:
            Dict con información de la sesión actual o None
        """
        if not self.enabled or self.current_mode == 'single':
            return None
        
        now_tz = datetime.now(self.tz)
        current_time = now_tz.time()
        active_session = self._find_active_session(current_time)
        
        if active_session:
            return {
                'name': active_session['name'],
                'strategy': active_session['strategy'],
                'start_time': active_session['start_time_str'],
                'end_time': active_session['end_time_str'],
                'description': active_session['description']
            }
        
        return None
    
    def get_next_session_change(self) -> Optional[datetime]:
        """
        Obtiene cuándo cambiará la próxima sesión
        
        Returns:
            datetime de la próxima transición o None
        """
        if not self.enabled or self.current_mode == 'single':
            return None
        
        now_tz = datetime.now(self.tz)
        current_time = now_tz.time()
        
        # Encontrar próxima transición
        next_change = None
        
        for session in self.sessions:
            end_time = session['end_time']
            
            # Calcular datetime de fin de sesión
            if end_time > current_time:
                # Termina hoy
                end_datetime = self.tz.localize(
                    datetime.combine(now_tz.date(), end_time)
                )
            else:
                # Termina mañana
                from datetime import timedelta
                end_datetime = self.tz.localize(
                    datetime.combine(now_tz.date() + timedelta(days=1), end_time)
                )
            
            if next_change is None or end_datetime < next_change:
                next_change = end_datetime
        
        return next_change

