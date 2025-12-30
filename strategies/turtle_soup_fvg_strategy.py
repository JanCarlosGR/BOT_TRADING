"""
Estrategia Turtle Soup H4 + FVG
Combina detección de Turtle Soup en H4 con entradas basadas en FVG
"""

import logging
from typing import Optional, Dict
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, date
import time

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy_manager import BaseStrategy
from Base.turtle_soup_detector import detect_turtle_soup_h4
from Base.fvg_detector import detect_fvg
from Base.news_checker import can_trade_now
from Base.order_executor import OrderExecutor
from Base.candle_reader import get_candle


class TurtleSoupFVGStrategy(BaseStrategy):
    """
    Estrategia Turtle Soup H4 + FVG
    
    Lógica:
    1. Detecta Turtle Soup en H4 (barridos de 1 AM, 5 AM, 9 AM)
    2. Define TP basado en extremo opuesto
    3. Verifica noticias de alto impacto
    4. Busca entrada en FVG contrario al barrido
    5. Ejecuta orden con RR mínimo 1:2
    """
    
    def __init__(self, config: Dict):
        """
        Inicializa la estrategia
        
        Args:
            config: Configuración del bot
        """
        super().__init__(config)
        self.executor = OrderExecutor()
        
        # Configuración de la estrategia
        strategy_config = config.get('strategy_config', {})
        self.entry_timeframe = strategy_config.get('entry_timeframe', 'M5')  # M1 o M5
        self.min_rr = strategy_config.get('min_rr', 2.0)  # Risk/Reward mínimo
        
        # Configuración de gestión de riesgo
        risk_config = config.get('risk_management', {})
        self.risk_per_trade_percent = risk_config.get('risk_per_trade_percent', 1.0)  # Porcentaje de riesgo por trade
        self.max_trades_per_day = risk_config.get('max_trades_per_day', 2)  # Máximo de trades por día
        self.max_position_size = risk_config.get('max_position_size', 0.1)  # Límite de seguridad
        
        # Contador de trades por día
        self.trades_today = 0
        self.last_trade_date = None
        
        # Frecuencia de evaluación según timeframe
        if self.entry_timeframe == 'M1':
            self.evaluation_interval = 30  # 30 segundos
        else:
            self.evaluation_interval = 60  # 1 minuto
        
        # Estado de la estrategia
        self.turtle_soup_signal = None
        self.last_news_check = None
        self.last_evaluation = None
        
        # Estado de monitoreo intensivo de FVG
        self.monitoring_fvg = False  # Indica si estamos monitoreando un FVG en tiempo real
        self.monitoring_fvg_data = None  # Datos del FVG que estamos monitoreando (turtle_soup, fvg_info)
        
        self.logger.info(f"TurtleSoupFVGStrategy inicializada - Entry: {self.entry_timeframe}, RR: {self.min_rr}")
        self.logger.info(f"Riesgo por trade: {self.risk_per_trade_percent}% | Máximo trades/día: {self.max_trades_per_day}")
    
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        """
        Analiza el mercado y genera señales de trading
        
        Args:
            symbol: Símbolo a analizar
            rates: Array de velas OHLCV
            
        Returns:
            Dict con señal de trading o None
        """
        try:
            # ⚠️ VERIFICACIÓN TEMPRANA: Si ya se alcanzó el límite de trades, detener análisis
            self._reset_daily_trades_counter()
            if self.trades_today >= self.max_trades_per_day:
                # Solo loguear una vez cada minuto para no saturar
                if not hasattr(self, '_last_limit_log') or (time.time() - self._last_limit_log) >= 60:
                    self.logger.info(
                        f"[{symbol}] ⏸️  Límite de trades diarios alcanzado: {self.trades_today}/{self.max_trades_per_day} | "
                        f"Análisis detenido hasta próxima sesión operativa"
                    )
                    self._last_limit_log = time.time()
                return None
            
            # Si estamos en modo monitoreo intensivo, evaluar condiciones del FVG
            if self.monitoring_fvg and self.monitoring_fvg_data:
                return self._monitor_fvg_intensive(symbol)
            
            # 1. Verificar noticias de alto impacto (5 min antes/después)
            self.logger.info(f"[{symbol}] 📰 Etapa 1/4: Verificando noticias económicas...")
            if not self._check_news(symbol):
                return None
            self.logger.info(f"[{symbol}] ✅ Etapa 1/4: Noticias OK - Puede operar")
            
            # 2. Detectar Turtle Soup en H4
            self.logger.info(f"[{symbol}] 🔍 Etapa 2/4: Buscando Turtle Soup en H4...")
            turtle_soup = detect_turtle_soup_h4(symbol)
            
            if not turtle_soup or not turtle_soup.get('detected'):
                self.turtle_soup_signal = None
                # Si estaba monitoreando, cancelar monitoreo
                if self.monitoring_fvg:
                    self.logger.info(f"[{symbol}] ⏸️  Turtle Soup desapareció - Cancelando monitoreo intensivo")
                    self.monitoring_fvg = False
                    self.monitoring_fvg_data = None
                # Cancelar también monitoreo intermedio
                if hasattr(self, '_waiting_for_fvg'):
                    self._waiting_for_fvg = False
                self.logger.info(f"[{symbol}] ⏸️  Etapa 2/4: Esperando - No hay Turtle Soup detectado en H4")
                return None
            
            # Guardar señal de Turtle Soup
            self.turtle_soup_signal = turtle_soup
            
            self.logger.info(
                f"[{symbol}] ✅ Etapa 2/4 COMPLETA: Turtle Soup detectado - {turtle_soup['sweep_type']} | "
                f"Barrido: {turtle_soup['swept_candle']} | "
                f"TP: {turtle_soup['target_price']:.5f} | "
                f"Dirección: {turtle_soup['direction']}"
            )
            
            # 3. Buscar entrada en FVG contrario al barrido
            self.logger.info(f"[{symbol}] 🔍 Etapa 3/4: Buscando entrada en FVG ({self.entry_timeframe})...")
            entry_signal = self._find_fvg_entry(symbol, turtle_soup)
            
            if entry_signal:
                # 4. Ejecutar orden
                # Cancelar monitoreo intermedio si estaba activo
                if hasattr(self, '_waiting_for_fvg'):
                    self._waiting_for_fvg = False
                self.logger.info(f"[{symbol}] 💹 Etapa 4/4: Ejecutando orden...")
                return self._execute_order(symbol, turtle_soup, entry_signal)
            else:
                # Verificar si hay un FVG esperado para activar monitoreo intensivo
                fvg = detect_fvg(symbol, self.entry_timeframe)
                if fvg and self._is_expected_fvg(fvg, turtle_soup):
                    # Activar monitoreo intensivo solo si no está ya activo
                    if not self.monitoring_fvg:
                        self.logger.info(f"[{symbol}] {'='*70}")
                        self.logger.info(f"[{symbol}] 🔄 FVG ESPERADO DETECTADO - ACTIVANDO MONITOREO INTENSIVO")
                        self.logger.info(f"[{symbol}] {'='*70}")
                        self.logger.info(f"[{symbol}] 📊 FVG {fvg.get('fvg_type')} detectado: {fvg.get('fvg_bottom', 0):.5f} - {fvg.get('fvg_top', 0):.5f}")
                        self.logger.info(f"[{symbol}] 📊 Estado FVG: {fvg.get('status')} | Entró: {fvg.get('entered_fvg')} | Salió: {fvg.get('exited_fvg')}")
                        self.logger.info(f"[{symbol}] 🔄 El bot ahora analizará cada SEGUNDO evaluando:")
                        self.logger.info(f"[{symbol}]    • Si las 3 velas forman el FVG esperado")
                        self.logger.info(f"[{symbol}]    • Si la vela EN FORMACIÓN entró al FVG (HIGH para BAJISTA, LOW para ALCISTA)")
                        self.logger.info(f"[{symbol}]    • Si el precio actual salió del FVG en la dirección correcta")
                        self.logger.info(f"[{symbol}] {'='*70}")
                        self.monitoring_fvg = True
                        self.monitoring_fvg_data = {
                            'turtle_soup': turtle_soup,
                            'fvg': fvg
                        }
                    else:
                        # Actualizar datos del FVG si ya está monitoreando
                        self.monitoring_fvg_data['fvg'] = fvg
                        self.monitoring_fvg_data['turtle_soup'] = turtle_soup
                        # Log cada 10 segundos para no saturar
                        if not hasattr(self, '_last_fvg_update_log') or (time.time() - self._last_fvg_update_log) >= 10:
                            self.logger.debug(f"[{symbol}] 🔄 Monitoreando FVG en tiempo real... Estado: {fvg.get('status')}")
                            self._last_fvg_update_log = time.time()
                else:
                    # Si estaba monitoreando pero el FVG desapareció o no es el esperado, cancelar monitoreo
                    if self.monitoring_fvg:
                        self.logger.info(f"[{symbol}] ⏸️  FVG esperado desapareció o cambió - Cancelando monitoreo intensivo")
                        self.monitoring_fvg = False
                        self.monitoring_fvg_data = None
                
                # Cuando hay Turtle Soup pero no hay FVG, activar monitoreo intermedio
                # Esto permite detectar FVG más rápido sin saturar con logs
                if not self.monitoring_fvg:
                    # Activar monitoreo intermedio (cada 5-10 segundos) cuando hay Turtle Soup pero no FVG
                    if not hasattr(self, '_waiting_for_fvg') or not self._waiting_for_fvg:
                        self._waiting_for_fvg = True
                        self.logger.info(f"[{symbol}] ⏳ Turtle Soup detectado pero sin FVG - Activando monitoreo intermedio")
                        self.logger.info(f"[{symbol}]    • El bot analizará cada 10 segundos buscando FVG {self.entry_timeframe}")
                        self.logger.info(f"[{symbol}]    • Turtle Soup: {turtle_soup['sweep_type']} | TP: {turtle_soup['target_price']:.5f} | Dirección: {turtle_soup['direction']}")
                        self.logger.info(f"[{symbol}]    • Esperando FVG {'BAJISTA' if turtle_soup['direction'] == 'BEARISH' else 'ALCISTA'} en {self.entry_timeframe}")
                    
                    # Log periódico cada 30 segundos para indicar que sigue esperando
                    current_time = time.time()
                    if not hasattr(self, '_last_waiting_log') or (current_time - self._last_waiting_log) >= 30:
                        self.logger.info(f"[{symbol}] ⏸️  Etapa 3/4: Esperando FVG válida - Turtle Soup activo, buscando FVG en {self.entry_timeframe}...")
                        self._last_waiting_log = current_time
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error en análisis: {e}", exc_info=True)
            return None
    
    def needs_intensive_monitoring(self) -> bool:
        """
        Indica si la estrategia necesita monitoreo intensivo (cada segundo)
        
        Returns:
            True si necesita monitoreo intensivo, False si usa intervalo normal
        """
        return self.monitoring_fvg
    
    def has_reached_daily_limit(self) -> bool:
        """
        Verifica si se ha alcanzado el límite de trades diarios
        
        Returns:
            True si se alcanzó el límite, False si aún se pueden ejecutar trades
        """
        self._reset_daily_trades_counter()
        return self.trades_today >= self.max_trades_per_day
    
    def _price_to_pips(self, price_diff: float, digits: int) -> float:
        """
        Convierte una diferencia de precio a pips
        
        Args:
            price_diff: Diferencia de precio (ej: 0.00025)
            digits: Número de dígitos del símbolo (5 para EURUSD, 3 para USDJPY)
            
        Returns:
            Diferencia en pips
        """
        # Para símbolos con 5 dígitos: 1 pip = 0.00010 = 10 points
        # Para símbolos con 3 dígitos: 1 pip = 0.01 = 1 point
        if digits == 5:
            return price_diff * 10000  # Multiplicar por 10000 para convertir a pips
        elif digits == 3:
            return price_diff * 100  # Multiplicar por 100 para convertir a pips
        else:
            # Por defecto, asumir 5 dígitos
            return price_diff * 10000
    
    def _is_expected_fvg(self, fvg: Dict, turtle_soup: Dict) -> bool:
        """
        Verifica si un FVG es el esperado según el Turtle Soup
        
        Args:
            fvg: Información del FVG
            turtle_soup: Información del Turtle Soup
            
        Returns:
            True si el FVG es el esperado
        """
        try:
            sweep_type = turtle_soup.get('sweep_type')
            direction = turtle_soup.get('direction')
            fvg_type = fvg.get('fvg_type')
            
            # Determinar qué tipo de FVG buscamos según el barrido de H4
            expected_fvg_type = None
            if sweep_type == 'BULLISH_SWEEP' and direction == 'BEARISH':
                expected_fvg_type = 'BAJISTA'
            elif sweep_type == 'BEARISH_SWEEP' and direction == 'BULLISH':
                expected_fvg_type = 'ALCISTA'
            
            return expected_fvg_type is not None and fvg_type == expected_fvg_type
        except:
            return False
    
    def _monitor_fvg_intensive(self, symbol: str) -> Optional[Dict]:
        """
        Monitorea el FVG en tiempo real (cada segundo) hasta que se cumplan condiciones o expire
        
        Args:
            symbol: Símbolo a monitorear
            
        Returns:
            Dict con señal de trading si se cumplen condiciones, None si sigue monitoreando
        """
        try:
            if not self.monitoring_fvg_data:
                self.monitoring_fvg = False
                return None
            
            turtle_soup = self.monitoring_fvg_data.get('turtle_soup')
            if not turtle_soup:
                self.monitoring_fvg = False
                self.monitoring_fvg_data = None
                return None
            
            # Verificar que el Turtle Soup aún existe
            current_turtle_soup = detect_turtle_soup_h4(symbol)
            if not current_turtle_soup or not current_turtle_soup.get('detected'):
                self.logger.info(f"[{symbol}] ⏸️  Turtle Soup desapareció durante monitoreo - Cancelando")
                self.monitoring_fvg = False
                self.monitoring_fvg_data = None
                return None
            
            # Verificar que el FVG aún existe y es el esperado
            fvg = detect_fvg(symbol, self.entry_timeframe)
            if not fvg or not self._is_expected_fvg(fvg, turtle_soup):
                self.logger.info(f"[{symbol}] ⏸️  FVG esperado desapareció durante monitoreo - Cancelando")
                self.monitoring_fvg = False
                self.monitoring_fvg_data = None
                return None
            
            # Actualizar datos del FVG
            self.monitoring_fvg_data['fvg'] = fvg
            
            # Obtener precio actual para verificar estado
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                self.logger.error(f"[{symbol}] ❌ No se pudo obtener precio actual durante monitoreo")
                return None
            
            current_price = float(tick.bid)
            fvg_bottom = fvg.get('fvg_bottom')
            fvg_top = fvg.get('fvg_top')
            fvg_type = fvg.get('fvg_type')
            direction = turtle_soup.get('direction')
            
            # Verificar si el precio está dentro del FVG
            price_inside_fvg = (fvg_bottom <= current_price <= fvg_top) if fvg_bottom and fvg_top else False
            
            # Si el precio está dentro del FVG, esperar a que salga en la dirección esperada
            if price_inside_fvg:
                # Log cada 10 segundos para no saturar
                import time
                current_time = time.time()
                if not hasattr(self, '_last_inside_fvg_log') or (current_time - self._last_inside_fvg_log) >= 10:
                    # Determinar dirección esperada de salida
                    expected_exit = None
                    if fvg_type == 'BAJISTA' and direction == 'BEARISH':
                        expected_exit = "DEBAJO"
                    elif fvg_type == 'ALCISTA' and direction == 'BULLISH':
                        expected_exit = "ARRIBA"
                    
                    self.logger.info(
                        f"[{symbol}] ⏳ MONITOREO INTENSIVO: Precio DENTRO del FVG {fvg_type} | "
                        f"Precio actual: {current_price:.5f} | FVG: {fvg_bottom:.5f}-{fvg_top:.5f} | "
                        f"Esperando salida hacia {expected_exit} en dirección {direction}"
                    )
                    self._last_inside_fvg_log = current_time
                # NO intentar ejecutar orden mientras el precio está dentro
                return None
            
            # El precio está fuera del FVG - evaluar condiciones de entrada
            entry_signal = self._find_fvg_entry(symbol, turtle_soup)
            
            if entry_signal:
                # Condiciones cumplidas - ejecutar orden y cancelar monitoreo
                self.logger.info(f"[{symbol}] ✅ Condiciones cumplidas durante monitoreo intensivo - Precio salió del FVG en dirección esperada - Ejecutando orden")
                self.monitoring_fvg = False
                self.monitoring_fvg_data = None
                return self._execute_order(symbol, turtle_soup, entry_signal)
            
            # El precio salió del FVG pero no en la dirección esperada, o condiciones no cumplidas
            # Log cada 10 segundos para no saturar
            import time
            current_time = time.time()
            if not hasattr(self, '_last_monitor_log') or (current_time - self._last_monitor_log) >= 10:
                self.logger.debug(
                    f"[{symbol}] 🔄 Monitoreando FVG en tiempo real... "
                    f"(Estado: {fvg.get('status')}, Entró: {fvg.get('entered_fvg')}, Salió: {fvg.get('exited_fvg')}, "
                    f"Precio: {current_price:.5f})"
                )
                self._last_monitor_log = current_time
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error en monitoreo intensivo: {e}", exc_info=True)
            self.monitoring_fvg = False
            self.monitoring_fvg_data = None
            return None
    
    def _reset_daily_trades_counter(self):
        """Resetea el contador de trades si es un nuevo día"""
        today = date.today()
        if self.last_trade_date != today:
            if self.last_trade_date is not None:
                self.logger.info(f"🔄 Nuevo día - Reseteando contador de trades (anterior: {self.trades_today})")
            self.trades_today = 0
            self.last_trade_date = today
    
    def _check_daily_trade_limit(self, symbol: str) -> bool:
        """
        Verifica si se puede ejecutar un trade según el límite diario
        
        Esta verificación incluye:
        1. Límite de trades por día (max_trades_per_day) - desde base de datos
        2. Posiciones abiertas (no permite nueva entrada si hay una posición activa)
        3. Cierre de día por primer TP (si la primera entrada cerró con TP, no colocar más órdenes)
        
        Args:
            symbol: Símbolo a verificar
            
        Returns:
            True si se puede ejecutar, False si hay algún bloqueo
        """
        # 3. Verificar si el primer trade del día cerró con TP (cerrar día operativo)
        if self._check_first_trade_tp_closure(symbol):
            return False
        
        # 1. Verificar límite de trades diarios desde base de datos
        db_manager = self._get_db_manager()
        if db_manager.enabled:
            # Obtener conteo desde BD (más confiable)
            strategy_name = 'turtle_soup_fvg'  # Nombre de esta estrategia
            trades_today_db = db_manager.count_trades_today(strategy=strategy_name)
            if trades_today_db >= self.max_trades_per_day:
                self.logger.info(f"[{symbol}] ⏸️  Límite de trades diarios alcanzado (desde BD): {trades_today_db}/{self.max_trades_per_day}")
                # Actualizar contador local para consistencia
                self.trades_today = trades_today_db
                return False
            # Actualizar contador local
            self.trades_today = trades_today_db
        else:
            # Si BD no está disponible, usar contador local
            self._reset_daily_trades_counter()
            if self.trades_today >= self.max_trades_per_day:
                self.logger.info(f"[{symbol}] ⏸️  Límite de trades diarios alcanzado: {self.trades_today}/{self.max_trades_per_day}")
                return False
        
        # 2. Verificar si hay posiciones abiertas (no permitir nueva entrada mientras hay posición activa)
        if self._has_open_positions(symbol):
            return False
        
        return True
    
    def _calculate_volume_by_risk(self, symbol: str, entry_price: float, stop_loss: float) -> Optional[float]:
        """
        Calcula el volumen basado en el riesgo porcentual de la cuenta
        
        Args:
            symbol: Símbolo a operar
            entry_price: Precio de entrada
            stop_loss: Precio de stop loss
            
        Returns:
            Volumen calculado en lotes o None si hay error
        """
        try:
            # Obtener información de la cuenta
            account_info = mt5.account_info()
            if account_info is None:
                self.logger.error("No se pudo obtener información de la cuenta")
                return None
            
            balance = account_info.balance
            equity = account_info.equity if hasattr(account_info, 'equity') else balance
            margin_free = account_info.margin_free if hasattr(account_info, 'margin_free') else balance
            
            if balance <= 0:
                self.logger.error(f"[{symbol}] ❌ Balance inválido: {balance}")
                return None
            
            # Obtener información del símbolo
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                self.logger.error(f"[{symbol}] No se pudo obtener información del símbolo {symbol}")
                return None
            
            # Calcular el riesgo en dinero
            risk_amount = balance * (self.risk_per_trade_percent / 100.0)
            
            # Validar que el balance sea suficiente para el riesgo
            # El balance debe ser al menos 2x el riesgo para tener margen de seguridad
            min_balance_required = risk_amount * 2
            if balance < min_balance_required:
                self.logger.error(
                    f"[{symbol}] ❌ Balance insuficiente: Balance={balance:.2f} | "
                    f"Riesgo calculado={risk_amount:.2f} | Mínimo requerido={min_balance_required:.2f}"
                )
                return None
            
            # Validar que haya margen libre suficiente
            # Necesitamos al menos el riesgo + un margen adicional para el margen de la posición
            # Estimación conservadora: necesitamos al menos 3x el riesgo en margen libre
            min_margin_required = risk_amount * 3
            if margin_free < min_margin_required:
                self.logger.error(
                    f"[{symbol}] ❌ Margen libre insuficiente: Margen libre={margin_free:.2f} | "
                    f"Mínimo requerido={min_margin_required:.2f} | Equity={equity:.2f}"
                )
                return None
            
            self.logger.debug(
                f"[{symbol}] ✅ Validación de balance: Balance={balance:.2f} | "
                f"Equity={equity:.2f} | Margen libre={margin_free:.2f} | "
                f"Riesgo={risk_amount:.2f} ({self.risk_per_trade_percent}%)"
            )
            
            # Calcular el riesgo en precio (distancia del SL al entry)
            risk_in_price = abs(entry_price - stop_loss)
            
            if risk_in_price == 0:
                self.logger.error("El riesgo en precio es 0, no se puede calcular volumen")
                return None
            
            # Obtener información del símbolo para calcular el valor del pip
            tick_size = symbol_info.trade_tick_size  # Tamaño del tick (ej: 0.00001 para EURUSD)
            tick_value = symbol_info.trade_tick_value  # Valor del tick en la moneda de la cuenta
            
            # Calcular el valor del riesgo por lote
            # Fórmula: Volumen = Riesgo_en_dinero / (Riesgo_en_precio * Valor_del_tick_por_lote)
            # Donde: Valor_del_tick_por_lote = tick_value / tick_size (para 1 lote estándar)
            
            if tick_size > 0 and tick_value > 0:
                # Calcular cuántos ticks hay en el riesgo en precio
                ticks_in_risk = risk_in_price / tick_size
                
                # El tick_value en MT5 es el valor de 1 tick para 1 lote estándar
                # Valor del riesgo por lote = ticks_in_risk * tick_value
                risk_value_per_lot = ticks_in_risk * tick_value
                
                self.logger.debug(f"[{symbol}] Cálculo detallado: ticks_in_risk={ticks_in_risk:.2f}, tick_value={tick_value}, risk_value_per_lot={risk_value_per_lot:.2f}")
                
                if risk_value_per_lot > 0:
                    # Volumen = riesgo_en_dinero / riesgo_por_lote
                    volume = risk_amount / risk_value_per_lot
                    self.logger.debug(f"[{symbol}] Volumen calculado antes de normalizar: {volume:.4f} lotes")
                else:
                    self.logger.error("No se pudo calcular el valor del riesgo por lote")
                    return None
            else:
                # Fallback: usar fórmula simplificada para forex estándar
                # Asumir que 1 pip = 0.0001 y valor del pip = $10 por lote (para cuentas en USD)
                # Esto es una aproximación y puede no ser exacta para todos los pares
                pips_in_risk = risk_in_price / 0.0001
                # Obtener la moneda de la cuenta para ajustar el valor del pip
                account_info = mt5.account_info()
                account_currency = account_info.currency if account_info else "USD"
                
                # Valor aproximado del pip por lote (esto varía según el par y la moneda de la cuenta)
                # Para la mayoría de pares mayores con cuenta en USD: ~$10 por pip por lote
                value_per_pip_per_lot = 10.0
                risk_value_per_lot = pips_in_risk * value_per_pip_per_lot
                
                if risk_value_per_lot > 0:
                    volume = risk_amount / risk_value_per_lot
                    self.logger.warning(f"[{symbol}] Usando cálculo aproximado de volumen (fallback)")
                else:
                    self.logger.error("No se pudo calcular el volumen con método fallback")
                    return None
            
            # Normalizar volumen según los límites del símbolo
            volume_step = symbol_info.volume_step
            volume_min = symbol_info.volume_min
            volume_max = symbol_info.volume_max
            
            # Redondear al step más cercano (hacia arriba para asegurar que no sea menor)
            volume_before_limit = volume
            if volume_step > 0:
                volume = round(volume / volume_step) * volume_step
                # Si después de redondear es menor al mínimo, usar el mínimo
                if volume < volume_min:
                    volume = volume_min
                    # Advertencia si el volumen calculado era mucho menor al mínimo
                    if volume_before_limit < volume_min * 0.5:
                        self.logger.warning(
                            f"[{symbol}] ⚠️  Volumen calculado ({volume_before_limit:.4f}) es menor al mínimo ({volume_min}). "
                            f"Usando mínimo, pero el riesgo real será menor al {self.risk_per_trade_percent}% configurado"
                        )
            else:
                # Si no hay step definido, usar el mínimo si es necesario
                if volume < volume_min:
                    if volume < volume_min * 0.5:
                        self.logger.warning(
                            f"[{symbol}] ⚠️  Volumen calculado ({volume:.4f}) es menor al mínimo ({volume_min}). "
                            f"Usando mínimo, pero el riesgo real será menor al {self.risk_per_trade_percent}% configurado"
                        )
                    volume = volume_min
            
            # Aplicar límite máximo del símbolo
            if volume > volume_max:
                volume = volume_max
                self.logger.warning(f"[{symbol}] ⚠️  Volumen calculado excede el máximo del símbolo ({volume_max}), usando máximo")
            
            # Aplicar límite de seguridad de la configuración (solo como advertencia, no como límite restrictivo)
            # El volumen se calcula basado en el 1% de riesgo, por lo que no debe limitarse arbitrariamente
            if volume > self.max_position_size:
                # Si el volumen calculado es mayor al límite, loguear advertencia pero permitir el volumen calculado
                # El límite max_position_size es solo una referencia de seguridad, no un límite absoluto
                self.logger.info(
                    f"[{symbol}] ℹ️  Volumen calculado ({volume:.2f}) es mayor al límite de referencia ({self.max_position_size}), "
                    f"pero se usa el volumen calculado para respetar el {self.risk_per_trade_percent}% de riesgo configurado"
                )
                # NO limitar el volumen - usar el calculado para respetar el % de riesgo
            
            # Verificar que el volumen final sea válido
            if volume < volume_min:
                self.logger.error(f"[{symbol}] ❌ Volumen calculado ({volume:.4f}) es menor al mínimo permitido ({volume_min})")
                return None
            
            # Calcular el riesgo real que se está tomando con el volumen calculado
            if tick_size > 0 and tick_value > 0:
                ticks_in_risk = risk_in_price / tick_size
                risk_value_actual = ticks_in_risk * tick_value * volume
                risk_percent_actual = (risk_value_actual / balance) * 100
            else:
                pips_in_risk = risk_in_price / 0.0001
                risk_value_actual = pips_in_risk * 10.0 * volume
                risk_percent_actual = (risk_value_actual / balance) * 100
            
            self.logger.info(
                f"[{symbol}] 💰 Cálculo de volumen por riesgo: "
                f"Balance={balance:.2f} | Riesgo objetivo={self.risk_per_trade_percent}%={risk_amount:.2f} | "
                f"Risk en precio={risk_in_price:.5f} | Volumen={volume:.2f} lotes | "
                f"Riesgo real={risk_percent_actual:.2f}%={risk_value_actual:.2f}"
            )
            
            # Advertencia si el riesgo real es muy diferente al objetivo
            if abs(risk_percent_actual - self.risk_per_trade_percent) > 0.1:
                self.logger.warning(
                    f"[{symbol}] ⚠️  Diferencia entre riesgo objetivo ({self.risk_per_trade_percent}%) y real ({risk_percent_actual:.2f}%) "
                    f"puede deberse a límites de volumen mínimo/máximo"
                )
            
            return volume
            
        except Exception as e:
            self.logger.error(f"Error al calcular volumen por riesgo: {e}", exc_info=True)
            return None
    
    def _check_news(self, symbol: str) -> bool:
        """
        Verifica si se puede operar según noticias (5 min antes/después)
        
        Args:
            symbol: Símbolo a verificar
            
        Returns:
            True si se puede operar, False si hay noticia cercana
        """
        try:
            can_trade, reason, next_news = can_trade_now(symbol, minutes_before=5, minutes_after=5)
            
            if not can_trade:
                if next_news:
                    self.logger.info(f"[{symbol}] ⏸️  Bloqueado por noticias: {reason} | Próxima noticia: {next_news.get('title', 'N/A')} a las {next_news.get('time_str', 'N/A')}")
                else:
                    self.logger.info(f"[{symbol}] ⏸️  Bloqueado por noticias: {reason}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error al verificar noticias: {e}")
            return False
    
    def _find_fvg_entry(self, symbol: str, turtle_soup: Dict) -> Optional[Dict]:
        """
        Busca entrada en FVG contrario a la dirección del barrido
        
        Args:
            symbol: Símbolo
            turtle_soup: Información del Turtle Soup detectado
            
        Returns:
            Dict con señal de entrada o None
        """
        try:
            # Detectar FVG en la temporalidad de entrada
            fvg = detect_fvg(symbol, self.entry_timeframe)
            
            if not fvg:
                self.logger.info(f"[{symbol}] ⏸️  Esperando: No hay FVG detectado en {self.entry_timeframe}")
                return None
            
            sweep_type = turtle_soup.get('sweep_type')
            direction = turtle_soup.get('direction')
            fvg_type = fvg.get('fvg_type')
            
            # Verificar si el FVG es el esperado según el Turtle Soup
            if not self._is_expected_fvg(fvg, turtle_soup):
                self.logger.info(f"[{symbol}] ⏸️  FVG detectado ({fvg_type}) no es el esperado según Turtle Soup ({sweep_type} → {direction})")
                return None
            
            exit_direction = fvg.get('exit_direction')
            fvg_bottom = fvg.get('fvg_bottom')
            fvg_top = fvg.get('fvg_top')
            current_price_fvg = fvg.get('current_price')
            self.logger.info(f"[{symbol}] 📊 FVG ESPERADO detectado: {fvg_type} | Estado: {fvg.get('status')} | Entró: {fvg.get('entered_fvg')} | Salió: {fvg.get('exited_fvg')} | Exit Direction: {exit_direction}")
            self.logger.info(f"[{symbol}] 📊 FVG detalles: Bottom={fvg_bottom:.5f} | Top={fvg_top:.5f} | Precio actual={current_price_fvg:.5f}")
            
            # ⚠️ VALIDACIÓN CRÍTICA: Verificar que la VELA EN FORMACIÓN (junto con las 2 anteriores) formen el FVG esperado
            # REGLA OBLIGATORIA: 
            # 1. Las 3 velas (en formación + 2 anteriores) DEBEN formar el FVG esperado
            # 2. La VELA EN FORMACIÓN (posición 0) DEBE haber entrado al FVG y salido en la dirección esperada
            self.logger.info(f"[{symbol}] 🔍 Validando regla crítica: Vela EN FORMACIÓN + 2 anteriores deben formar FVG esperado...")
            
            # Obtener las 3 velas: vela en formación (posición 0) + 2 anteriores (posición 1 y 2)
            # Mapeo de timeframe
            timeframe_map = {
                'M1': mt5.TIMEFRAME_M1,
                'M5': mt5.TIMEFRAME_M5,
                'M15': mt5.TIMEFRAME_M15,
                'M30': mt5.TIMEFRAME_M30,
                'H1': mt5.TIMEFRAME_H1,
                'H4': mt5.TIMEFRAME_H4,
                'D1': mt5.TIMEFRAME_D1,
            }
            tf = timeframe_map.get(self.entry_timeframe.upper(), mt5.TIMEFRAME_M5)
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, 3)  # Obtener 3 velas: actual (pos 0), anterior1 (pos 1), anterior2 (pos 2)
            
            if rates is None or len(rates) < 3:
                self.logger.error(f"[{symbol}] ❌ No se pudo obtener las 3 velas necesarias (necesitamos vela en formación + 2 anteriores)")
                return None
            
            # Estructura: rates[0] = vela3 (en formación/actual), rates[1] = vela2 (anterior), rates[2] = vela1 (más antigua)
            # Ordenar por tiempo para tener: vela1 (más antigua), vela2 (del medio), vela3 (actual/en formación)
            candles_data = []
            for i, candle_data in enumerate(rates):
                candles_data.append({
                    'open': float(candle_data['open']),
                    'high': float(candle_data['high']),
                    'low': float(candle_data['low']),
                    'close': float(candle_data['close']),
                    'time': datetime.fromtimestamp(candle_data['time']),
                    'index': i  # Guardar índice original
                })
            
            # Ordenar por tiempo (más antigua primero)
            candles_data = sorted(candles_data, key=lambda x: x['time'])
            
            # vela1 = más antigua, vela2 = del medio, vela3 = actual/en formación
            vela1 = candles_data[0]  # Más antigua
            vela2 = candles_data[1]    # Del medio
            vela3 = candles_data[2]    # Actual/en formación
            
            self.logger.info(f"[{symbol}] 📊 Analizando 3 velas para formar FVG:")
            self.logger.info(f"[{symbol}]    • Vela1 (antigua): {vela1['time'].strftime('%Y-%m-%d %H:%M:%S')} | H={vela1['high']:.5f} L={vela1['low']:.5f}")
            self.logger.info(f"[{symbol}]    • Vela2 (medio): {vela2['time'].strftime('%Y-%m-%d %H:%M:%S')} | H={vela2['high']:.5f} L={vela2['low']:.5f}")
            self.logger.info(f"[{symbol}]    • Vela3 (EN FORMACIÓN): {vela3['time'].strftime('%Y-%m-%d %H:%M:%S')} | H={vela3['high']:.5f} L={vela3['low']:.5f} C={vela3['close']:.5f}")
            
            # VALIDACIÓN 0: Verificar que las 3 velas forman el FVG esperado
            # Según la lógica del detector FVG:
            # - FVG ALCISTA: vela1.low < vela3.high AND vela3.low > vela1.high (sin solapamiento)
            #   Rango: entre vela1.high (bottom) y vela3.low (top)
            # - FVG BAJISTA: vela1.high > vela3.low AND vela3.high < vela1.low (sin solapamiento)
            #   Rango: entre vela3.high (bottom) y vela1.low (top)
            
            fvg_formed = False
            calculated_fvg_bottom = None
            calculated_fvg_top = None
            calculated_fvg_type = None
            
            # Verificar FVG ALCISTA entre vela1 y vela3
            if vela1['low'] < vela3['high'] and vela3['low'] > vela1['high']:
                calculated_fvg_bottom = vela1['high']  # HIGH de vela1
                calculated_fvg_top = vela3['low']      # LOW de vela3
                calculated_fvg_type = 'ALCISTA'
                fvg_formed = True
                self.logger.info(f"[{symbol}] ✅ FVG ALCISTA formado por las 3 velas: {calculated_fvg_bottom:.5f} - {calculated_fvg_top:.5f}")
            
            # Verificar FVG BAJISTA entre vela1 y vela3
            elif vela1['high'] > vela3['low'] and vela3['high'] < vela1['low']:
                calculated_fvg_bottom = vela3['high']    # HIGH de vela3
                calculated_fvg_top = vela1['low']      # LOW de vela1
                calculated_fvg_type = 'BAJISTA'
                fvg_formed = True
                self.logger.info(f"[{symbol}] ✅ FVG BAJISTA formado por las 3 velas: {calculated_fvg_bottom:.5f} - {calculated_fvg_top:.5f}")
            
            if not fvg_formed:
                self.logger.info(f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: Las 3 velas NO forman un FVG válido")
                return None
            
            # Verificar que el FVG formado es del tipo esperado según el Turtle Soup
            if calculated_fvg_type != fvg_type:
                self.logger.info(
                    f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: FVG formado es {calculated_fvg_type} pero esperábamos {fvg_type} "
                    f"(según Turtle Soup {sweep_type} + dirección {direction})"
                )
                return None
            
            # Verificar que el FVG calculado coincide con el detectado (con tolerancia pequeña)
            tolerance = abs(fvg_top - fvg_bottom) * 0.01  # 1% de tolerancia
            if abs(calculated_fvg_bottom - fvg_bottom) > tolerance or abs(calculated_fvg_top - fvg_top) > tolerance:
                self.logger.warning(
                    f"[{symbol}] ⚠️  FVG calculado difiere del detectado: "
                    f"Calculado: {calculated_fvg_bottom:.5f}-{calculated_fvg_top:.5f} | "
                    f"Detectado: {fvg_bottom:.5f}-{fvg_top:.5f}"
                )
                # Usar el FVG calculado de las velas (más confiable)
                fvg_bottom = calculated_fvg_bottom
                fvg_top = calculated_fvg_top
            
            # Obtener información de la vela EN FORMACIÓN (vela3)
            candle_high = vela3.get('high')
            candle_low = vela3.get('low')
            candle_close = vela3.get('close')
            candle_open = vela3.get('open')
            
            if candle_high is None or candle_low is None or candle_close is None:
                self.logger.error(f"[{symbol}] ❌ Vela en formación no tiene datos completos")
                return None
            
            # Obtener precio actual (bid) para validar salida
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                self.logger.error(f"[{symbol}] ❌ No se pudo obtener precio actual")
                return None
            current_price = float(tick.bid)
            
            self.logger.info(f"[{symbol}] 📊 Vela EN FORMACIÓN: H={candle_high:.5f} L={candle_low:.5f} C={candle_close:.5f} | Precio actual: {current_price:.5f}")
            self.logger.info(f"[{symbol}] 📊 FVG calculado desde velas: {calculated_fvg_type} | Bottom: {fvg_bottom:.5f} | Top: {fvg_top:.5f}")
            
            # ⚠️ VALIDACIÓN CRÍTICA 1: La vela EN FORMACIÓN (vela3) DEBE haber entrado al FVG
            # REGLA ESPECÍFICA POR TIPO DE FVG (VERIFICACIÓN ESTRICTA):
            # - FVG BAJISTA: El HIGH de la vela DEBE estar dentro del FVG (fvg_bottom <= HIGH <= fvg_top)
            # - FVG ALCISTA: El LOW de la vela DEBE estar dentro del FVG (fvg_bottom <= LOW <= fvg_top)
            # 
            # IMPORTANTE: Si la vela NO tocó el FVG, NO puede haber una entrada válida
            candle_entered_fvg = False
            
            if calculated_fvg_type == 'BAJISTA':
                # FVG BAJISTA: El HIGH de la vela en formación DEBE estar dentro del FVG
                # Verificación estricta: HIGH debe estar en el rango [fvg_bottom, fvg_top]
                if fvg_bottom <= candle_high <= fvg_top:
                    candle_entered_fvg = True
                    self.logger.info(f"[{symbol}] ✅ Vela entró al FVG BAJISTA: HIGH ({candle_high:.5f}) está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f})")
                else:
                    # CRÍTICO: Si el HIGH no está dentro del FVG, la vela NO entró
                    self.logger.warning(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Para FVG BAJISTA, HIGH de vela ({candle_high:.5f}) NO está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f}) | "
                        f"La vela NO entró al FVG - NO SE PUEDE EJECUTAR ORDEN"
                    )
                    return None
            elif calculated_fvg_type == 'ALCISTA':
                # FVG ALCISTA: El LOW de la vela en formación DEBE estar dentro del FVG
                # Verificación estricta: LOW debe estar en el rango [fvg_bottom, fvg_top]
                if fvg_bottom <= candle_low <= fvg_top:
                    candle_entered_fvg = True
                    self.logger.info(f"[{symbol}] ✅ Vela entró al FVG ALCISTA: LOW ({candle_low:.5f}) está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f})")
                else:
                    # CRÍTICO: Si el LOW no está dentro del FVG, la vela NO entró
                    self.logger.warning(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Para FVG ALCISTA, LOW de vela ({candle_low:.5f}) NO está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f}) | "
                        f"La vela NO entró al FVG - NO SE PUEDE EJECUTAR ORDEN"
                    )
                    return None
            
            # Verificación adicional de seguridad (no debería llegar aquí si no entró, pero por si acaso)
            if not candle_entered_fvg:
                self.logger.error(
                    f"[{symbol}] ❌ VALIDACIÓN FALLIDA: La vela EN FORMACIÓN NO entró al FVG {calculated_fvg_type} | "
                    f"Vela: H={candle_high:.5f} L={candle_low:.5f} C={candle_close:.5f} | "
                    f"FVG: {fvg_bottom:.5f}-{fvg_top:.5f} | NO SE EJECUTARÁ ORDEN"
                )
                return None
            
            self.logger.info(f"[{symbol}] ✅ Vela EN FORMACIÓN entró al FVG {calculated_fvg_type}: H={candle_high:.5f} L={candle_low:.5f}")
            
            # VALIDACIÓN 2: El precio actual DEBE haber salido del FVG en la dirección correcta
            # IMPORTANTE: Usamos el precio actual (bid) para validar salida, no el CLOSE de la vela
            # porque la vela está en formación y el CLOSE puede cambiar
            price_exited_fvg = False
            exit_direction = None
            
            # Verificar que el precio actual esté FUERA del rango del FVG
            price_outside_fvg = (current_price < fvg_bottom) or (current_price > fvg_top)
            
            if not price_outside_fvg:
                self.logger.info(
                    f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: El precio actual ({current_price:.5f}) aún NO salió del FVG | "
                    f"Precio está DENTRO del FVG ({fvg_bottom:.5f}-{fvg_top:.5f}) | "
                    f"Debe estar FUERA del FVG en dirección {direction}"
                )
                return None
            
            # Verificar la dirección de salida según el tipo de FVG y dirección esperada
            # ⚠️ VALIDACIÓN CRÍTICA: El precio DEBE salir del FVG en la dirección CORRECTA
            # Si sale en dirección INCORRECTA, se rechaza la entrada
            if calculated_fvg_type == 'BAJISTA' and direction == 'BEARISH':
                # FVG BAJISTA + dirección BEARISH: precio debe estar DEBAJO del FVG
                if current_price < fvg_bottom:
                    price_exited_fvg = True
                    exit_direction = 'BAJISTA'
                    self.logger.info(f"[{symbol}] 📍 Precio salió del FVG BAJISTA: Precio actual ({current_price:.5f}) está DEBAJO del FVG Bottom ({fvg_bottom:.5f})")
                elif current_price > fvg_top:
                    # ⚠️ ERROR CRÍTICO: Precio salió ARRIBA del FVG pero esperábamos salida BAJISTA
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Precio salió del FVG en dirección INCORRECTA | "
                        f"FVG BAJISTA + dirección BEARISH esperada, pero precio ({current_price:.5f}) está ARRIBA del FVG Top ({fvg_top:.5f}) | "
                        f"El precio salió ALCISTA cuando debería haber salido BAJISTA - RECHAZANDO ENTRADA"
                    )
                    return None
                else:
                    # Precio aún dentro del FVG o en el borde (no debería llegar aquí por la validación anterior)
                    self.logger.info(
                        f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: Precio aún no salió del FVG en dirección {direction} | "
                        f"Precio actual={current_price:.5f} | FVG: {fvg_bottom:.5f}-{fvg_top:.5f}"
                    )
                    return None
            elif calculated_fvg_type == 'ALCISTA' and direction == 'BULLISH':
                # FVG ALCISTA + dirección BULLISH: precio debe estar ARRIBA del FVG
                if current_price > fvg_top:
                    price_exited_fvg = True
                    exit_direction = 'ALCISTA'
                    self.logger.info(f"[{symbol}] 📍 Precio salió del FVG ALCISTA: Precio actual ({current_price:.5f}) está ARRIBA del FVG Top ({fvg_top:.5f})")
                elif current_price < fvg_bottom:
                    # ⚠️ ERROR CRÍTICO: Precio salió DEBAJO del FVG pero esperábamos salida ALCISTA
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Precio salió del FVG en dirección INCORRECTA | "
                        f"FVG ALCISTA + dirección BULLISH esperada, pero precio ({current_price:.5f}) está DEBAJO del FVG Bottom ({fvg_bottom:.5f}) | "
                        f"El precio salió BAJISTA cuando debería haber salido ALCISTA - RECHAZANDO ENTRADA"
                    )
                    return None
                else:
                    # Precio aún dentro del FVG o en el borde (no debería llegar aquí por la validación anterior)
                    self.logger.info(
                        f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: Precio aún no salió del FVG en dirección {direction} | "
                        f"Precio actual={current_price:.5f} | FVG: {fvg_bottom:.5f}-{fvg_top:.5f}"
                    )
                    return None
            else:
                # Tipo de FVG no coincide con dirección esperada
                self.logger.info(
                    f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: FVG {calculated_fvg_type} no coincide con dirección {direction} esperada"
                )
                return None
            
            if not price_exited_fvg:
                self.logger.info(
                    f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: El precio NO salió del FVG en dirección {direction} | "
                    f"Precio actual={current_price:.5f} | FVG: {fvg_bottom:.5f}-{fvg_top:.5f}"
                )
                return None
            
            self.logger.info(
                f"[{symbol}] ✅ REGLA CUMPLIDA: Vela EN FORMACIÓN entró al FVG {calculated_fvg_type} y precio salió en dirección {exit_direction} | "
                f"Vela: O={candle_open:.5f} H={candle_high:.5f} L={candle_low:.5f} C={candle_close:.5f} | "
                f"Precio actual: {current_price:.5f}"
            )
            
            # Determinar qué tipo de FVG buscamos según el barrido de H4
            # LÓGICA CORREGIDA:
            # - Barrido de HIGH (BULLISH_SWEEP) + dirección BEARISH → Busca FVG BAJISTA (formado a la baja) para vender
            # - Barrido de LOW (BEARISH_SWEEP) + dirección BULLISH → Busca FVG ALCISTA (formado en alza) para comprar
            # En ambos casos, esperamos que el precio entre y salga en la dirección del Turtle Soup
            
            # Verificar tipo de FVG según el barrido de H4
            expected_fvg_type = None
            if sweep_type == 'BULLISH_SWEEP' and direction == 'BEARISH':
                # Barrido de HIGH → Busca FVG BAJISTA (formado a la baja) para entrada bajista (venta)
                expected_fvg_type = 'BAJISTA'
            elif sweep_type == 'BEARISH_SWEEP' and direction == 'BULLISH':
                # Barrido de LOW → Busca FVG ALCISTA (formado en alza) para entrada alcista (compra)
                expected_fvg_type = 'ALCISTA'
            
            if expected_fvg_type and fvg_type != expected_fvg_type:
                # El tipo de FVG no es el esperado según el barrido
                self.logger.info(f"[{symbol}] ⏸️  Esperando: FVG {fvg_type} detectado, pero necesitamos FVG {expected_fvg_type} (barrido {sweep_type} → {direction})")
                return None
            
            self.logger.info(f"[{symbol}] ✅ FVG {fvg_type} correcto para la estrategia (según barrido H4: {sweep_type})")
            
            self.logger.info(f"[{symbol}] ✅ Condiciones cumplidas - Listo para calcular entrada")
            
            # Obtener precio actual (bid para venta, ask para compra)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            
            # Calcular niveles
            fvg_top = fvg.get('fvg_top')
            fvg_bottom = fvg.get('fvg_bottom')
            target_price = turtle_soup.get('target_price')
            
            if fvg_top is None or fvg_bottom is None or target_price is None:
                return None
            
            # Calcular Stop Loss (debe cubrir TODO el espacio del FVG + margen adicional para soportar movimientos del precio)
            # El SL debe estar lo suficientemente lejos para que si el precio retrocede y completa el FVG, el SL no se active
            fvg_size = fvg_top - fvg_bottom
            
            # Obtener información del símbolo para calcular spread y distancia mínima
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return None
            
            spread_points = symbol_info.spread  # Spread en puntos
            point = symbol_info.point  # Valor de un punto
            spread_price = spread_points * point  # Spread en precio
            
            # Para calcular pips correctamente: 1 pip = 10 points para símbolos con 5 dígitos, 1 point para 3 dígitos
            pips_to_points = 10 if symbol_info.digits == 5 else 1
            
            # Margen adicional estándar: 100% del tamaño del FVG (aumentado de 50% a 100%)
            # Esto asegura que el SL cubra el espacio completo del FVG (100%) + un margen adicional igual (100%)
            # Total: 2.0x el tamaño del FVG para soportar movimientos del precio
            safety_margin = fvg_size * 1.0  # 100% adicional más allá del FVG
            
            # Distancia mínima estándar del SL: debe ser razonable para soportar movimientos del precio
            # IMPORTANTE: La distancia mínima debe adaptarse a la temporalidad de entrada
            # - M1: Entradas más ajustadas, SL más corto (15-20 pips)
            # - M5 o superior: SL más amplio (30-40 pips)
            fvg_size_pips = fvg_size * (10000 if symbol_info.digits == 5 else 100)
            
            # Determinar distancia mínima según temporalidad de entrada
            entry_tf = self.entry_timeframe.upper()
            if entry_tf == 'M1':
                # Para M1: SL más ajustado, pero aún cubriendo el FVG bien
                if fvg_size_pips < 3:
                    min_pips = 15  # FVG muy pequeño en M1: 15 pips mínimo
                elif fvg_size_pips < 5:
                    min_pips = 18  # FVG pequeño en M1: 18 pips mínimo
                else:
                    min_pips = 20  # FVG normal en M1: 20 pips mínimo
                self.logger.info(f"[{symbol}] 📏 Entrada M1: FVG {fvg_size_pips:.1f} pips → distancia mínima ajustada: {min_pips} pips")
            else:
                # Para M5 o superior: SL más amplio
                if fvg_size_pips < 5:
                    # FVG muy pequeño (< 5 pips): usar distancia mínima generosa de 40 pips
                    min_pips = 40
                    self.logger.info(f"[{symbol}] 📏 FVG pequeño ({fvg_size_pips:.1f} pips) → usando distancia mínima generosa de {min_pips} pips")
                elif fvg_size_pips < 10:
                    # FVG pequeño (5-10 pips): usar distancia mínima de 35 pips
                    min_pips = 35
                    self.logger.info(f"[{symbol}] 📏 FVG pequeño ({fvg_size_pips:.1f} pips) → usando distancia mínima de {min_pips} pips")
                else:
                    # FVG normal o grande (>= 10 pips): usar distancia mínima estándar de 30 pips
                    min_pips = 30
                    self.logger.info(f"[{symbol}] 📏 FVG normal ({fvg_size_pips:.1f} pips) → usando distancia mínima estándar de {min_pips} pips")
            
            min_sl_distance_pips = min_pips * pips_to_points * point
            
            # La distancia mínima debe ser el mayor entre:
            # 1. 5x el spread (mínimo por spread)
            # 2. La distancia mínima en pips (30-40 pips según tamaño del FVG)
            # 3. 2.5x el tamaño del FVG (solo si el FVG es grande, para cubrirlo bien)
            min_sl_distance = max(
                spread_price * 5,  # 5x el spread como mínimo
                min_sl_distance_pips,  # Mínimo 30-40 pips según tamaño del FVG
                fvg_size * 2.5  # 2.5x el tamaño del FVG para cubrirlo bien + margen adicional
            )
            
            self.logger.info(f"[{symbol}] 📐 Cálculo SL: FVG Size={fvg_size:.5f} ({fvg_size_pips:.1f} pips) | Safety Margin={safety_margin:.5f} ({safety_margin * (10000 if symbol_info.digits == 5 else 100):.1f} pips) | Min Distance={min_sl_distance:.5f} ({min_sl_distance * (10000 if symbol_info.digits == 5 else 100):.1f} pips)")
            
            # ⚡ ORDEN A MERCADO: Usar precio actual del mercado (bid/ask)
            # Para órdenes a mercado, el precio de entrada es el precio actual del mercado
            # La optimización viene de entrar cuando el precio ya salió del FVG (mejor momento)
            
            if direction == 'BULLISH':
                # Compra: Orden a mercado se ejecuta al precio ASK actual
                entry_price = float(tick.ask)
                self.logger.info(f"[{symbol}] 💹 Entrada a mercado (BUY): Precio ASK actual = {entry_price:.5f}")
                
                # SL debajo del FVG: cubre el espacio completo del FVG + margen adicional estándar
                # Fórmula: SL = FVG Bottom - (Tamaño del FVG + Margen de seguridad)
                # Esto asegura que el SL esté a 2.0x el tamaño del FVG debajo del FVG Bottom
                # Cubriendo así todo el espacio del FVG (100%) + margen adicional igual (100%) = 200% del FVG
                # Esto soporta mejor los movimientos del precio y evita SL demasiado cortos
                calculated_sl = fvg_bottom - fvg_size - safety_margin
                self.logger.info(f"[{symbol}] 📊 SL desde FVG: FVG Bottom={fvg_bottom:.5f} - FVG Size={fvg_size:.5f} - Safety Margin={safety_margin:.5f} = {calculated_sl:.5f}")
                
                # Asegurar distancia mínima del SL desde el precio de entrada
                # El SL debe estar al menos a min_sl_distance del precio de entrada
                # IMPORTANTE: SIEMPRE usar el MENOR entre el SL calculado y el mínimo requerido (para BUY, SL está abajo)
                # Esto asegura que el SL tenga una distancia mínima razonable del entry,
                # incluso cuando el entry está muy cerca del FVG o el FVG es muy pequeño
                min_sl_price = entry_price - min_sl_distance
                stop_loss = min(calculated_sl, min_sl_price)
                
                # Calcular distancia final del SL al entry
                final_sl_distance = abs(entry_price - stop_loss)
                
                # Verificar si el SL cubre bien el FVG
                # El SL debe estar al menos a (FVG Size + Safety Margin) del FVG Bottom
                sl_to_fvg_bottom = abs(stop_loss - fvg_bottom)
                required_coverage = fvg_size + safety_margin
                
                pips_min = self._price_to_pips(min_sl_distance, symbol_info.digits)
                pips_final = self._price_to_pips(final_sl_distance, symbol_info.digits)
                pips_coverage = self._price_to_pips(sl_to_fvg_bottom, symbol_info.digits)
                pips_required = self._price_to_pips(required_coverage, symbol_info.digits)
                
                if stop_loss < calculated_sl:
                    # SL fue ajustado por distancia mínima (más lejos del entry = más seguro)
                    self.logger.info(f"[{symbol}] ⚠️  SL ajustado por distancia mínima: {calculated_sl:.5f} → {stop_loss:.5f}")
                    self.logger.info(f"[{symbol}]    Mínimo requerido: {min_sl_price:.5f} | Distancia mínima: {min_sl_distance:.5f} ({pips_min:.1f} pips)")
                    self.logger.info(f"[{symbol}]    Distancia final del SL al entry: {final_sl_distance:.5f} ({pips_final:.1f} pips)")
                    self.logger.info(f"[{symbol}]    Cobertura del FVG: {sl_to_fvg_bottom:.5f} ({pips_coverage:.1f} pips) | Requerido: {required_coverage:.5f} ({pips_required:.1f} pips)")
                else:
                    # SL calculado cubre el FVG adecuadamente
                    self.logger.info(f"[{symbol}] ✅ SL calculado cubre FVG adecuadamente: {stop_loss:.5f}")
                    self.logger.info(f"[{symbol}]    Distancia desde entry: {final_sl_distance:.5f} ({pips_final:.1f} pips)")
                    self.logger.info(f"[{symbol}]    Cobertura del FVG: {sl_to_fvg_bottom:.5f} ({pips_coverage:.1f} pips) | Requerido: {required_coverage:.5f} ({pips_required:.1f} pips)")
                
                take_profit = target_price
                self.logger.info(f"[{symbol}] 🛑 SL calculado: {stop_loss:.5f} (FVG Bottom: {fvg_bottom:.5f} - FVG Size: {fvg_size:.5f} - Safety Margin: {safety_margin:.5f} - Min Distance: {min_sl_distance:.5f})")
            else:
                # Venta: Orden a mercado se ejecuta al precio BID actual
                entry_price = float(tick.bid)
                self.logger.info(f"[{symbol}] 💹 Entrada a mercado (SELL): Precio BID actual = {entry_price:.5f}")
                
                # SL arriba del FVG: cubre el espacio completo del FVG + margen adicional estándar
                # Fórmula: SL = FVG Top + (Tamaño del FVG + Margen de seguridad)
                # Esto asegura que el SL esté a 2.0x el tamaño del FVG arriba del FVG Top
                # Cubriendo así todo el espacio del FVG (100%) + margen adicional igual (100%) = 200% del FVG
                # Esto soporta mejor los movimientos del precio y evita SL demasiado cortos
                calculated_sl = fvg_top + fvg_size + safety_margin
                self.logger.info(f"[{symbol}] 📊 SL desde FVG: FVG Top={fvg_top:.5f} + FVG Size={fvg_size:.5f} + Safety Margin={safety_margin:.5f} = {calculated_sl:.5f}")
                
                # Asegurar distancia mínima del SL desde el precio de entrada
                # El SL debe estar al menos a min_sl_distance del precio de entrada
                # IMPORTANTE: SIEMPRE usar el MAYOR entre el SL calculado y el mínimo requerido
                # Esto asegura que el SL tenga una distancia mínima razonable del entry,
                # incluso cuando el entry está muy cerca del FVG o el FVG es muy pequeño
                min_sl_price = entry_price + min_sl_distance
                stop_loss = max(calculated_sl, min_sl_price)
                
                # Calcular distancia final del SL al entry
                final_sl_distance = abs(entry_price - stop_loss)
                
                # Verificar si el SL cubre bien el FVG
                # El SL debe estar al menos a (FVG Size + Safety Margin) del FVG Top
                sl_to_fvg_top = abs(stop_loss - fvg_top)
                required_coverage = fvg_size + safety_margin
                
                pips_min = self._price_to_pips(min_sl_distance, symbol_info.digits)
                pips_final = self._price_to_pips(final_sl_distance, symbol_info.digits)
                pips_coverage = self._price_to_pips(sl_to_fvg_top, symbol_info.digits)
                pips_required = self._price_to_pips(required_coverage, symbol_info.digits)
                
                if stop_loss > calculated_sl:
                    # SL fue ajustado por distancia mínima (más lejos del entry = más seguro)
                    self.logger.info(f"[{symbol}] ⚠️  SL ajustado por distancia mínima: {calculated_sl:.5f} → {stop_loss:.5f}")
                    self.logger.info(f"[{symbol}]    Mínimo requerido: {min_sl_price:.5f} | Distancia mínima: {min_sl_distance:.5f} ({pips_min:.1f} pips)")
                    self.logger.info(f"[{symbol}]    Distancia final del SL al entry: {final_sl_distance:.5f} ({pips_final:.1f} pips)")
                    self.logger.info(f"[{symbol}]    Cobertura del FVG: {sl_to_fvg_top:.5f} ({pips_coverage:.1f} pips) | Requerido: {required_coverage:.5f} ({pips_required:.1f} pips)")
                else:
                    # SL calculado cubre el FVG adecuadamente
                    self.logger.info(f"[{symbol}] ✅ SL calculado cubre FVG adecuadamente: {stop_loss:.5f}")
                    self.logger.info(f"[{symbol}]    Distancia desde entry: {final_sl_distance:.5f} ({pips_final:.1f} pips)")
                    self.logger.info(f"[{symbol}]    Cobertura del FVG: {sl_to_fvg_top:.5f} ({pips_coverage:.1f} pips) | Requerido: {required_coverage:.5f} ({pips_required:.1f} pips)")
                
                take_profit = target_price
                self.logger.info(f"[{symbol}] 🛑 SL calculado: {stop_loss:.5f} (FVG Top: {fvg_top:.5f} + FVG Size: {fvg_size:.5f} + Safety Margin: {safety_margin:.5f} + Min Distance: {min_sl_distance:.5f})")
            
            # Verificar y ajustar Risk/Reward (mínimo: min_rr, máximo: min_rr)
            # El TP debe estar limitado para que el RR no exceda el máximo permitido (1:2)
            risk = abs(entry_price - stop_loss)
            
            if risk == 0:
                return None
            
            # Calcular RR con el TP del target_price
            initial_reward = abs(take_profit - entry_price)
            initial_rr = initial_reward / risk
            
            # ⚠️ LIMITAR TP: Si el RR es mayor que el máximo permitido, ajustar TP para que RR = max_rr
            max_rr = self.min_rr  # RR máximo = RR mínimo (1:2)
            
            if initial_rr > max_rr:
                # Ajustar TP para que el RR sea exactamente el máximo permitido
                max_reward = risk * max_rr
                if direction == 'BULLISH':
                    # Compra: TP debe estar arriba del entry
                    take_profit = entry_price + max_reward
                else:
                    # Venta: TP debe estar debajo del entry
                    take_profit = entry_price - max_reward
                
                reward = max_reward
                rr = max_rr
                
                self.logger.info(
                    f"[{symbol}] ⚠️  TP ajustado: RR inicial ({initial_rr:.2f}) excedía el máximo permitido ({max_rr:.2f}) | "
                    f"TP original: {turtle_soup.get('target_price'):.5f} → TP ajustado: {take_profit:.5f} | "
                    f"RR final: {rr:.2f}"
                )
            else:
                reward = initial_reward
                rr = initial_rr
            
            self.logger.info(f"[{symbol}] 📈 Calculando RR: Risk={risk:.5f}, Reward={reward:.5f}, RR={rr:.2f} (mínimo requerido: {self.min_rr}, máximo: {max_rr})")
            
            if rr < self.min_rr:
                self.logger.info(f"[{symbol}] ⏸️  Esperando: RR insuficiente ({rr:.2f} < {self.min_rr}). Intentando optimizar SL...")
                # Intentar ajustar SL si es posible
                adjusted_sl = self._optimize_sl(entry_price, take_profit, direction, fvg_top, fvg_bottom)
                if adjusted_sl:
                    new_risk = abs(entry_price - adjusted_sl)
                    new_rr = reward / new_risk
                    if new_rr >= self.min_rr and new_rr <= max_rr:
                        stop_loss = adjusted_sl
                        rr = new_rr
                        risk = new_risk
                        self.logger.info(f"[{symbol}] ✅ SL optimizado: Nuevo RR={rr:.2f}")
                    else:
                        self.logger.info(f"[{symbol}] ⏸️  Esperando: SL optimizado no alcanza RR válido (RR={new_rr:.2f}, requiere: {self.min_rr}-{max_rr})")
                        return None
                else:
                    self.logger.info(f"[{symbol}] ⏸️  Esperando: No se pudo optimizar SL para alcanzar RR mínimo")
                    return None
            else:
                self.logger.info(f"[{symbol}] ✅ RR válido: {rr:.2f} (dentro del rango {self.min_rr}-{max_rr}) - Etapa 3/4 COMPLETA")
            
            return {
                'direction': direction,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'risk': risk,
                'reward': reward,
                'rr': rr,
                'fvg': fvg
            }
            
        except Exception as e:
            self.logger.error(f"Error al buscar entrada FVG: {e}", exc_info=True)
            return None
    
    def _optimize_sl(self, entry_price: float, take_profit: float, direction: str, 
                    fvg_top: float, fvg_bottom: float) -> Optional[float]:
        """
        Intenta optimizar el SL para lograr RR mínimo respetando el margen de seguridad del FVG
        
        Args:
            entry_price: Precio de entrada
            take_profit: Precio objetivo
            direction: Dirección de la operación
            fvg_top: Top del FVG
            fvg_bottom: Bottom del FVG
            
        Returns:
            SL optimizado o None
        """
        try:
            reward = abs(take_profit - entry_price)
            required_risk = reward / self.min_rr
            fvg_size = fvg_top - fvg_bottom
            safety_margin = fvg_size * 0.3  # 30% adicional más allá del FVG (reducido de 50% para SL más corto)
            
            if direction == 'BULLISH':
                # Compra: SL debe estar debajo del entry
                optimal_sl = entry_price - required_risk
                # Calcular el SL mínimo requerido (FVG bottom - tamaño FVG - margen)
                min_sl_required = fvg_bottom - fvg_size - safety_margin
                # El SL optimizado debe estar al menos al nivel mínimo requerido
                if optimal_sl <= min_sl_required:
                    return optimal_sl
                else:
                    # Si el SL optimizado está muy cerca del FVG, usar el mínimo requerido
                    # pero verificar que aún cumpla con el RR mínimo
                    if min_sl_required < entry_price:
                        return min_sl_required
            else:
                # Venta: SL debe estar arriba del entry
                optimal_sl = entry_price + required_risk
                # Calcular el SL mínimo requerido (FVG top + tamaño FVG + margen)
                min_sl_required = fvg_top + fvg_size + safety_margin
                # El SL optimizado debe estar al menos al nivel mínimo requerido
                if optimal_sl >= min_sl_required:
                    return optimal_sl
                else:
                    # Si el SL optimizado está muy cerca del FVG, usar el mínimo requerido
                    # pero verificar que aún cumpla con el RR mínimo
                    if min_sl_required > entry_price:
                        return min_sl_required
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error al optimizar SL: {e}")
            return None
    
    def _execute_order(self, symbol: str, turtle_soup: Dict, entry_signal: Dict) -> Optional[Dict]:
        """
        Ejecuta la orden de trading
        
        Args:
            symbol: Símbolo
            turtle_soup: Información del Turtle Soup
            entry_signal: Señal de entrada
            
        Returns:
            Dict con resultado de la orden
        """
        try:
            # ⚠️ VALIDACIÓN CRÍTICA FINAL: Verificar que la VELA EN FORMACIÓN (junto con las 2 anteriores) formen el FVG esperado
            # Esta es la validación final más estricta antes de ejecutar la orden
            self.logger.info(f"[{symbol}] 🔍 Validación final estricta: Verificando vela EN FORMACIÓN + 2 anteriores forman FVG esperado...")
            
            # Obtener las 3 velas: vela en formación (posición 0) + 2 anteriores (posición 1 y 2)
            timeframe_map = {
                'M1': mt5.TIMEFRAME_M1,
                'M5': mt5.TIMEFRAME_M5,
                'M15': mt5.TIMEFRAME_M15,
                'M30': mt5.TIMEFRAME_M30,
                'H1': mt5.TIMEFRAME_H1,
                'H4': mt5.TIMEFRAME_H4,
                'D1': mt5.TIMEFRAME_D1,
            }
            tf = timeframe_map.get(self.entry_timeframe.upper(), mt5.TIMEFRAME_M5)
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, 3)  # Obtener 3 velas: actual (pos 0), anterior1 (pos 1), anterior2 (pos 2)
            
            if rates is None or len(rates) < 3:
                self.logger.error(f"[{symbol}] ❌ VALIDACIÓN FALLIDA: No se pudo obtener las 3 velas necesarias - Cancelando orden")
                return None
            
            # Ordenar por tiempo para tener: vela1 (más antigua), vela2 (del medio), vela3 (actual/en formación)
            candles_data = []
            for i, candle_data in enumerate(rates):
                candles_data.append({
                    'open': float(candle_data['open']),
                    'high': float(candle_data['high']),
                    'low': float(candle_data['low']),
                    'close': float(candle_data['close']),
                    'time': datetime.fromtimestamp(candle_data['time'])
                })
            
            candles_data = sorted(candles_data, key=lambda x: x['time'])
            vela1 = candles_data[0]  # Más antigua
            vela2 = candles_data[1]    # Del medio
            vela3 = candles_data[2]    # Actual/en formación
            
            # VALIDACIÓN FINAL 0: Verificar que las 3 velas forman el FVG esperado
            fvg_formed = False
            calculated_fvg_bottom = None
            calculated_fvg_top = None
            calculated_fvg_type = None
            
            # Verificar FVG ALCISTA entre vela1 y vela3
            if vela1['low'] < vela3['high'] and vela3['low'] > vela1['high']:
                calculated_fvg_bottom = vela1['high']
                calculated_fvg_top = vela3['low']
                calculated_fvg_type = 'ALCISTA'
                fvg_formed = True
            
            # Verificar FVG BAJISTA entre vela1 y vela3
            elif vela1['high'] > vela3['low'] and vela3['high'] < vela1['low']:
                calculated_fvg_bottom = vela3['high']
                calculated_fvg_top = vela1['low']
                calculated_fvg_type = 'BAJISTA'
                fvg_formed = True
            
            if not fvg_formed:
                self.logger.error(f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Las 3 velas NO forman un FVG válido - Cancelando orden")
                return None
            
            # Verificar que el FVG formado es del tipo esperado
            expected_fvg_type = None
            sweep_type = turtle_soup.get('sweep_type')
            direction = entry_signal['direction']
            if sweep_type == 'BULLISH_SWEEP' and direction == 'BEARISH':
                expected_fvg_type = 'BAJISTA'
            elif sweep_type == 'BEARISH_SWEEP' and direction == 'BULLISH':
                expected_fvg_type = 'ALCISTA'
            
            if calculated_fvg_type != expected_fvg_type:
                self.logger.error(
                    f"[{symbol}] ❌ VALIDACIÓN FALLIDA: FVG formado es {calculated_fvg_type} pero esperábamos {expected_fvg_type} - Cancelando orden"
                )
                return None
            
            # Usar el FVG calculado
            fvg_bottom = calculated_fvg_bottom
            fvg_top = calculated_fvg_top
            
            # Obtener información de la vela EN FORMACIÓN (vela3)
            candle_high = vela3.get('high')
            candle_low = vela3.get('low')
            candle_close = vela3.get('close')
            candle_time = vela3.get('time')
            
            # Obtener precio actual (bid) para validar salida
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                self.logger.error(f"[{symbol}] ❌ VALIDACIÓN FALLIDA: No se pudo obtener precio actual - Cancelando orden")
                return None
            current_price = float(tick.bid)
            
            self.logger.info(f"[{symbol}] 📊 Validando vela EN FORMACIÓN: {candle_time.strftime('%Y-%m-%d %H:%M:%S')} | H={candle_high:.5f} L={candle_low:.5f} C={candle_close:.5f} | Precio actual: {current_price:.5f}")
            self.logger.info(f"[{symbol}] 📊 FVG calculado: {calculated_fvg_type} | Bottom: {fvg_bottom:.5f} | Top: {fvg_top:.5f}")
            
            # ⚠️ VALIDACIÓN CRÍTICA FINAL 1: La vela EN FORMACIÓN (vela3) DEBE haber entrado al FVG
            # Esta es la validación MÁS ESTRICTA antes de ejecutar - NO SE PUEDE EJECUTAR si la vela NO entró
            # REGLA ESPECÍFICA POR TIPO DE FVG:
            # - FVG BAJISTA: El HIGH de la vela DEBE estar dentro del FVG [fvg_bottom, fvg_top]
            # - FVG ALCISTA: El LOW de la vela DEBE estar dentro del FVG [fvg_bottom, fvg_top]
            candle_entered = False
            
            if calculated_fvg_type == 'BAJISTA':
                # FVG BAJISTA: HIGH debe estar dentro del FVG - VERIFICACIÓN ESTRICTA
                if fvg_bottom <= candle_high <= fvg_top:
                    candle_entered = True
                    self.logger.info(f"[{symbol}] ✅ VALIDACIÓN: HIGH ({candle_high:.5f}) está dentro del FVG BAJISTA ({fvg_bottom:.5f}-{fvg_top:.5f})")
                else:
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Para FVG BAJISTA, HIGH ({candle_high:.5f}) NO está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f}) | "
                        f"Vela: H={candle_high:.5f} L={candle_low:.5f} | "
                        f"La vela NO entró al FVG - CANCELANDO ORDEN"
                    )
                    return None
            elif calculated_fvg_type == 'ALCISTA':
                # FVG ALCISTA: LOW debe estar dentro del FVG - VERIFICACIÓN ESTRICTA
                if fvg_bottom <= candle_low <= fvg_top:
                    candle_entered = True
                    self.logger.info(f"[{symbol}] ✅ VALIDACIÓN: LOW ({candle_low:.5f}) está dentro del FVG ALCISTA ({fvg_bottom:.5f}-{fvg_top:.5f})")
                else:
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Para FVG ALCISTA, LOW ({candle_low:.5f}) NO está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f}) | "
                        f"Vela: H={candle_high:.5f} L={candle_low:.5f} | "
                        f"La vela NO entró al FVG - CANCELANDO ORDEN"
                    )
                    return None
            
            # Verificación adicional de seguridad (no debería llegar aquí si no entró)
            if not candle_entered:
                self.logger.error(
                    f"[{symbol}] ❌ VALIDACIÓN FALLIDA: La vela EN FORMACIÓN NO entró al FVG {calculated_fvg_type} | "
                    f"Vela: H={candle_high:.5f} L={candle_low:.5f} C={candle_close:.5f} | "
                    f"FVG: {fvg_bottom:.5f}-{fvg_top:.5f} | CANCELANDO ORDEN - NO SE EJECUTARÁ"
                )
                return None
            
            # VALIDACIÓN FINAL 2: El precio actual DEBE haber salido del FVG en la dirección correcta
            # Usamos precio actual (bid) para validar salida, no el CLOSE de la vela
            price_outside = (current_price < fvg_bottom) or (current_price > fvg_top)
            if not price_outside:
                self.logger.error(
                    f"[{symbol}] ❌ VALIDACIÓN FALLIDA: El precio actual ({current_price:.5f}) NO salió del FVG | "
                    f"Precio está DENTRO del FVG ({fvg_bottom:.5f}-{fvg_top:.5f}) - Cancelando orden"
                )
                return None
            
            # VALIDACIÓN FINAL 3: La dirección de salida DEBE ser correcta
            # ⚠️ VALIDACIÓN CRÍTICA: El precio DEBE salir del FVG en la dirección CORRECTA
            # Si sale en dirección INCORRECTA, se CANCELA la orden
            if calculated_fvg_type == 'BAJISTA' and direction == 'BEARISH':
                # FVG BAJISTA + dirección BEARISH: precio debe estar DEBAJO del FVG
                if current_price < fvg_bottom:
                    # ✅ Precio salió correctamente (DEBAJO del FVG)
                    self.logger.info(
                        f"[{symbol}] ✅ Validación dirección: Precio ({current_price:.5f}) está DEBAJO del FVG Bottom ({fvg_bottom:.5f}) - Dirección correcta"
                    )
                elif current_price > fvg_top:
                    # ❌ ERROR CRÍTICO: Precio salió ARRIBA del FVG pero esperábamos salida BAJISTA
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Precio salió del FVG en dirección INCORRECTA | "
                        f"FVG BAJISTA + dirección BEARISH esperada, pero precio ({current_price:.5f}) está ARRIBA del FVG Top ({fvg_top:.5f}) | "
                        f"El precio salió ALCISTA cuando debería haber salido BAJISTA - CANCELANDO ORDEN"
                    )
                    return None
                else:
                    # Precio aún dentro del FVG o en el borde
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Precio ({current_price:.5f}) NO salió del FVG en dirección {direction} | "
                        f"Debe estar DEBAJO de {fvg_bottom:.5f} - Cancelando orden"
                    )
                    return None
            elif calculated_fvg_type == 'ALCISTA' and direction == 'BULLISH':
                # FVG ALCISTA + dirección BULLISH: precio debe estar ARRIBA del FVG
                if current_price > fvg_top:
                    # ✅ Precio salió correctamente (ARRIBA del FVG)
                    self.logger.info(
                        f"[{symbol}] ✅ Validación dirección: Precio ({current_price:.5f}) está ARRIBA del FVG Top ({fvg_top:.5f}) - Dirección correcta"
                    )
                elif current_price < fvg_bottom:
                    # ❌ ERROR CRÍTICO: Precio salió DEBAJO del FVG pero esperábamos salida ALCISTA
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Precio salió del FVG en dirección INCORRECTA | "
                        f"FVG ALCISTA + dirección BULLISH esperada, pero precio ({current_price:.5f}) está DEBAJO del FVG Bottom ({fvg_bottom:.5f}) | "
                        f"El precio salió BAJISTA cuando debería haber salido ALCISTA - CANCELANDO ORDEN"
                    )
                    return None
                else:
                    # Precio aún dentro del FVG o en el borde
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Precio ({current_price:.5f}) NO salió del FVG en dirección {direction} | "
                        f"Debe estar ARRIBA de {fvg_top:.5f} - Cancelando orden"
                    )
                    return None
            else:
                self.logger.error(
                    f"[{symbol}] ❌ VALIDACIÓN FALLIDA: FVG {calculated_fvg_type} no coincide con dirección {direction} esperada - Cancelando orden"
                )
                return None
            
            self.logger.info(
                f"[{symbol}] ✅ VALIDACIÓN FINAL EXITOSA: Vela EN FORMACIÓN entró al FVG {calculated_fvg_type} y precio salió correctamente | "
                f"Vela: H={candle_high:.5f} L={candle_low:.5f} C={candle_close:.5f} | "
                f"Precio actual: {current_price:.5f} | FVG: {fvg_bottom:.5f}-{fvg_top:.5f} | Dirección: {direction}"
            )
            
            # Verificar límite de trades por día
            if not self._check_daily_trade_limit(symbol):
                return None
            
            # ⚠️ VERIFICACIÓN CRÍTICA FINAL: Verificar posiciones abiertas JUSTO ANTES de ejecutar
            # Esto previene race conditions donde una posición puede estar abierta entre la verificación anterior y la ejecución
            if self._has_open_positions(symbol):
                self.logger.error(
                    f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Se detectaron posiciones abiertas JUSTO ANTES de ejecutar - "
                    f"CANCELANDO ORDEN para evitar posición opuesta"
                )
                return None
            
            direction = entry_signal['direction']
            stop_loss = entry_signal['stop_loss']
            take_profit = entry_signal['take_profit']
            rr = entry_signal['rr']
            
            # ⚡ OBTENER PRECIO ACTUAL DEL MERCADO EN ESTE MOMENTO EXACTO
            # Las condiciones se cumplieron, ahora obtenemos el precio actual para ejecutar orden a mercado
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                self.logger.error(f"[{symbol}] ❌ No se pudo obtener precio actual del mercado - Cancelando orden")
                return None
            
            # Precio de entrada = precio actual del mercado (bid para venta, ask para compra)
            if direction == 'BULLISH':
                entry_price = float(tick.ask)  # Compra: precio ASK
                self.logger.info(f"[{symbol}] 💹 Precio de entrada a mercado (BUY): {entry_price:.5f} (ASK actual)")
            else:
                entry_price = float(tick.bid)  # Venta: precio BID
                self.logger.info(f"[{symbol}] 💹 Precio de entrada a mercado (SELL): {entry_price:.5f} (BID actual)")
            
            # ⚠️ VALIDACIÓN CRÍTICA: El precio de entrada DEBE estar fuera del FVG con distancia mínima
            # Esto previene entradas cuando el precio está justo en el borde del FVG o dentro de él
            # debido a la diferencia entre BID/ASK y el precio usado en la validación anterior
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                self.logger.error(f"[{symbol}] ❌ No se pudo obtener información del símbolo")
                return None
            
            point = symbol_info.point
            spread_points = symbol_info.spread
            spread_price = spread_points * point
            
            # Distancia mínima requerida desde el FVG: spread + margen de seguridad (2 pips mínimo)
            # Esto asegura que el precio de entrada esté claramente fuera del FVG
            # Usamos los valores del FVG calculado (fvg_top y fvg_bottom) que ya fueron validados arriba
            pips_to_points = 10 if symbol_info.digits == 5 else 1
            min_distance_from_fvg = max(
                spread_price * 2,  # Al menos 2x el spread
                point * pips_to_points * 2  # Mínimo 2 pips
            )
            
            # Validar que el precio de entrada esté fuera del FVG con distancia mínima
            if direction == 'BULLISH' and calculated_fvg_type == 'ALCISTA':
                # Para BUY con FVG ALCISTA: entry_price (ASK) debe estar ARRIBA del FVG Top con distancia mínima
                required_min_price = fvg_top + min_distance_from_fvg
                if entry_price <= required_min_price:
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Precio de entrada (ASK={entry_price:.5f}) está muy cerca o dentro del FVG | "
                        f"FVG Top: {fvg_top:.5f} | Precio mínimo requerido: {required_min_price:.5f} | "
                        f"Distancia mínima: {min_distance_from_fvg:.5f} ({min_distance_from_fvg * (10000 if symbol_info.digits == 5 else 100):.1f} pips) | "
                        f"Cancelando orden - El precio debe salir más del FVG antes de entrar"
                    )
                    return None
                self.logger.info(
                    f"[{symbol}] ✅ Precio de entrada validado: ASK={entry_price:.5f} está ARRIBA del FVG Top ({fvg_top:.5f}) "
                    f"con distancia de {entry_price - fvg_top:.5f} ({(entry_price - fvg_top) * (10000 if symbol_info.digits == 5 else 100):.1f} pips)"
                )
            elif direction == 'BEARISH' and calculated_fvg_type == 'BAJISTA':
                # Para SELL con FVG BAJISTA: entry_price (BID) debe estar DEBAJO del FVG Bottom con distancia mínima
                required_max_price = fvg_bottom - min_distance_from_fvg
                if entry_price >= required_max_price:
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Precio de entrada (BID={entry_price:.5f}) está muy cerca o dentro del FVG | "
                        f"FVG Bottom: {fvg_bottom:.5f} | Precio máximo requerido: {required_max_price:.5f} | "
                        f"Distancia mínima: {min_distance_from_fvg:.5f} ({min_distance_from_fvg * (10000 if symbol_info.digits == 5 else 100):.1f} pips) | "
                        f"Cancelando orden - El precio debe salir más del FVG antes de entrar"
                    )
                    return None
                self.logger.info(
                    f"[{symbol}] ✅ Precio de entrada validado: BID={entry_price:.5f} está DEBAJO del FVG Bottom ({fvg_bottom:.5f}) "
                    f"con distancia de {fvg_bottom - entry_price:.5f} ({(fvg_bottom - entry_price) * (10000 if symbol_info.digits == 5 else 100):.1f} pips)"
                )
            
            # ⚠️ VERIFICAR Y AJUSTAR SL CON EL PRECIO REAL DE ENTRADA
            # El SL puede haberse calculado con un precio diferente, asegurar distancia mínima con precio real
            # (symbol_info ya fue obtenido arriba, reutilizamos)
            
            point = symbol_info.point
            spread_points = symbol_info.spread
            spread_price = spread_points * point
            
            # Obtener tamaño del FVG del entry_signal para calcular distancia mínima
            fvg_info = entry_signal.get('fvg', {})
            fvg_size = abs(fvg_info.get('fvg_top', 0) - fvg_info.get('fvg_bottom', 0)) if fvg_info else point * 2
            
            # Para calcular pips correctamente: 1 pip = 10 points para símbolos con 5 dígitos, 1 point para 3 dígitos
            pips_to_points = 10 if symbol_info.digits == 5 else 1
            fvg_size_pips = fvg_size * (10000 if symbol_info.digits == 5 else 100)
            
            # Distancia mínima del SL: adaptativa según tamaño del FVG Y temporalidad de entrada
            # IMPORTANTE: La distancia mínima debe adaptarse a la temporalidad de entrada
            # - M1: Entradas más ajustadas, SL más corto (15-20 pips)
            # - M5 o superior: SL más amplio (30-40 pips)
            entry_tf = self.entry_timeframe.upper()
            if entry_tf == 'M1':
                # Para M1: SL más ajustado
                if fvg_size_pips < 3:
                    min_pips = 15  # FVG muy pequeño en M1: 15 pips mínimo
                elif fvg_size_pips < 5:
                    min_pips = 18  # FVG pequeño en M1: 18 pips mínimo
                else:
                    min_pips = 20  # FVG normal en M1: 20 pips mínimo
            else:
                # Para M5 o superior: SL más amplio
                if fvg_size_pips < 5:
                    # FVG muy pequeño (< 5 pips): usar distancia mínima generosa de 40 pips
                    min_pips = 40
                elif fvg_size_pips < 10:
                    # FVG pequeño (5-10 pips): usar distancia mínima de 35 pips
                    min_pips = 35
                else:
                    # FVG normal o grande (>= 10 pips): usar distancia mínima estándar de 30 pips
                    min_pips = 30
            
            min_sl_distance_pips = min_pips * pips_to_points * point
            
            # La distancia mínima debe ser el mayor entre:
            # 1. 5x el spread (mínimo por spread)
            # 2. La distancia mínima en pips (30-40 pips según tamaño del FVG)
            # 3. 2.5x el tamaño del FVG (solo si el FVG es grande, para cubrirlo bien)
            min_sl_distance = max(
                spread_price * 5,  # 5x el spread como mínimo
                min_sl_distance_pips,  # Mínimo 30-40 pips según tamaño del FVG
                fvg_size * 2.5  # 2.5x el tamaño del FVG para cubrirlo bien + margen adicional
            )
            
            # Verificar distancia actual del SL al entry real
            current_sl_distance = abs(entry_price - stop_loss)
            original_sl = stop_loss
            
            # Si la distancia es menor que el mínimo, ajustar el SL
            if current_sl_distance < min_sl_distance:
                if direction == 'BULLISH':
                    # Para BUY: SL debe estar debajo del entry
                    min_sl_price = entry_price - min_sl_distance
                    if stop_loss > min_sl_price:
                        stop_loss = min_sl_price
                        self.logger.warning(
                            f"[{symbol}] ⚠️  SL ajustado por distancia mínima con precio real: "
                            f"{original_sl:.5f} → {stop_loss:.5f} | "
                            f"Distancia anterior: {current_sl_distance:.5f} ({current_sl_distance * 10000:.1f} pips) | "
                            f"Nueva distancia: {min_sl_distance:.5f} ({min_sl_distance * 10000:.1f} pips)"
                        )
                else:
                    # Para SELL: SL debe estar arriba del entry
                    min_sl_price = entry_price + min_sl_distance
                    if stop_loss < min_sl_price:
                        stop_loss = min_sl_price
                        self.logger.warning(
                            f"[{symbol}] ⚠️  SL ajustado por distancia mínima con precio real: "
                            f"{original_sl:.5f} → {stop_loss:.5f} | "
                            f"Distancia anterior: {current_sl_distance:.5f} ({current_sl_distance * 10000:.1f} pips) | "
                            f"Nueva distancia: {min_sl_distance:.5f} ({min_sl_distance * 10000:.1f} pips)"
                        )
            else:
                final_distance = abs(entry_price - stop_loss)
                pips_final = self._price_to_pips(final_distance, symbol_info.digits)
                pips_min = self._price_to_pips(min_sl_distance, symbol_info.digits)
                self.logger.info(
                    f"[{symbol}] ✅ SL tiene distancia adecuada: {final_distance:.5f} ({pips_final:.1f} pips) >= "
                    f"mínimo requerido: {min_sl_distance:.5f} ({pips_min:.1f} pips)"
                )
            
            # Recalcular RIESGO con el precio real de entrada y SL ajustado
            # IMPORTANTE: Mantener el SL ajustado (basado en distancia mínima + FVG)
            # Solo ajustaremos el TP para mantener el RR de 1:2
            risk = abs(entry_price - stop_loss)
            if risk <= 0:
                self.logger.error(f"[{symbol}] ❌ Risk calculado 0 o negativo después de ajustar entry_price - Cancelando orden")
                return None
            
            # Obtener información del FVG para validaciones (ya calculado arriba en la validación final)
            if 'calculated_fvg_bottom' in locals() and 'calculated_fvg_top' in locals():
                fvg_size_calc = abs(calculated_fvg_top - calculated_fvg_bottom)
            else:
                # Si no está disponible, usar el tamaño del FVG del entry_signal
                fvg_size_calc = fvg_size
            
            point = symbol_info.point  # Precisión del símbolo (ej: 0.00001 para EURUSD)
            digits = symbol_info.digits  # Dígitos decimales del símbolo (ej: 5 para EURUSD)
            stop_level = symbol_info.trade_stops_level  # Distancia mínima requerida por el broker
            min_distance = stop_level * point  # Distancia mínima en precio
            
            # ⚠️ FORZAR RR EXACTO 1:2 CON EL PRECIO REAL
            # Mantenemos el SL original (basado en FVG) y ajustamos el TP para mantener RR exacto de 1:2
            max_rr = self.min_rr  # 2.0 (1:2)
            original_tp = take_profit
            original_sl = stop_loss  # Guardar SL original para referencia
            
            # Calcular risk real con el precio de entrada actual
            risk_actual = abs(entry_price - stop_loss)
            if risk_actual == 0:
                self.logger.error(f"[{symbol}] ❌ Risk calculado 0 - Cancelando orden")
                return None
            
            # Calcular reward para RR exacto de 1:2 basado en el risk real
            reward_target = risk_actual * max_rr  # Reward = Risk * 2.0
            
            # Calcular TP forzado con reward que mantiene RR exacto de 1:2
            if direction == 'BULLISH':
                take_profit_raw = entry_price + reward_target
            else:
                take_profit_raw = entry_price - reward_target
            
            # Redondear TP según los digits del símbolo
            take_profit = round(take_profit_raw, digits)
            
            # Recalcular reward real después del redondeo
            if direction == 'BULLISH':
                reward_actual = take_profit - entry_price
            else:
                reward_actual = entry_price - take_profit
            
            # Verificar que el TP redondeado cumpla con la distancia mínima del broker
            # Si no cumple, ajustar ligeramente pero manteniendo RR lo más cercano a 1:2
            if direction == 'BULLISH':
                tp_distance = take_profit - entry_price
                if tp_distance < min_distance:
                    # Ajustar TP para cumplir distancia mínima, pero recalcular para mantener RR
                    take_profit = round(entry_price + min_distance, digits)
                    reward_actual = take_profit - entry_price
                    # Si el TP ajustado es mayor que el reward target, mantenerlo (mejor RR)
                    if reward_actual < reward_target:
                        # Recalcular TP para mantener RR exacto si es posible
                        take_profit = round(entry_price + reward_target, digits)
                        reward_actual = take_profit - entry_price
            else:
                tp_distance = entry_price - take_profit
                if tp_distance < min_distance:
                    # Ajustar TP para cumplir distancia mínima, pero recalcular para mantener RR
                    take_profit = round(entry_price - min_distance, digits)
                    reward_actual = entry_price - take_profit
                    # Si el TP ajustado es mayor que el reward target, mantenerlo (mejor RR)
                    if reward_actual < reward_target:
                        # Recalcular TP para mantener RR exacto si es posible
                        take_profit = round(entry_price - reward_target, digits)
                        reward_actual = entry_price - take_profit
            
            # Recalcular RR final con TP ajustado y SL original
            rr = reward_actual / risk_actual  # RR real con TP ajustado y SL original
            
            # Log del RR forzado
            self.logger.info(
                f"[{symbol}] 📈 RR recalculado y FORZADO a {rr:.2f}:1 con precio real | "
                f"Entry={entry_price:.5f}, SL={stop_loss:.5f} (Risk: {risk_actual:.5f}), "
                f"TP original={original_tp:.5f} → TP ajustado={take_profit:.5f} (Reward: {reward_actual:.5f})"
            )
            
            # Verificar que el RR sea al menos el mínimo requerido
            if rr < (self.min_rr - 0.01):  # Tolerancia de 0.01 para redondeo
                # Si el RR es menor que el mínimo, solo ajustar ligeramente el SL si es necesario
                # pero manteniendo una distancia razonable (no demasiado corta)
                required_reward = risk_actual * max_rr
                
                # Verificar si podemos ajustar el TP para cumplir RR sin hacer SL demasiado corto
                if direction == 'BULLISH':
                    min_tp = entry_price + min_distance
                    if required_reward >= min_distance:
                        # Podemos ajustar TP para cumplir RR
                        take_profit = round(entry_price + required_reward, digits)
                        reward_actual = take_profit - entry_price
                        rr = reward_actual / risk_actual
                    else:
                        # El reward requerido es menor que la distancia mínima, usar distancia mínima
                        take_profit = round(min_tp, digits)
                        reward_actual = take_profit - entry_price
                        rr = reward_actual / risk_actual
                else:
                    min_tp = entry_price - min_distance
                    if required_reward >= min_distance:
                        # Podemos ajustar TP para cumplir RR
                        take_profit = round(entry_price - required_reward, digits)
                        reward_actual = entry_price - take_profit
                        rr = reward_actual / risk_actual
                    else:
                        # El reward requerido es menor que la distancia mínima, usar distancia mínima
                        take_profit = round(min_tp, digits)
                        reward_actual = entry_price - take_profit
                        rr = reward_actual / risk_actual
                
                # Si después de ajustar el TP el RR aún es menor, verificar si podemos ajustar SL ligeramente
                # pero solo si no lo hace demasiado corto (mínimo 1.5x el tamaño del FVG)
                if rr < (self.min_rr - 0.01):
                    # Obtener información del FVG calculado en la validación final
                    # (calculated_fvg_bottom y calculated_fvg_top están disponibles en este scope)
                    if 'calculated_fvg_bottom' in locals() and 'calculated_fvg_top' in locals():
                        fvg_size = abs(calculated_fvg_top - calculated_fvg_bottom)
                    else:
                        # Si no están disponibles, usar el risk actual como referencia
                        fvg_size = risk_actual
                    
                    # Calcular distancia mínima razonable del SL
                    # No hacer el SL demasiado corto: mínimo 1.5x el tamaño del FVG o 80% del risk actual
                    min_sl_distance_reasonable = max(
                        fvg_size_calc * 1.5,  # Mínimo 1.5x el tamaño del FVG
                        min_distance * 2,  # O 2x la distancia mínima del broker
                        risk_actual * 0.8  # O 80% del risk actual (no hacer SL demasiado corto)
                    )
                    
                    self.logger.info(
                        f"[{symbol}] ⚠️  Ajustando SL para mantener RR mínimo | "
                        f"Distancia mínima razonable del SL: {min_sl_distance_reasonable:.5f} | "
                        f"FVG size: {fvg_size_calc:.5f}"
                    )
                    
                    # Calcular nuevo SL que mantenga distancia razonable
                    # IMPORTANTE: Solo ajustar el SL si es necesario y manteniendo distancia razonable
                    # No hacer el SL demasiado corto (más cercano al entry)
                    if direction == 'BULLISH':
                        new_sl = entry_price - min_sl_distance_reasonable
                        # Para BUY: SL debe estar debajo del entry
                        # Solo ajustar si el nuevo SL está más lejos (más abajo) que el original
                        # Esto aumenta el risk y permite mantener RR de 1:2
                        if new_sl < stop_loss:  # new_sl más abajo = más lejos = más risk
                            stop_loss = round(new_sl, digits)
                            risk_actual = abs(entry_price - stop_loss)
                            # Recalcular TP para mantener RR
                            reward_actual = risk_actual * max_rr
                            take_profit = round(entry_price + reward_actual, digits)
                            reward_actual = take_profit - entry_price
                            rr = reward_actual / risk_actual
                            self.logger.info(
                                f"[{symbol}] ⚠️  SL ajustado para mantener RR mínimo: "
                                f"SL original={original_sl:.5f} → SL ajustado={stop_loss:.5f} | "
                                f"Distancia razonable: {min_sl_distance_reasonable:.5f}"
                            )
                    else:
                        new_sl = entry_price + min_sl_distance_reasonable
                        # Para SELL: SL debe estar arriba del entry
                        # Solo ajustar si el nuevo SL está más lejos (más arriba) que el original
                        # Esto aumenta el risk y permite mantener RR de 1:2
                        if new_sl > stop_loss:  # new_sl más arriba = más lejos = más risk
                            stop_loss = round(new_sl, digits)
                            risk_actual = abs(entry_price - stop_loss)
                            # Recalcular TP para mantener RR
                            reward_actual = risk_actual * max_rr
                            take_profit = round(entry_price - reward_actual, digits)
                            reward_actual = entry_price - take_profit
                            rr = reward_actual / risk_actual
                            self.logger.info(
                                f"[{symbol}] ⚠️  SL ajustado para mantener RR mínimo: "
                                f"SL original={original_sl:.5f} → SL ajustado={stop_loss:.5f} | "
                                f"Distancia razonable: {min_sl_distance_reasonable:.5f}"
                            )
                    
                    if rr < (self.min_rr - 0.01):
                        self.logger.error(
                            f"[{symbol}] ❌ ERROR: No se pudo alcanzar RR mínimo ({self.min_rr:.2f}) manteniendo SL razonable | "
                            f"RR final: {rr:.2f} | Cancelando orden"
                        )
                        return None
            
            self.logger.info(
                f"[{symbol}] 📈 RR recalculado y FORZADO a {rr:.2f}:1 con precio real | "
                f"Entry={entry_price:.5f}, SL={stop_loss:.5f} (original: {original_sl:.5f}), TP original={original_tp:.5f} → TP ajustado={take_profit:.5f} (redondeado según digits={digits})"
            )
            
            # Crear diccionario FVG con la información calculada y validada
            fvg = {
                'fvg_type': calculated_fvg_type,
                'fvg_bottom': fvg_bottom,
                'fvg_top': fvg_top,
                'status': 'VALIDADO',
                'entered_fvg': True,  # Ya validado arriba
                'exited_fvg': True,   # Ya validado arriba
                'exit_direction': 'BAJISTA' if (calculated_fvg_type == 'BAJISTA' and direction == 'BEARISH') else 'ALCISTA' if (calculated_fvg_type == 'ALCISTA' and direction == 'BULLISH') else None
            }
            
            # Calcular volumen basado en el riesgo porcentual
            volume = self._calculate_volume_by_risk(symbol, entry_price, stop_loss)
            if volume is None or volume <= 0:
                self.logger.error(f"[{symbol}] ❌ No se pudo calcular el volumen por riesgo")
                return None
            
            # Log estructurado de la orden
            self.logger.info(f"[{symbol}] {'='*70}")
            self.logger.info(f"[{symbol}] 💹 EJECUTANDO ORDEN DE TRADING")
            self.logger.info(f"[{symbol}] {'='*70}")
            self.logger.info(f"[{symbol}] 📊 Dirección: {direction} ({'COMPRA' if direction == 'BULLISH' else 'VENTA'})")
            self.logger.info(f"[{symbol}] 💰 Precio de Entrada: {entry_price:.5f}")
            self.logger.info(f"[{symbol}] 🛑 Stop Loss: {stop_loss:.5f} (Risk: {entry_signal.get('risk', 0):.5f})")
            self.logger.info(f"[{symbol}] 🎯 Take Profit: {take_profit:.5f} (Reward: {entry_signal.get('reward', 0):.5f})")
            # Log final del RR con detalles
            risk_pips = self._price_to_pips(risk_actual, symbol_info.digits)
            reward_pips = self._price_to_pips(reward_actual, symbol_info.digits)
            self.logger.info(
                f"[{symbol}] 📈 Risk/Reward FINAL: {rr:.2f}:1 (objetivo: {self.min_rr}:1) | "
                f"Risk: {risk_actual:.5f} ({risk_pips:.1f} pips) | "
                f"Reward: {reward_actual:.5f} ({reward_pips:.1f} pips)"
            )
            
            # Verificar que el RR sea exactamente 2.0:1 (con pequeña tolerancia por redondeo)
            if abs(rr - self.min_rr) > 0.05:  # Tolerancia de 0.05 para redondeo
                self.logger.warning(
                    f"[{symbol}] ⚠️  RR ({rr:.2f}:1) difiere del objetivo ({self.min_rr}:1) | "
                    f"Diferencia: {abs(rr - self.min_rr):.2f} | "
                    f"Esto puede deberse a redondeo del broker o restricciones de stop level"
                )
            else:
                self.logger.info(f"[{symbol}] ✅ RR exacto de {self.min_rr}:1 logrado exitosamente")
            self.logger.info(f"[{symbol}] 📦 Volumen: {volume:.2f} lotes (calculado por {self.risk_per_trade_percent}% de riesgo)")
            self.logger.info(f"[{symbol}] {'-'*70}")
            self.logger.info(f"[{symbol}] 📋 Contexto de la Señal:")
            self.logger.info(f"[{symbol}]    • Turtle Soup H4: {turtle_soup.get('sweep_type', 'N/A')} → {turtle_soup.get('direction', 'N/A')}")
            self.logger.info(f"[{symbol}]    • Vela barrida: {turtle_soup.get('swept_candle', 'N/A')} ({turtle_soup.get('swept_extreme', 'N/A')})")
            sweep_price = turtle_soup.get('sweep_price')
            sweep_price_str = f"{sweep_price:.5f}" if sweep_price is not None else 'N/A'
            self.logger.info(f"[{symbol}]    • Precio barrido: {sweep_price_str}")
            target_price_log = turtle_soup.get('target_price')
            target_price_str = f"{target_price_log:.5f}" if target_price_log is not None else 'N/A'
            self.logger.info(f"[{symbol}]    • Objetivo: {target_price_str}")
            if fvg:
                self.logger.info(f"[{symbol}]    • FVG {self.entry_timeframe}: {fvg.get('fvg_type', 'N/A')} ({fvg.get('fvg_bottom', 0):.5f} - {fvg.get('fvg_top', 0):.5f})")
                self.logger.info(f"[{symbol}]    • FVG Estado: {fvg.get('status', 'N/A')} | Entró: {fvg.get('entered_fvg', False)} | Salió: {fvg.get('exited_fvg', False)}")
                self.logger.info(f"[{symbol}]    • Dirección de salida FVG: {fvg.get('exit_direction', 'N/A')}")
            self.logger.info(f"[{symbol}] {'='*70}")
            
            # Ejecutar orden según dirección
            if direction == 'BULLISH':
                result = self.executor.buy(
                    symbol=symbol,
                    volume=volume,
                    price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    comment=f"TurtleSoup H4 + FVG {self.entry_timeframe}"
                )
            else:
                result = self.executor.sell(
                    symbol=symbol,
                    volume=volume,
                    price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    comment=f"TurtleSoup H4 + FVG {self.entry_timeframe}"
                )
            
            if result['success']:
                # Incrementar contador de trades del día
                self.trades_today += 1
                
                self.logger.info(f"[{symbol}] {'='*70}")
                self.logger.info(f"[{symbol}] ✅ ORDEN EJECUTADA EXITOSAMENTE")
                self.logger.info(f"[{symbol}] {'='*70}")
                self.logger.info(f"[{symbol}] 🎫 Ticket: {result['order_ticket']}")
                self.logger.info(f"[{symbol}] 📊 Símbolo: {symbol}")
                self.logger.info(f"[{symbol}] 💰 Precio: {entry_price:.5f}")
                self.logger.info(f"[{symbol}] 📦 Volumen: {volume:.2f} lotes")
                self.logger.info(f"[{symbol}] 🛑 Stop Loss: {stop_loss:.5f}")
                self.logger.info(f"[{symbol}] 🎯 Take Profit: {take_profit:.5f}")
                self.logger.info(f"[{symbol}] 📈 Risk/Reward: {rr:.2f}:1")
                self.logger.info(f"[{symbol}] 📊 Trades hoy: {self.trades_today}/{self.max_trades_per_day}")
                self.logger.info(f"[{symbol}] {'='*70}")
                
                # Guardar orden en base de datos (método disponible en BaseStrategy)
                extra_data = {
                    'turtle_soup': turtle_soup,
                    'entry_signal': entry_signal,
                    'trades_today': self.trades_today,
                    'max_trades_per_day': self.max_trades_per_day
                }
                
                self.save_order_to_db(
                    ticket=result['order_ticket'],
                    symbol=symbol,
                    order_type=direction,  # 'BULLISH' o 'BEARISH' -> convertimos a 'BUY' o 'SELL'
                    entry_price=entry_price,
                    volume=volume,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    rr=rr,
                    comment=f"TurtleSoup H4 + FVG {self.entry_timeframe}",
                    extra_data=extra_data
                )
                
                return {
                    'action': f'{direction}_EXECUTED',
                    'ticket': result['order_ticket'],
                    'turtle_soup': turtle_soup,
                    'entry_signal': entry_signal
                }
            else:
                self.logger.error(f"[{symbol}] {'='*70}")
                self.logger.error(f"[{symbol}] ❌ ERROR AL EJECUTAR ORDEN")
                self.logger.error(f"[{symbol}] {'='*70}")
                self.logger.error(f"[{symbol}] Mensaje: {result.get('message', 'Error desconocido')}")
                self.logger.error(f"[{symbol}] {'='*70}")
                return None
                
        except Exception as e:
            self.logger.error(f"[{symbol}] ❌ Error al ejecutar orden: {e}", exc_info=True)
            return None

