"""
Bot de Trading para MetaTrader 5
Sistema multi-estrategia con gestión de horarios operativos
"""

import yaml
import logging
from datetime import datetime, time, date
from typing import List, Dict, Optional
import MetaTrader5 as mt5
from pytz import timezone
import time as time_module

from strategy_manager import StrategyManager
from Base.trading_hours import TradingHoursManager
from Base.position_monitor import PositionMonitor
from Base.database import DatabaseManager
from Base.db_log_handler import DatabaseLogHandler
from Base.strategy_scheduler import StrategyScheduler


class TradingBot:
    """Bot principal de trading con conexión a MT5"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Inicializa el bot de trading
        
        Args:
            config_path: Ruta al archivo de configuración
        """
        self.config = self._load_config(config_path)
        self._setup_logging()
        self.logger.info("Inicializando Bot de Trading...")
        
        # Inicializar componentes
        self.mt5_connected = False
        self.strategy_manager = StrategyManager(self.config)
        self.trading_hours = TradingHoursManager(self.config['trading_hours'])
        self.position_monitor = PositionMonitor(self.config)
        self.strategy_scheduler = StrategyScheduler(self.config)
        
        # Inicializar base de datos y configurar handler de logging
        self.db_manager = DatabaseManager(self.config)
        self._setup_database_logging()
        
        # Conectar a MT5
        self._connect_mt5()
        
    def _load_config(self, config_path: str) -> Dict:
        """Carga la configuración desde archivo YAML"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except FileNotFoundError:
            raise FileNotFoundError(f"Archivo de configuración no encontrado: {config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Error al leer configuración: {e}")
    
    def _setup_logging(self):
        """Configura el sistema de logging"""
        log_level = getattr(logging, self.config.get('general', {}).get('log_level', 'INFO'))
        
        # Crear carpeta logs si no existe
        import os
        os.makedirs('logs', exist_ok=True)
        
        # Configurar logging con archivo en carpeta logs/
        log_file = os.path.join('logs', 'trading_bot.log')
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def _setup_database_logging(self):
        """Configura el handler de logging para base de datos"""
        try:
            if self.db_manager.enabled:
                # Crear handler personalizado para BD
                db_handler = DatabaseLogHandler(
                    db_manager=self.db_manager,
                    min_level=logging.INFO  # Solo guardar INFO y superiores
                )
                
                # Agregar handler al root logger para que capture todos los logs
                root_logger = logging.getLogger()
                root_logger.addHandler(db_handler)
                
                self.logger.info("✅ Handler de logging para base de datos configurado")
            else:
                self.logger.debug("Base de datos deshabilitada - Logs no se guardarán en BD")
        except Exception as e:
            self.logger.warning(f"No se pudo configurar handler de BD: {e}")
    
    def _connect_mt5(self) -> bool:
        """Conecta al terminal MT5"""
        mt5_config = self.config['mt5']
        
        # Cerrar conexión existente si hay
        if self.mt5_connected:
            mt5.shutdown()
            self.mt5_connected = False
        
        # Inicializar MT5
        if not mt5.initialize(path=mt5_config.get('path')):
            self.logger.error(f"Error al inicializar MT5: {mt5.last_error()}")
            return False
        
        # Intentar conexión
        login = mt5_config['login']
        password = mt5_config['password']
        server = mt5_config['server']
        
        self.logger.info(f"Conectando a MT5 - Login: {login}, Server: {server}")
        
        authorized = mt5.login(login, password=password, server=server)
        
        if not authorized:
            self.logger.error(f"Error al conectar a MT5: {mt5.last_error()}")
            mt5.shutdown()
            return False
        
        # Verificar conexión
        account_info = mt5.account_info()
        if account_info is None:
            self.logger.error("No se pudo obtener información de la cuenta")
            mt5.shutdown()
            return False
        
        self.mt5_connected = True
        self.logger.info(f"✓ Conectado exitosamente a MT5")
        self.logger.info(f"  Cuenta: {account_info.login}")
        self.logger.info(f"  Balance: {account_info.balance} {account_info.currency}")
        self.logger.info(f"  Servidor: {account_info.server}")
        
        return True
    
    def _check_and_reconnect_mt5(self) -> bool:
        """
        Verifica la conexión de MT5 y reconecta si es necesario
        
        Returns:
            True si está conectado, False si no se pudo conectar
        """
        if not self.mt5_connected:
            self.logger.warning("MT5 no está conectado, intentando reconectar...")
            return self._connect_mt5()
        
        # Verificar que la conexión sigue activa
        account_info = mt5.account_info()
        if account_info is None:
            self.logger.warning("Conexión MT5 perdida, intentando reconectar...")
            self.mt5_connected = False
            return self._connect_mt5()
        
        return True
    
    def _is_trading_time(self) -> bool:
        """Verifica si estamos en horario operativo"""
        return self.trading_hours.is_trading_time()
    
    def _analyze_market(self):
        """Analiza el mercado para los símbolos configurados"""
        # Verificar y reconectar MT5 si es necesario
        if not self._check_and_reconnect_mt5():
            self.logger.warning("No se pudo conectar a MT5, saltando análisis")
            return
        
        symbols = self.config['symbols']
        # Obtener estrategia activa según el scheduler (puede cambiar por jornada)
        strategy_name = self.strategy_scheduler.get_current_strategy()
        
        # Verificar si la estrategia funciona 24/7 (sin restricción de horario)
        strategy = self.strategy_manager.strategies.get(strategy_name)
        is_24_7_strategy = False
        if strategy and hasattr(strategy, 'is_24_7_strategy'):
            is_24_7_strategy = strategy.is_24_7_strategy()
        
        # Verificar horario operativo (solo si la estrategia no es 24/7)
        if not is_24_7_strategy:
            if not self._is_trading_time():
                # Solo loguear una vez cada 5 minutos para no saturar
                if not hasattr(self, '_last_trading_hours_log') or (time_module.time() - self._last_trading_hours_log) >= 300:
                    self.logger.debug("Fuera de horario operativo, esperando...")
                    self._last_trading_hours_log = time_module.time()
                return
        
        # ⚠️ VERIFICACIÓN TEMPRANA: Si la estrategia alcanzó el límite de trades, detener análisis
        if strategy and hasattr(strategy, 'has_reached_daily_limit'):
            if strategy.has_reached_daily_limit():
                # Solo loguear una vez cada minuto para no saturar
                if not hasattr(self, '_last_limit_log') or (time_module.time() - self._last_limit_log) >= 60:
                    self.logger.info(
                        f"⏸️  Límite de trades diarios alcanzado para estrategia '{strategy_name}' | "
                        f"Análisis detenido hasta próxima sesión operativa"
                    )
                    self._last_limit_log = time_module.time()
                return
        
        self.logger.info(f"Analizando mercado para {len(symbols)} símbolo(s) con estrategia: {strategy_name}")
        
        for symbol in symbols:
            try:
                # Verificar que el símbolo existe en MT5
                symbol_info = mt5.symbol_info(symbol)
                if symbol_info is None:
                    self.logger.warning(f"Símbolo {symbol} no encontrado en MT5")
                    continue
                
                # Verificar que el símbolo está habilitado
                if not symbol_info.visible:
                    self.logger.info(f"Habilitando símbolo {symbol}...")
                    if not mt5.symbol_select(symbol, True):
                        self.logger.error(f"No se pudo habilitar {symbol}")
                        continue
                
                # Obtener datos del mercado
                timeframe = self._parse_timeframe(self.config['general']['timeframe'])
                rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 100)
                
                if rates is None or len(rates) == 0:
                    self.logger.warning(f"No se pudieron obtener datos para {symbol}")
                    continue
                
                # Ejecutar análisis con la estrategia
                self.logger.debug(f"Analizando {symbol} con {len(rates)} velas")
                signal = self.strategy_manager.analyze(symbol, rates, strategy_name)
                
                if signal:
                    self.logger.info(f"Señal generada para {symbol}: {signal}")
                    # Aquí se implementará la lógica de ejecución de órdenes
                else:
                    self.logger.debug(f"No hay señal para {symbol}")
                    
            except Exception as e:
                self.logger.error(f"Error al analizar {symbol}: {e}", exc_info=True)
    
    def _monitor_positions(self) -> Dict:
        """
        Monitorea posiciones abiertas y aplica reglas de gestión:
        - Trailing stop loss (70% -> mover SL a 50%)
        - Cierre automático a las 4:50 PM NY
        
        Returns:
            Dict con información de posiciones abiertas
        """
        try:
            result = self.position_monitor.monitor_positions()
            
            if not result['success']:
                self.logger.warning(f"Error en monitoreo de posiciones: {result.get('message', 'Unknown')}")
                return {'success': False, 'open_count': 0}
            
            actions = result.get('actions', [])
            if actions:
                for action in actions:
                    if action['action'] == 'trailing_stop':
                        self.logger.info(
                            f"📈 Trailing Stop aplicado - {action['symbol']} | "
                            f"Ticket: {action['ticket']} | "
                            f"SL: {action['old_sl']:.5f} → {action['new_sl']:.5f} | "
                            f"Progreso: {action['progress_percent']:.1%}"
                        )
                    elif action['action'] == 'auto_close':
                        self.logger.info(
                            f"🕐 Cierre automático - {action['closed_count']} posición(es) cerrada(s)"
                        )
                        for pos in action.get('closed_positions', []):
                            self.logger.info(f"  ✅ {pos['symbol']} - Ticket: {pos['ticket']}")
            
            # Obtener conteo de posiciones abiertas para retornar
            try:
                positions = self.position_monitor.executor.get_positions()
                result['open_count'] = len(positions) if positions else 0
            except:
                result['open_count'] = 0
            
            return result
                        
        except Exception as e:
            self.logger.error(f"Error en monitoreo de posiciones: {e}", exc_info=True)
            return {'success': False, 'open_count': 0}
    
    def _has_open_positions(self) -> bool:
        """
        Verifica si hay posiciones abiertas del día actual (rápido, sin loguear)
        
        IMPORTANTE: Solo considera posiciones del día actual. Las órdenes de días
        anteriores se ignoran completamente.
        
        Returns:
            True si hay posiciones abiertas del día actual, False si no hay
        """
        try:
            if not self.mt5_connected:
                return False
            
            all_positions = mt5.positions_get()
            if all_positions is None:
                return False
            
            # Filtrar solo posiciones del día actual usando PositionMonitor
            # Obtener timezone de NY para consistencia
            try:
                auto_close_config = self.config.get('position_monitoring', {}).get('auto_close', {})
                timezone_str = auto_close_config.get('timezone', 'America/New_York')
                from pytz import timezone as tz
                ny_tz = tz(timezone_str)
            except:
                from pytz import timezone as tz
                ny_tz = tz('America/New_York')
            
            now_ny = datetime.now(ny_tz)
            today_ny = now_ny.date()
            
            # Filtrar posiciones del día actual
            today_positions = []
            for pos in all_positions:
                try:
                    # Obtener fecha de creación desde MT5
                    pos_time = datetime.fromtimestamp(pos.time)
                    if pos_time.tzinfo is None:
                        pos_time_utc = tz('UTC').localize(pos_time)
                        pos_time_ny = pos_time_utc.astimezone(ny_tz)
                    else:
                        pos_time_ny = pos_time.astimezone(ny_tz)
                    
                    if pos_time_ny.date() == today_ny:
                        today_positions.append(pos)
                except Exception as e:
                    # Si hay error al procesar fecha, incluir por seguridad
                    self.logger.debug(f"Error al procesar fecha de posición {pos.ticket}: {e}")
                    today_positions.append(pos)
            
            has_pos = len(today_positions) > 0
            
            # Log de diagnóstico ocasional (cada 60 segundos máximo)
            if has_pos:
                if not hasattr(self, '_last_position_check_log'):
                    self._last_position_check_log = 0
                if (time_module.time() - self._last_position_check_log) >= 60:
                    total_count = len(all_positions)
                    today_count = len(today_positions)
                    if total_count > today_count:
                        self.logger.debug(
                            f"✅ Detectadas {today_count} posición(es) del día actual en MT5 "
                            f"(de {total_count} total, {total_count - today_count} excluidas por ser de día(s) anterior(es))"
                        )
                    else:
                        self.logger.debug(f"✅ Detectadas {today_count} posición(es) abierta(s) del día actual en MT5")
                    self._last_position_check_log = time_module.time()
            
            return has_pos
        except Exception as e:
            self.logger.error(f"Error al verificar posiciones abiertas: {e}", exc_info=True)
            return False
    
    def _has_open_orders_in_db(self) -> bool:
        """
        Verifica si hay órdenes abiertas en la base de datos (fuente de verdad)
        
        Returns:
            True si hay órdenes abiertas en BD, False si no hay
        """
        try:
            if not self.db_manager.enabled:
                self.logger.debug("BD no habilitada - no se puede verificar órdenes abiertas")
                return False
            
            open_orders = self.db_manager.get_open_orders()
            has_orders = len(open_orders) > 0
            
            # Log de diagnóstico: mostrar qué órdenes se encontraron
            if has_orders:
                if not hasattr(self, '_db_orders_detected_logged'):
                    self.logger.warning(f"🚨 ⚠️  SE DETECTARON {len(open_orders)} ORDEN(ES) CON Status='OPEN' EN BASE DE DATOS")
                    for order in open_orders:
                        self.logger.warning(
                            f"   🎫 Ticket: {order.get('ticket')}, "
                            f"Symbol: {order.get('symbol')}, "
                            f"Tipo: {order.get('order_type')}, "
                            f"Status: '{order.get('status', 'OPEN')}'"
                        )
                    self._db_orders_detected_logged = True
            else:
                # Si no hay órdenes abiertas, verificar si hay órdenes cerradas (para diagnóstico)
                if not hasattr(self, '_db_closed_orders_checked'):
                    try:
                        # Consultar todas las órdenes de hoy para diagnóstico
                        cursor = self.db_manager.connection.cursor()
                        today = datetime.now().date()
                        query = "SELECT COUNT(*) FROM Orders WHERE CAST(CreatedAt AS DATE) = ?"
                        cursor.execute(query, (today,))
                        total_today = cursor.fetchone()[0]
                        cursor.close()
                        
                        if total_today > 0:
                            self.logger.info(f"📊 Diagnóstico: Hay {total_today} orden(es) en BD hoy, pero todas están cerradas (Status='CLOSED')")
                        self._db_closed_orders_checked = True
                    except:
                        pass
            
            # Log siempre cuando hay órdenes (para diagnóstico - cada 10 segundos)
            if has_orders:
                if not hasattr(self, '_last_db_order_check_log'):
                    self._last_db_order_check_log = 0
                # Log cada 10 segundos cuando hay órdenes (más frecuente para diagnóstico)
                if (time_module.time() - self._last_db_order_check_log) >= 10:
                    self.logger.info(f"📊 ⚠️  DETECTADAS {len(open_orders)} ORDEN(ES) ABIERTA(S) EN BASE DE DATOS")
                    for order in open_orders:
                        self.logger.info(
                            f"   • Ticket: {order.get('ticket')}, "
                            f"Symbol: {order.get('symbol')}, "
                            f"Tipo: {order.get('order_type')}, "
                            f"Status: {order.get('status', 'OPEN')}"
                        )
                    self._last_db_order_check_log = time_module.time()
            else:
                # Log ocasional cuando NO hay órdenes (cada 60 segundos)
                if not hasattr(self, '_last_db_order_check_log_empty'):
                    self._last_db_order_check_log_empty = 0
                if (time_module.time() - self._last_db_order_check_log_empty) >= 60:
                    self.logger.debug("📊 No hay órdenes abiertas en BD")
                    self._last_db_order_check_log_empty = time_module.time()
            
            return has_orders
        except Exception as e:
            self.logger.error(f"❌ Error al verificar órdenes abiertas en BD: {e}", exc_info=True)
            return False
    
    def _parse_timeframe(self, tf_str: str) -> int:
        """Convierte string de timeframe a constante MT5"""
        timeframe_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
        }
        return timeframe_map.get(tf_str.upper(), mt5.TIMEFRAME_M15)
    
    def run(self):
        """Ejecuta el bot en modo continuo"""
        self.logger.info("=" * 50)
        self.logger.info("Bot de Trading iniciado")
        self.logger.info("=" * 50)
        self.logger.info(f"Activos: {', '.join(self.config['symbols'])}")
        self.logger.info(f"Horario operativo: {self.config['trading_hours']['start_time']} - {self.config['trading_hours']['end_time']} ({self.config['trading_hours']['timezone']})")
        
        # Mostrar información de estrategia según el modo
        if self.strategy_scheduler.enabled:
            session_info = self.strategy_scheduler.get_current_session_info()
            if session_info:
                self.logger.info(f"📅 Sistema de jornadas activo - Sesión actual: '{session_info['name']}' → Estrategia: '{session_info['strategy']}'")
            else:
                self.logger.info(f"📅 Sistema de jornadas activo - Estrategia actual: '{self.strategy_scheduler.get_current_strategy()}'")
        else:
            self.logger.info(f"Estrategia: {self.config['strategy']['name']}")
        
        # Verificar si el día actual es operativo
        is_trading_day, day_reason, holidays = self.trading_hours.is_trading_day()
        if is_trading_day:
            self.logger.info(f"📅 Día operativo: {day_reason}")
        else:
            self.logger.warning(f"🚫 {day_reason}")
            if holidays:
                holiday_names = [h.get('title', 'Holiday') for h in holidays]
                self.logger.warning(f"   Feriados detectados: {', '.join(holiday_names)}")
            next_trading = self.trading_hours.get_next_trading_time()
            self.logger.info(f"   Próximo día operativo: {next_trading.strftime('%Y-%m-%d %H:%M')}")
        
        self.logger.info("=" * 50)
        
        if not self.mt5_connected:
            self.logger.error("No se pudo conectar a MT5. El bot no puede continuar.")
            return
        
        try:
            while True:
                current_time = datetime.now()
                
                # PRIMERO: Verificar si hay órdenes abiertas ANTES de cualquier análisis o monitoreo
                # Verificar posiciones abiertas desde MT5 Y desde BD (fuente de verdad)
                has_mt5_positions = self._has_open_positions()
                has_db_orders = self._has_open_orders_in_db()
                has_open_positions = has_mt5_positions or has_db_orders
                
                # Monitorear posiciones abiertas (siempre, independiente del horario operativo)
                # IMPORTANTE: El monitoreo incluye cierre automático a las 4:50 PM NY
                monitor_result = self._monitor_positions()
                
                # Verificar si hay acciones de cierre automático
                actions = monitor_result.get('actions', [])
                auto_close_actions = [a for a in actions if a.get('action') in ['auto_close', 'auto_close_partial']]
                if auto_close_actions:
                    for action in auto_close_actions:
                        if action.get('closed_count', 0) > 0:
                            self.logger.info(
                                f"✅ Cierre automático (4:50 PM NY): {action['closed_count']} posición(es) cerrada(s)"
                            )
                        if action.get('pending_count', 0) > 0:
                            self.logger.warning(
                                f"⚠️  Cierre automático (4:50 PM NY): {action['pending_count']} posición(es) pendiente(s) - "
                                f"Se seguirá intentando cerrar"
                            )
                
                # Log de diagnóstico cada ciclo cuando hay órdenes en BD
                if has_db_orders:
                    self.logger.warning(
                        f"🚨 DEBUG: has_db_orders={has_db_orders}, "
                        f"has_mt5_positions={has_mt5_positions}, "
                        f"has_open_positions={has_open_positions}"
                    )
                
                # Log de diagnóstico cuando hay órdenes en BD pero no en MT5
                if has_db_orders and not has_mt5_positions:
                    if not hasattr(self, '_last_sync_warning_log'):
                        self._last_sync_warning_log = 0
                    if (time_module.time() - self._last_sync_warning_log) >= 30:
                        self.logger.warning(
                            "⚠️  Hay órdenes abiertas en BD pero no en MT5 - "
                            "Sincronizando automáticamente..."
                        )
                        # Forzar sincronización
                        if self.db_manager.enabled:
                            mt5_positions = []
                            try:
                                if self.mt5_connected:
                                    from Base.order_executor import OrderExecutor
                                    executor = OrderExecutor()
                                    mt5_positions = executor.get_positions()
                            except Exception as e:
                                self.logger.error(f"Error al obtener posiciones MT5 para sincronización: {e}")
                            self.db_manager.sync_orders_with_mt5(mt5_positions)
                        self._last_sync_warning_log = time_module.time()
                
                # Si hay posiciones abiertas del día actual, priorizar monitoreo sobre análisis
                if has_open_positions:
                    # Log inmediato cuando detecta posiciones abiertas del día actual (cada 5 segundos)
                    if not hasattr(self, '_last_position_detected_log'):
                        self._last_position_detected_log = 0
                    if (time_module.time() - self._last_position_detected_log) >= 5:
                        self.logger.warning(
                            f"🛑 POSICIONES ABIERTAS DEL DÍA ACTUAL DETECTADAS - "
                            f"MT5: {has_mt5_positions}, BD: {has_db_orders} - "
                            f"PRIORIZANDO MONITOREO - NO ANALIZANDO"
                        )
                        self._last_position_detected_log = time_module.time()
                    # Monitoreo activo: verificar cada 5 segundos (más frecuente)
                    # open_count_mt5 ya viene filtrado del PositionMonitor (solo día actual)
                    open_count_mt5 = monitor_result.get('open_count', 0) if isinstance(monitor_result, dict) else 0
                    
                    # Obtener conteo desde BD también (ya filtra por día actual por defecto)
                    open_count_db = 0
                    if self.db_manager.enabled:
                        db_orders = self.db_manager.get_open_orders(today_only=True)
                        open_count_db = len(db_orders) if db_orders else 0
                    
                    # Mostrar mensaje de monitoreo cada 30 segundos para no saturar logs
                    if not hasattr(self, '_last_monitor_log'):
                        self._last_monitor_log = 0
                    
                    if (time_module.time() - self._last_monitor_log) >= 30:
                        total_count = max(open_count_mt5, open_count_db)  # Usar el mayor
                        self.logger.info(
                            f"🔄 Monitoreando {total_count} posición(es) abierta(s) DEL DÍA ACTUAL "
                            f"(MT5: {open_count_mt5}, BD: {open_count_db}) - "
                            f"Priorizando monitoreo sobre análisis"
                        )
                        self._last_monitor_log = time_module.time()
                    
                    sleep_interval = 5  # Monitoreo más frecuente cuando hay posiciones
                    
                    # NO analizar mercado cuando hay posiciones abiertas (solo monitorear)
                    # El análisis se reanudará cuando se cierren todas las posiciones
                    if hasattr(self, '_last_analysis_with_positions'):
                        self._last_analysis_with_positions = time_module.time()
                    
                    # Saltar completamente el bloque de análisis - continuar al sleep (sleep_interval ya está configurado arriba)
                else:
                    # SOLO si NO hay posiciones abiertas: verificar si se debe cerrar el día operativo
                    # Verificar si se alcanzó el límite diario o si el primer TP cerró el día
                    # Obtener estrategia activa según el scheduler
                    strategy_name = self.strategy_scheduler.get_current_strategy()
                    strategy = self.strategy_manager.strategies.get(strategy_name)
                    
                    should_close_day = False
                    close_reason = ""
                    
                    if strategy:
                        # Verificar límite diario de trades desde BD
                        db_manager = strategy._get_db_manager()
                        if db_manager and db_manager.enabled:
                            for symbol in self.config.get('symbols', []):
                                # Verificar conteo de trades hoy
                                trades_today = db_manager.count_trades_today(strategy=strategy_name, symbol=symbol)
                                max_trades = strategy.max_trades_per_day
                                
                                if trades_today >= max_trades:
                                    should_close_day = True
                                    close_reason = f"Límite diario alcanzado ({trades_today}/{max_trades} trades)"
                                    break
                        
                        # Verificar si el primer TP cerró el día (solo si no se alcanzó el límite)
                        if not should_close_day and hasattr(strategy, '_check_first_trade_tp_closure'):
                            for symbol in self.config.get('symbols', []):
                                if strategy._check_first_trade_tp_closure(symbol):
                                    should_close_day = True
                                    close_reason = "Primer trade cerró con TP"
                                    break
                    
                    # Verificar si la estrategia funciona 24/7
                    is_24_7_strategy = False
                    if strategy and hasattr(strategy, 'is_24_7_strategy'):
                        is_24_7_strategy = strategy.is_24_7_strategy()
                    
                    # Si se debe cerrar el día, NO analizar mercado (excepto para estrategias 24/7)
                    if should_close_day and not is_24_7_strategy:
                        if not hasattr(self, '_last_day_closed_log'):
                            self._last_day_closed_log = 0
                        if (time_module.time() - self._last_day_closed_log) >= 300:  # Cada 5 minutos
                            self.logger.info(
                                f"⏸️  DÍA OPERATIVO CERRADO - {close_reason} - "
                                f"No se realizarán más operaciones hasta el próximo día operativo"
                            )
                            self._last_day_closed_log = time_module.time()
                        sleep_interval = 60  # Esperar 1 minuto antes de verificar de nuevo
                    elif is_24_7_strategy or self._is_trading_time():
                        # Estrategia 24/7 o está en horario operativo - analizar mercado
                        
                        # Para estrategias no-24/7: Verificar si es hora de cierre automático (4:50 PM NY)
                        if not is_24_7_strategy and self.position_monitor.auto_close_enabled and self.position_monitor.is_auto_close_time():
                            if not hasattr(self, '_last_auto_close_warning'):
                                self._last_auto_close_warning = 0
                            if (time_module.time() - self._last_auto_close_warning) >= 60:
                                self.logger.warning(
                                    f"🕐 HORA DE CIERRE AUTOMÁTICO (4:50 PM NY) - "
                                    f"NO se colocarán nuevas entradas - Solo monitoreando y cerrando posiciones abiertas"
                                )
                                self._last_auto_close_warning = time_module.time()
                            sleep_interval = 5  # Monitorear más frecuentemente para cerrar posiciones
                            continue  # Saltar análisis - solo monitorear y cerrar
                        
                        # Analizar mercado (para estrategias 24/7 siempre, para otras solo en horario operativo)
                        # Verificar ANTES de analizar si la estrategia necesita monitoreo intensivo
                        needs_intensive = self.strategy_manager.needs_intensive_monitoring(strategy_name)
                        
                        if needs_intensive:
                            # Modo monitoreo intensivo: analizar cada segundo
                            mode_msg = "24/7" if is_24_7_strategy else "Horario operativo"
                            self.logger.debug(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] 🔄 Modo monitoreo intensivo activo ({mode_msg}) - Analizando cada segundo...")
                            self._analyze_market()
                            sleep_interval = 1
                        else:
                            # Modo normal: analizar y esperar intervalo normal
                            mode_msg = "24/7" if is_24_7_strategy else "Horario operativo"
                            self.logger.info(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] ✅ {mode_msg} activo - Analizando mercado...")
                            self._analyze_market()
                            
                            # Verificar DESPUÉS de analizar si se activó monitoreo intensivo
                            if self.strategy_manager.needs_intensive_monitoring(strategy_name):
                                # Si se activó durante el análisis, usar intervalo corto
                                sleep_interval = 1
                                self.logger.info(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] 🔄 Monitoreo intensivo activado - Cambiando a intervalo de 1 segundo")
                            else:
                                # Verificar si la estrategia está esperando FVG (monitoreo intermedio)
                                strategy = self.strategy_manager.strategies.get(strategy_name)
                                if strategy and hasattr(strategy, '_waiting_for_fvg') and strategy._waiting_for_fvg:
                                    # Monitoreo intermedio: analizar cada 10 segundos cuando hay Turtle Soup pero no FVG
                                    sleep_interval = 10
                                    self.logger.debug(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] 🔄 Monitoreo intermedio activo (esperando FVG) - Analizando cada 10 segundos...")
                                else:
                                    # Modo normal: usar intervalo configurado (para 24/7 puede ser más corto)
                                    sleep_interval = 30 if is_24_7_strategy else 60
                    else:
                        # Fuera de horario operativo y no es estrategia 24/7
                        # Verificar si es por día no operativo o por hora
                        is_trading_day, day_reason, holidays = self.trading_hours.is_trading_day()
                        
                        if not is_trading_day:
                            # No es día operativo (fin de semana o feriado)
                            next_trading = self.trading_hours.get_next_trading_time()
                            time_until = self.trading_hours.get_time_until_trading()
                            self.logger.info(
                                f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] 🚫 {day_reason} - "
                                f"Próximo día operativo: {next_trading.strftime('%Y-%m-%d %H:%M')} ({time_until})"
                            )
                        else:
                            # Es día operativo pero fuera de horario
                            next_trading = self.trading_hours.get_next_trading_time()
                            time_until = self.trading_hours.get_time_until_trading()
                            self.logger.info(
                                f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] ⏸️  Fuera de horario operativo - "
                                f"Próximo horario: {next_trading.strftime('%H:%M')} ({time_until})"
                            )
                        sleep_interval = 60
                    
                    # Resetear contador cuando no hay posiciones
                    if hasattr(self, '_last_analysis_with_positions'):
                        self._last_analysis_with_positions = 0
                
                # Esperar antes de la siguiente iteración
                time_module.sleep(sleep_interval)
                
        except KeyboardInterrupt:
            self.logger.info("Bot detenido por el usuario")
        except Exception as e:
            self.logger.error(f"Error crítico en el bot: {e}", exc_info=True)
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Cierra conexiones y finaliza el bot"""
        self.logger.info("Cerrando conexiones...")
        if self.mt5_connected:
            mt5.shutdown()
            self.mt5_connected = False
        if self.db_manager:
            self.db_manager.close()
        self.logger.info("Bot finalizado correctamente")


