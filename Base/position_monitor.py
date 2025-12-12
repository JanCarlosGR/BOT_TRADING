"""
Monitor de Posiciones Abiertas
Monitorea y gestiona posiciones abiertas en MT5 con:
- Trailing Stop Loss (70% -> mover SL a 50%)
- Cierre automático antes del cierre del día (4:50 PM NY)
"""

import logging
import time as time_module
from datetime import datetime, time
from typing import List, Dict, Optional, Tuple
import MetaTrader5 as mt5
from pytz import timezone as tz
from Base.order_executor import OrderExecutor
from Base.database import DatabaseManager


class PositionMonitor:
    """Monitor para gestionar posiciones abiertas con trailing stop y cierre automático"""
    
    def __init__(self, config: Dict):
        """
        Inicializa el monitor de posiciones
        
        Args:
            config: Configuración del bot (incluye position_monitoring, trading_hours)
        """
        self.logger = logging.getLogger(__name__)
        self.executor = OrderExecutor()
        self.config = config
        # Inicializar DatabaseManager para actualizar estado de órdenes
        self.db_manager = DatabaseManager(config)
        
        # Cargar configuración de monitoreo de posiciones
        monitoring_config = config.get('position_monitoring', {})
        self.monitoring_enabled = monitoring_config.get('enabled', True)
        
        # Configuración de trailing stop
        trailing_config = monitoring_config.get('trailing_stop', {})
        self.trailing_enabled = trailing_config.get('enabled', True)
        self.trailing_trigger_percent = trailing_config.get('trigger_percent', 0.70)  # 70% del movimiento por defecto
        self.trailing_sl_percent = trailing_config.get('sl_percent', 0.50)  # 50% por defecto
        
        # Configuración de cierre automático
        auto_close_config = monitoring_config.get('auto_close', {})
        self.auto_close_enabled = auto_close_config.get('enabled', True)
        self.close_time_str = auto_close_config.get('time', '16:50')  # 4:50 PM por defecto
        self.close_timezone_str = auto_close_config.get('timezone', 'America/New_York')
        self.close_tz = tz(self.close_timezone_str)
        
        # Parsear hora de cierre
        try:
            hour, minute = map(int, self.close_time_str.split(':'))
            self.close_time = time(hour, minute)
        except (ValueError, AttributeError) as e:
            self.logger.error(f"Formato de hora de cierre inválido: {self.close_time_str}. Usando 16:50 por defecto - Error: {e}")
            self.close_time = time(16, 50)
        
        # Cache de cierre diario (para evitar cerrar múltiples veces el mismo día)
        self.daily_close_cache = set()
        
        # Log de configuración
        if self.monitoring_enabled:
            log_msg = f"PositionMonitor inicializado"
            if self.trailing_enabled:
                log_msg += f" - Trailing Stop: {self.trailing_trigger_percent*100:.0f}% → {self.trailing_sl_percent*100:.0f}%"
            if self.auto_close_enabled:
                log_msg += f" - Cierre automático: {self.close_time_str} ({self.close_timezone_str})"
            self.logger.info(log_msg)
        else:
            self.logger.info("PositionMonitor deshabilitado en configuración")
    
    def monitor_positions(self) -> Dict:
        """
        Monitorea todas las posiciones abiertas y aplica las reglas de gestión
        
        Returns:
            Dict con resumen de acciones realizadas
        """
        try:
            # Verificar si el monitoreo está habilitado
            if not self.monitoring_enabled:
                return {
                    'success': True,
                    'message': 'Monitoreo deshabilitado en configuración',
                    'actions': []
                }
            
            # Verificar conexión MT5
            if not self.executor._verify_mt5_connection():
                return {
                    'success': False,
                    'message': 'MT5 no está conectado',
                    'actions': []
                }
            
            # Obtener todas las posiciones abiertas desde MT5
            positions = self.executor.get_positions()
            
            # Sincronizar BD con MT5 (marcar como cerradas las órdenes que ya no están abiertas en MT5)
            # IMPORTANTE: Hacer esto ANTES de verificar cierre automático para asegurar sincronización
            if self.db_manager.enabled:
                sync_result = self.db_manager.sync_orders_with_mt5(positions)
                if sync_result.get('closed', 0) > 0:
                    self.logger.info(f"🔄 Sincronización BD-MT5: {sync_result['closed']} orden(es) marcada(s) como cerrada(s)")
            
            # Si después de sincronizar no hay posiciones, retornar
            if not positions:
                # Actualizar lista de posiciones después de sincronización
                positions = self.executor.get_positions()
            
            if not positions:
                return {
                    'success': True,
                    'message': 'No hay posiciones abiertas',
                    'actions': [],
                    'open_count': 0
                }
            
            actions = []
            
            # 1. Verificar cierre automático por hora
            if self.auto_close_enabled:
                close_action = self._check_auto_close_time(positions)
                if close_action:
                    actions.append(close_action)
                    # Si hay posiciones pendientes, continuar monitoreo (no retornar aún)
                    # Actualizar lista de posiciones después de intentar cerrar
                    remaining_positions = self.executor.get_positions()
                    if not remaining_positions:
                        # Todas las posiciones fueron cerradas exitosamente
                        return {
                            'success': True,
                            'message': f'Todas las posiciones cerradas por hora de cierre',
                            'actions': actions,
                            'open_count': 0
                        }
                    # Aún hay posiciones pendientes - continuar con trailing stop y seguir intentando cerrar
                    positions = remaining_positions
            
            # 2. Aplicar trailing stop loss a cada posición
            if self.trailing_enabled:
                for position in positions:
                    trailing_action = self._check_and_apply_trailing_stop(position)
                    if trailing_action:
                        actions.append(trailing_action)
            
            return {
                'success': True,
                'message': f'Monitoreo completado - {len(positions)} posición(es) revisada(s)',
                'actions': actions,
                'open_count': len(positions)
            }
            
        except Exception as e:
            self.logger.error(f"Error en monitoreo de posiciones: {e}", exc_info=True)
            return {
                'success': False,
                'message': str(e),
                'actions': []
            }
    
    def _check_and_apply_trailing_stop(self, position: Dict) -> Optional[Dict]:
        """
        Verifica si debe aplicarse trailing stop loss y lo aplica si corresponde
        
        Args:
            position: Dict con información de la posición
            
        Returns:
            Dict con información de la acción realizada o None
        """
        try:
            ticket = position['ticket']
            symbol = position['symbol']
            position_type = position['type']
            entry_price = position['price_open']
            current_price = position['price_current']
            current_sl = position.get('price_stop_loss', 0) or 0
            take_profit = position.get('price_take_profit', 0) or 0
            
            # Necesitamos TP para calcular el movimiento
            if take_profit <= 0:
                # Si no hay TP, no podemos aplicar trailing stop
                return None
            
            # Calcular movimiento total esperado
            if position_type == 'BUY':
                # Compra: movimiento desde entry hacia arriba hasta TP
                total_movement = take_profit - entry_price
                current_movement = current_price - entry_price
            else:  # SELL
                # Venta: movimiento desde entry hacia abajo hasta TP
                total_movement = entry_price - take_profit
                current_movement = entry_price - current_price
            
            if total_movement <= 0:
                # TP está en dirección incorrecta o igual al entry
                return None
            
            # Calcular porcentaje de progreso
            progress_percent = current_movement / total_movement
            
            # Verificar si alcanzó el 70% del movimiento
            if progress_percent < self.trailing_trigger_percent:
                return None  # Aún no alcanza el 70%
            
            # Calcular nuevo SL a 50% del movimiento
            if position_type == 'BUY':
                # SL a 50% del movimiento desde entry
                target_sl = entry_price + (total_movement * self.trailing_sl_percent)
                # El nuevo SL debe estar por encima del SL actual (si existe) y por debajo del precio actual
                # Si hay un SL actual, el nuevo debe estar por encima para proteger más ganancias
                if current_sl > 0 and target_sl <= current_sl:
                    # Ya se movió el SL anteriormente, solo actualizar si el nuevo es mejor
                    # Verificar si el precio actual permite un SL mejor
                    if current_price <= current_sl:
                        # El precio retrocedió, no podemos mejorar el SL
                        return None
                    # Solo actualizar si el nuevo SL está más cerca del precio actual pero aún es mejor que el actual
                    if target_sl <= current_sl:
                        return None
            else:  # SELL
                # SL a 50% del movimiento desde entry
                target_sl = entry_price - (total_movement * self.trailing_sl_percent)
                # El nuevo SL debe estar por debajo del SL actual (si existe) y por encima del precio actual
                # Si hay un SL actual, el nuevo debe estar por debajo para proteger más ganancias
                if current_sl > 0 and target_sl >= current_sl:
                    # Ya se movió el SL anteriormente, solo actualizar si el nuevo es mejor
                    # Verificar si el precio actual permite un SL mejor
                    if current_price >= current_sl:
                        # El precio retrocedió, no podemos mejorar el SL
                        return None
                    # Solo actualizar si el nuevo SL está más cerca del precio actual pero aún es mejor que el actual
                    if target_sl >= current_sl:
                        return None
            
            # Verificar que el nuevo SL es válido
            if position_type == 'BUY' and (target_sl >= current_price or target_sl <= entry_price):
                self.logger.warning(f"[{symbol}] SL objetivo inválido para BUY: {target_sl:.5f} (Entry: {entry_price:.5f}, Current: {current_price:.5f})")
                return None
            elif position_type == 'SELL' and (target_sl <= current_price or target_sl >= entry_price):
                self.logger.warning(f"[{symbol}] SL objetivo inválido para SELL: {target_sl:.5f} (Entry: {entry_price:.5f}, Current: {current_price:.5f})")
                return None
            
            # Aplicar modificación del SL
            result = self.executor.modify_position_sl(ticket, target_sl, take_profit)
            
            if result['success']:
                self.logger.info(
                    f"[{symbol}] ✅ Trailing Stop aplicado - Ticket: {ticket} | "
                    f"Progreso: {progress_percent:.1%} | "
                    f"SL: {current_sl:.5f} → {target_sl:.5f} | "
                    f"Precio actual: {current_price:.5f}"
                )
                return {
                    'action': 'trailing_stop',
                    'ticket': ticket,
                    'symbol': symbol,
                    'old_sl': current_sl,
                    'new_sl': target_sl,
                    'progress_percent': progress_percent
                }
            else:
                self.logger.warning(
                    f"[{symbol}] ⚠️  No se pudo aplicar trailing stop - Ticket: {ticket} | "
                    f"Error: {result.get('message', 'Unknown')}"
                )
                return None
            
        except Exception as e:
            self.logger.error(f"Error al verificar trailing stop para posición {position.get('ticket', 'unknown')}: {e}", exc_info=True)
            return None
    
    def _check_auto_close_time(self, positions: List[Dict]) -> Optional[Dict]:
        """
        Verifica si es hora de cerrar posiciones automáticamente (4:50 PM NY)
        
        Args:
            positions: Lista de posiciones abiertas
            
        Returns:
            Dict con información de cierres realizados o None
        """
        try:
            # Obtener hora actual en timezone de NY
            now_ny = datetime.now(self.close_tz)
            current_time = now_ny.time()
            
            # Verificar si es 4:50 PM o después (cerrar desde 4:50 hasta el fin del día)
            close_start = time(self.close_time.hour, self.close_time.minute)
            
            if current_time < close_start:
                return None  # Aún no es hora de cerrar
            
            # Es 4:50 PM o después - Intentar cerrar todas las posiciones
            # IMPORTANTE: Continuar intentando hasta que TODAS las posiciones estén cerradas
            # No usar cache para prevenir reintentos - necesitamos seguir intentando incluso si el mercado está cerrado
            
            closed_positions = []
            errors = []
            pending_positions = []
            
            for position in positions:
                ticket = position['ticket']
                symbol = position['symbol']
                
                # Verificar si ya intentamos cerrar esta posición hoy (evitar spam de logs)
                today = now_ny.date()
                attempt_key = f"close_attempt_{ticket}_{today}"
                
                if attempt_key not in self.daily_close_cache:
                    self.logger.info(f"[{symbol}] 🕐 Hora de cierre automático (4:50 PM NY) - Cerrando posición {ticket}")
                    self.daily_close_cache.add(attempt_key)
                else:
                    # Ya intentamos antes, intentar de nuevo (puede que el mercado haya vuelto a abrir)
                    self.logger.debug(f"[{symbol}] 🔄 Reintentando cerrar posición {ticket} (cierre automático pendiente)")
                
                result = self.executor.close_position(ticket)
                
                if result['success']:
                    # Marcar orden como cerrada en BD (cierre por hora - AUTO_CLOSE)
                    if self.db_manager.enabled:
                        close_price = result.get('close_price')
                        self.db_manager.mark_order_as_closed(ticket, close_reason='AUTO_CLOSE', close_price=close_price)
                    
                    closed_positions.append({
                        'ticket': ticket,
                        'symbol': symbol
                    })
                    # Remover de intentos pendientes si estaba
                    if attempt_key in self.daily_close_cache:
                        # Mantener el registro de que se intentó pero ya está cerrada
                        pass
                else:
                    error_msg = result.get('message', 'Unknown error')
                    errors.append({
                        'ticket': ticket,
                        'symbol': symbol,
                        'error': error_msg
                    })
                    pending_positions.append({
                        'ticket': ticket,
                        'symbol': symbol
                    })
                    # Log solo si es la primera vez o si pasó suficiente tiempo
                    if 'Market closed' in error_msg or '10018' in str(error_msg):
                        self.logger.warning(
                            f"[{symbol}] ⚠️  No se pudo cerrar posición {ticket}: Mercado cerrado - "
                            f"Se seguirá intentando cuando el mercado vuelva a abrir"
                        )
                    else:
                        self.logger.error(f"[{symbol}] ❌ Error al cerrar posición {ticket}: {error_msg}")
            
            # Si cerramos alguna posición, loguearlo
            if closed_positions:
                self.logger.info(
                    f"✅ Cierre automático parcial - {len(closed_positions)} posición(es) cerrada(s), "
                    f"{len(pending_positions)} pendiente(s)"
                )
            
            # Si hay posiciones pendientes, continuar intentando
            if pending_positions:
                # Log solo cada 60 segundos para no saturar
                current_time_sec = time_module.time()
                last_warning_key = f"pending_close_warning_{today}"
                if not hasattr(self, '_last_pending_warning') or (current_time_sec - getattr(self, '_last_pending_warning', 0)) >= 60:
                    self.logger.warning(
                        f"🔄 {len(pending_positions)} posición(es) pendiente(s) de cierre automático (4:50 PM NY) - "
                        f"Se seguirá intentando cerrar en cada ciclo de monitoreo hasta que se cierren todas"
                    )
                    self._last_pending_warning = current_time_sec
                
                return {
                    'action': 'auto_close_partial',
                    'closed_count': len(closed_positions),
                    'closed_positions': closed_positions,
                    'pending_count': len(pending_positions),
                    'pending_positions': pending_positions,
                    'errors': errors
                }
            
            # Si todas las posiciones se cerraron, loguear éxito completo
            if closed_positions and not pending_positions:
                self.logger.info(
                    f"✅ Cierre automático completado - Todas las {len(closed_positions)} posición(es) cerrada(s)"
                )
                return {
                    'action': 'auto_close',
                    'closed_count': len(closed_positions),
                    'closed_positions': closed_positions,
                    'errors': errors
                }
            
            # Si no había posiciones para cerrar
            return None
            
        except Exception as e:
            self.logger.error(f"Error al verificar hora de cierre automático: {e}", exc_info=True)
            return None
    
    def reset_daily_cache(self):
        """Resetea el cache de cierre diario (útil para testing o reseteo diario)"""
        self.daily_close_cache.clear()
        self.logger.debug("Cache de cierre diario reseteado")

