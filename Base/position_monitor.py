"""
Monitor de Posiciones Abiertas
Monitorea y gestiona posiciones abiertas en MT5 con:
- Trailing Stop Loss (70% -> mover SL a 50%)
- Cierre automático antes del cierre del día (4:50 PM NY)
"""

import logging
import time as time_module
from datetime import datetime, time, date
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
            log_msg += " - Solo monitoreando órdenes del día actual"
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
            all_positions = self.executor.get_positions()
            
            # Sincronizar BD con MT5 (marcar como cerradas las órdenes que ya no están abiertas en MT5)
            # IMPORTANTE: Hacer esto ANTES de verificar cierre automático para asegurar sincronización
            if self.db_manager.enabled:
                sync_result = self.db_manager.sync_orders_with_mt5(all_positions)
                if sync_result.get('closed', 0) > 0:
                    self.logger.info(f"🔄 Sincronización BD-MT5: {sync_result['closed']} orden(es) marcada(s) como cerrada(s)")
            
            # Filtrar solo las posiciones del día actual
            positions = self._filter_today_positions(all_positions)
            
            # Si después de sincronizar y filtrar no hay posiciones del día, retornar
            if not positions:
                # Log ocasional si hay posiciones de días anteriores (cada 60 segundos)
                if all_positions:
                    if not hasattr(self, '_last_old_positions_log') or (time_module.time() - getattr(self, '_last_old_positions_log', 0)) >= 60:
                        old_count = len(all_positions) - len(positions)
                        self.logger.info(
                            f"📅 Filtrado de posiciones: {len(all_positions)} posición(es) abierta(s) en total, "
                            f"{old_count} de día(s) anterior(es) (no monitoreadas), "
                            f"{len(positions)} del día actual"
                        )
                        self._last_old_positions_log = time_module.time()
                
                return {
                    'success': True,
                    'message': 'No hay posiciones abiertas del día actual',
                    'actions': [],
                    'open_count': 0
                }
            
            actions = []
            
            if self.auto_close_enabled:
                close_action = self._check_auto_close_time(positions)
                if close_action:
                    actions.append(close_action)
                    # Actualizar lista de posiciones después de intentar cerrar
                    all_remaining_positions = self.executor.get_positions()
                    # Filtrar solo las del día actual
                    remaining_positions = self._filter_today_positions(all_remaining_positions)
                    
                    # Si cerramos algunas posiciones, loguearlo
                    if close_action.get('closed_count', 0) > 0:
                        self.logger.info(
                            f"✅ Cierre automático (4:50 PM NY): {close_action['closed_count']} posición(es) cerrada(s)"
                        )
                    
                    # Si aún hay posiciones pendientes del día actual, continuar intentando cerrar
                    if close_action.get('pending_count', 0) > 0:
                        self.logger.warning(
                            f"⚠️  Cierre automático (4:50 PM NY): {close_action['pending_count']} posición(es) pendiente(s) - "
                            f"Se seguirá intentando cerrar en cada ciclo de monitoreo"
                        )
                        # Continuar con trailing stop pero priorizar cierre en el próximo ciclo
                        positions = remaining_positions
                    elif not remaining_positions:
                        # Todas las posiciones del día fueron cerradas exitosamente
                        self.logger.info(
                            f"✅ Cierre automático (4:50 PM NY) completado - Todas las posiciones del día cerradas"
                        )
                        return {
                            'success': True,
                            'message': f'Todas las posiciones del día cerradas por hora de cierre (4:50 PM NY)',
                            'actions': actions,
                            'open_count': 0
                        }
                    else:
                        # Actualizar lista de posiciones para continuar con trailing stop
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
            
            # Obtener precio actual del mercado para verificar (más preciso que price_current de la posición)
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                # Para SELL usar bid, para BUY usar ask
                if position_type == 'SELL':
                    market_price = float(tick.bid)
                else:  # BUY
                    market_price = float(tick.ask)
                # Usar el precio del mercado si está disponible (más actualizado)
                if abs(market_price - current_price) > 0.00001:  # Si hay diferencia significativa
                    current_price = market_price
                    self.logger.debug(
                        f"[{symbol}] Precio actualizado desde mercado: {position['price_current']:.5f} → {current_price:.5f}"
                    )
            
            # Necesitamos TP para calcular el movimiento
            if take_profit <= 0:
                # Si no hay TP, no podemos aplicar trailing stop
                self.logger.debug(f"[{symbol}] ⏸️  Trailing stop: No hay TP definido para ticket {ticket}")
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
            
            # Log periódico cuando está cerca del 70% (cada 10 segundos)
            current_time = time_module.time()
            log_key = f"trailing_log_{ticket}"
            if not hasattr(self, '_last_trailing_logs'):
                self._last_trailing_logs = {}
            
            # Log cuando está cerca del umbral (65% o más) pero aún no alcanza el 70%
            if 0.65 <= progress_percent < self.trailing_trigger_percent:
                if log_key not in self._last_trailing_logs or (current_time - self._last_trailing_logs[log_key]) >= 10:
                    self.logger.info(
                        f"[{symbol}] 📊 Monitoreando trailing stop - Ticket: {ticket} | "
                        f"Progreso: {progress_percent:.1%} | "
                        f"Esperando alcanzar {self.trailing_trigger_percent*100:.0f}% para mover SL a {self.trailing_sl_percent*100:.0f}% | "
                        f"Entry: {entry_price:.5f} | Current: {current_price:.5f} | TP: {take_profit:.5f} | "
                        f"Movimiento: {current_movement:.5f}/{total_movement:.5f}"
                    )
                    self._last_trailing_logs[log_key] = current_time
            
            # Verificar si alcanzó el 70% del movimiento
            # Usar >= en lugar de < para incluir exactamente el 70%
            if progress_percent < self.trailing_trigger_percent:
                # Log detallado cuando está muy cerca pero aún no alcanza
                if progress_percent >= 0.68:  # Muy cerca del umbral
                    if log_key not in self._last_trailing_logs or (current_time - self._last_trailing_logs[log_key]) >= 5:
                        self.logger.debug(
                            f"[{symbol}] ⏳ Trailing stop: Muy cerca del umbral - "
                            f"Progreso: {progress_percent:.2%} (falta {((self.trailing_trigger_percent - progress_percent) * 100):.2f}% para {self.trailing_trigger_percent*100:.0f}%) | "
                            f"Precio actual: {current_price:.5f}"
                        )
                        self._last_trailing_logs[log_key] = current_time
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
                        self.logger.debug(
                            f"[{symbol}] ⏸️  Trailing stop: Precio retrocedió (Current: {current_price:.5f} <= SL: {current_sl:.5f}) - "
                            f"No se puede mejorar SL"
                        )
                        return None
                    # Solo actualizar si el nuevo SL está más cerca del precio actual pero aún es mejor que el actual
                    if target_sl <= current_sl:
                        self.logger.debug(
                            f"[{symbol}] ⏸️  Trailing stop: SL objetivo ({target_sl:.5f}) no es mejor que SL actual ({current_sl:.5f})"
                        )
                        return None
            else:  # SELL
                # SL a 50% del movimiento desde entry
                # Para SELL: el SL debe estar ARRIBA del entry (protege contra subidas)
                # Concepto: cuando el precio ha recorrido 70% del camino, mover el SL para asegurar que capturemos al menos 50% de las ganancias
                # Calculamos: entry + (50% del movimiento total)
                # Esto coloca el SL a una distancia del entry igual al 50% del movimiento total
                target_sl = entry_price + (total_movement * self.trailing_sl_percent)
                # El nuevo SL debe estar por debajo del SL actual (si existe) para proteger más ganancias
                # Para SELL: un SL más bajo (más cerca del precio actual) es mejor
                if current_sl > 0 and target_sl >= current_sl:
                    # Ya se movió el SL anteriormente, solo actualizar si el nuevo es mejor
                    # Verificar si el precio actual permite un SL mejor
                    if current_price >= current_sl:
                        # El precio retrocedió, no podemos mejorar el SL
                        self.logger.debug(
                            f"[{symbol}] ⏸️  Trailing stop: Precio retrocedió (Current: {current_price:.5f} >= SL: {current_sl:.5f}) - "
                            f"No se puede mejorar SL"
                        )
                        return None
                    # Solo actualizar si el nuevo SL está más cerca del precio actual pero aún es mejor que el actual
                    if target_sl >= current_sl:
                        self.logger.debug(
                            f"[{symbol}] ⏸️  Trailing stop: SL objetivo ({target_sl:.5f}) no es mejor que SL actual ({current_sl:.5f})"
                        )
                        return None
            
            # Verificar que el nuevo SL es válido
            if position_type == 'BUY' and (target_sl >= current_price or target_sl <= entry_price):
                self.logger.warning(f"[{symbol}] SL objetivo inválido para BUY: {target_sl:.5f} (Entry: {entry_price:.5f}, Current: {current_price:.5f})")
                return None
            elif position_type == 'SELL' and (target_sl <= current_price or target_sl <= entry_price):
                # Para SELL: el SL debe estar ARRIBA del entry y ARRIBA del precio actual
                self.logger.warning(f"[{symbol}] SL objetivo inválido para SELL: {target_sl:.5f} (Entry: {entry_price:.5f}, Current: {current_price:.5f}) - Debe estar arriba del entry")
                return None
            
            # Log antes de aplicar
            self.logger.info(
                f"[{symbol}] 🔄 Aplicando Trailing Stop - Ticket: {ticket} | "
                f"Progreso: {progress_percent:.1%} (>= {self.trailing_trigger_percent*100:.0f}%) | "
                f"SL actual: {current_sl:.5f} → SL objetivo: {target_sl:.5f} ({self.trailing_sl_percent*100:.0f}% del movimiento) | "
                f"Entry: {entry_price:.5f} | Current: {current_price:.5f} | TP: {take_profit:.5f}"
            )
            
            # Aplicar modificación del SL
            result = self.executor.modify_position_sl(ticket, target_sl, take_profit)
            
            if result['success']:
                self.logger.info(
                    f"[{symbol}] ✅ Trailing Stop aplicado exitosamente - Ticket: {ticket} | "
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
    
    def is_auto_close_time(self) -> bool:
        """
        Verifica si es hora de cierre automático (4:50 PM NY)
        
        Returns:
            True si es hora de cerrar posiciones, False en caso contrario
        """
        # Verificar primero si el cierre automático está habilitado en la configuración
        if not self.auto_close_enabled:
            return False
        
        try:
            # Obtener hora actual en timezone de NY
            now_ny = datetime.now(self.close_tz)
            current_time = now_ny.time()
            
            # Verificar si es 4:50 PM o después (cerrar desde 4:50 hasta el fin del día)
            close_start = time(self.close_time.hour, self.close_time.minute)
            
            return current_time >= close_start
        except Exception as e:
            self.logger.error(f"Error al verificar hora de cierre automático: {e}", exc_info=True)
            return False
    
    def _check_auto_close_time(self, positions: List[Dict]) -> Optional[Dict]:
        """
        Verifica si es hora de cerrar posiciones automáticamente (4:50 PM NY)
        
        Args:
            positions: Lista de posiciones abiertas
            
        Returns:
            Dict con información de cierres realizados o None
        """
        try:
            # Verificar si es hora de cerrar
            if not self.is_auto_close_time():
                return None  # Aún no es hora de cerrar
            
            # Obtener hora actual en timezone de NY
            now_ny = datetime.now(self.close_tz)
            
            # Es 4:50 PM o después - CERRAR TODAS LAS POSICIONES ABIERTAS
            # IMPORTANTE: Continuar intentando hasta que TODAS las posiciones estén cerradas
            # Esto tiene PRIORIDAD sobre cualquier otra operación (trailing stop, etc.)
            
            closed_positions = []
            errors = []
            pending_positions = []
            
            # Log inicial cuando se detecta la hora de cierre
            today = now_ny.date()
            today_key = f"auto_close_today_{today}"
            if today_key not in self.daily_close_cache:
                self.logger.warning(
                    f"🕐 HORA DE CIERRE AUTOMÁTICO (4:50 PM NY) - "
                    f"Cerrando TODAS las posiciones abiertas ({len(positions)} posición(es))"
                )
                self.daily_close_cache.add(today_key)
            
            for position in positions:
                ticket = position['ticket']
                symbol = position['symbol']
                
                # Verificar si ya intentamos cerrar esta posición hoy (evitar spam de logs)
                attempt_key = f"close_attempt_{ticket}_{today}"
                
                if attempt_key not in self.daily_close_cache:
                    self.logger.info(f"[{symbol}] 🕐 Cerrando posición {ticket} (cierre automático 4:50 PM NY)")
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
            
            # Si hay posiciones pendientes, continuar intentando (PRIORIDAD MÁXIMA)
            if pending_positions:
                # Log cada 30 segundos para mantener visibilidad
                current_time_sec = time_module.time()
                last_warning_key = f"pending_close_warning_{today}"
                if not hasattr(self, '_last_pending_warning') or (current_time_sec - getattr(self, '_last_pending_warning', 0)) >= 30:
                    self.logger.warning(
                        f"🔄 CIERRE AUTOMÁTICO (4:50 PM NY): {len(pending_positions)} posición(es) pendiente(s) - "
                        f"Se seguirá intentando cerrar en cada ciclo de monitoreo hasta que se cierren TODAS"
                    )
                    # Mostrar detalles de posiciones pendientes
                    for pos in pending_positions[:5]:  # Mostrar máximo 5
                        self.logger.warning(f"   ⚠️  Pendiente: {pos['symbol']} - Ticket: {pos['ticket']}")
                    if len(pending_positions) > 5:
                        self.logger.warning(f"   ... y {len(pending_positions) - 5} más")
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
    
    def _get_position_creation_date(self, ticket: int, position_time: Optional[datetime] = None) -> Optional[date]:
        """
        Obtiene la fecha de creación de una posición
        
        Args:
            ticket: Ticket de la posición
            position_time: Fecha/hora de creación desde MT5 (opcional)
            
        Returns:
            date en timezone NY o None si no se puede determinar
        """
        # Primero intentar desde MT5 si está disponible
        if position_time and isinstance(position_time, datetime):
            try:
                # Convertir a timezone NY
                if position_time.tzinfo is None:
                    position_time_utc = tz('UTC').localize(position_time)
                    position_time_ny = position_time_utc.astimezone(self.close_tz)
                else:
                    position_time_ny = position_time.astimezone(self.close_tz)
                return position_time_ny.date()
            except Exception as e:
                self.logger.debug(f"Error al convertir fecha MT5 para ticket {ticket}: {e}")
        
        # Si no está disponible desde MT5, intentar desde BD
        if self.db_manager.enabled:
            try:
                if not self.db_manager._ensure_connection():
                    return None
                
                cursor = self.db_manager.connection.cursor()
                query = "SELECT CreatedAt FROM Orders WHERE Ticket = ?"
                cursor.execute(query, (ticket,))
                row = cursor.fetchone()
                cursor.close()
                
                if row and row[0]:
                    created_at = row[0]
                    if isinstance(created_at, datetime):
                        # Convertir a timezone NY
                        if created_at.tzinfo is None:
                            created_at_utc = tz('UTC').localize(created_at)
                            created_at_ny = created_at_utc.astimezone(self.close_tz)
                        else:
                            created_at_ny = created_at.astimezone(self.close_tz)
                        return created_at_ny.date()
            except Exception as e:
                self.logger.debug(f"Error al consultar BD para ticket {ticket}: {e}")
        
        return None
    
    def _filter_today_positions(self, positions: List[Dict]) -> List[Dict]:
        """
        Filtra las posiciones para solo incluir las que fueron abiertas el día actual
        
        Args:
            positions: Lista de posiciones desde MT5
            
        Returns:
            Lista filtrada con solo posiciones del día actual
        """
        if not positions:
            return []
        
        # Obtener fecha actual en timezone de NY (mismo que se usa para cierre automático)
        now_ny = datetime.now(self.close_tz)
        today_ny = now_ny.date()
        
        today_positions = []
        skipped_positions = []
        
        for position in positions:
            ticket = position.get('ticket')
            symbol = position.get('symbol', 'UNKNOWN')
            position_time = position.get('time')
            
            # Obtener fecha de creación
            creation_date = self._get_position_creation_date(ticket, position_time)
            
            if creation_date:
                # Verificar si es del día actual
                if creation_date == today_ny:
                    today_positions.append(position)
                else:
                    skipped_positions.append({
                        'ticket': ticket,
                        'symbol': symbol,
                        'date': creation_date
                    })
            else:
                # No se pudo determinar la fecha - incluir por seguridad pero loguear
                self.logger.warning(
                    f"[{symbol}] ⚠️  No se pudo determinar fecha de creación para ticket {ticket} - "
                    f"Incluyendo en monitoreo por seguridad"
                )
                today_positions.append(position)
        
        # Log ocasional de posiciones filtradas (cada 5 minutos)
        if skipped_positions:
            if not hasattr(self, '_last_filter_log') or (time_module.time() - getattr(self, '_last_filter_log', 0)) >= 300:
                self.logger.info(
                    f"📅 Filtrado de posiciones: {len(skipped_positions)} posición(es) de día(s) anterior(es) "
                    f"excluida(s) del monitoreo (solo se monitorean órdenes del día actual)"
                )
                # Mostrar algunas posiciones excluidas
                for pos in skipped_positions[:3]:
                    self.logger.debug(
                        f"   ⏭️  Excluida: {pos['symbol']} - Ticket: {pos['ticket']} "
                        f"(abierta el {pos['date']})"
                    )
                if len(skipped_positions) > 3:
                    self.logger.debug(f"   ... y {len(skipped_positions) - 3} más")
                self._last_filter_log = time_module.time()
        
        return today_positions
    
    def reset_daily_cache(self):
        """Resetea el cache de cierre diario (útil para testing o reseteo diario)"""
        self.daily_close_cache.clear()
        self.logger.debug("Cache de cierre diario reseteado")