def select_strategy_interactive(config_path: str = "config.yaml") -> str:
    """
    Muestra un menú interactivo para seleccionar la estrategia
    
    Args:
        config_path: Ruta al archivo de configuración
        
    Returns:
        Nombre de la estrategia seleccionada
    """
    # Cargar configuración para obtener estrategias disponibles
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Error al cargar configuración: {e}")
        return "turtle_soup_fvg"  # Default
    
    # Estrategias disponibles con descripciones
    strategies_info = {
        '1': {
            'name': 'turtle_soup_fvg',
            'description': 'Turtle Soup H4 + FVG (Sopa de Tortuga)'
        },
        '2': {
            'name': 'crt_strategy',
            'description': 'CRT Strategy (Detecta automáticamente: Revisión, Continuación o Extremo)'
        },
        '3': {
            'name': 'default',
            'description': 'Default Strategy (Estrategia por defecto)'
        },
        '4': {
            'name': 'daily_levels_sweep',
            'description': 'Daily Levels Sweep (Barrido de Niveles Diarios - 24/7)'
        }
    }
    
    # Obtener estrategia actual del config
    current_strategy = config.get('strategy', {}).get('name', 'turtle_soup_fvg')
    
    print("\n" + "=" * 60)
    print("🤖 BOT DE TRADING - Selección de Estrategia")
    print("=" * 60)
    print(f"\n📋 Estrategia actual en config: {current_strategy}")
    print("\nEstrategias disponibles:")
    print("-" * 60)
    print("  📌 RECOMENDADO: Opción 2 (CRT Strategy) detecta automáticamente")
    print("     cualquiera de los 3 tipos: Revisión, Continuación o Extremo")
    print("-" * 60)
    
    for key, info in strategies_info.items():
        marker = " ← ACTUAL" if info['name'] == current_strategy else ""
        print(f"  {key}. {info['description']}{marker}")
    
    print("-" * 60)
    print("  0. Usar estrategia del config (no cambiar)")
    print("=" * 60)
    
    while True:
        try:
            choice = input("\n👉 Selecciona una opción (0-4): ").strip()
            
            if choice == '0':
                # Usar la estrategia del config sin cambiar
                print(f"✅ Usando estrategia del config: {current_strategy}")
                return current_strategy
            
            if choice in strategies_info:
                selected = strategies_info[choice]
                print(f"✅ Estrategia seleccionada: {selected['description']}")
                
                # Actualizar el config con la estrategia seleccionada
                if 'strategy' not in config:
                    config['strategy'] = {}
                config['strategy']['name'] = selected['name']
                
                # Guardar el config actualizado
                try:
                    with open(config_path, 'w', encoding='utf-8') as f:
                        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                    print(f"💾 Configuración actualizada en {config_path}")
                except Exception as e:
                    print(f"⚠️  Advertencia: No se pudo guardar la configuración: {e}")
                    print(f"   La estrategia se usará solo para esta sesión")
                
                return selected['name']
            else:
                print("❌ Opción inválida. Por favor selecciona un número del 0 al 4.")
        except KeyboardInterrupt:
            print("\n\n⚠️  Operación cancelada. Usando estrategia del config.")
            return current_strategy
        except Exception as e:
            print(f"❌ Error: {e}. Intenta de nuevo.")


if __name__ == "__main__":
    # Mostrar menú de selección de estrategia
    selected_strategy = select_strategy_interactive()
    
    # Inicializar y ejecutar el bot
    bot = TradingBot()
    bot.run()

