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
        
        # Control de trades ejecutados para evitar duplicados
        self.executed_trades_today = []  # Lista de señales ya ejecutadas hoy (por Turtle Soup)
        
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
                        self.logger.info(f"[{symbol}] 🔄 El bot ahora analizará cada SEGUNDO hasta que se cumplan las condiciones de entrada")
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
                    # Si estaba monitoreando pero el FVG desapareció, cancelar monitoreo
                    if self.monitoring_fvg:
                        self.logger.info(f"[{symbol}] ⏸️  FVG esperado desapareció - Cancelando monitoreo intensivo")
                        self.monitoring_fvg = False
                        self.monitoring_fvg_data = None
                
                # Solo log si no está en monitoreo intensivo (para evitar saturación)
                if not self.monitoring_fvg:
                    self.logger.info(f"[{symbol}] ⏸️  Etapa 3/4: Esperando - No hay señal de entrada FVG válida aún")
            
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
            
            # Evaluar condiciones de entrada
            entry_signal = self._find_fvg_entry(symbol, turtle_soup)
            
            if entry_signal:
                # Condiciones cumplidas - ejecutar orden y cancelar monitoreo
                self.logger.info(f"[{symbol}] ✅ Condiciones cumplidas durante monitoreo intensivo - Ejecutando orden")
                self.monitoring_fvg = False
                self.monitoring_fvg_data = None
                return self._execute_order(symbol, turtle_soup, entry_signal)
            
            # Condiciones aún no cumplidas - seguir monitoreando
            # Log solo cada 10 segundos para no saturar
            import time
            current_time = time.time()
            if not hasattr(self, '_last_monitor_log') or (current_time - self._last_monitor_log) >= 10:
                self.logger.debug(f"[{symbol}] 🔄 Monitoreando FVG en tiempo real... (Estado: {fvg.get('status')}, Entró: {fvg.get('entered_fvg')}, Salió: {fvg.get('exited_fvg')})")
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
            self.executed_trades_today = []  # Resetear también la lista de trades ejecutados
    
    def _check_daily_trade_limit(self, symbol: str) -> bool:
        """
        Verifica si se puede ejecutar un trade según el límite diario
        
        Args:
            symbol: Símbolo a verificar
            
        Returns:
            True si se puede ejecutar, False si se alcanzó el límite
        """
        self._reset_daily_trades_counter()
        
        if self.trades_today >= self.max_trades_per_day:
            self.logger.info(f"[{symbol}] ⏸️  Límite de trades diarios alcanzado: {self.trades_today}/{self.max_trades_per_day}")
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
            
            # Aplicar límite de seguridad de la configuración
            if volume > self.max_position_size:
                volume = self.max_position_size
                self.logger.warning(f"[{symbol}] ⚠️  Volumen calculado excede el límite máximo de configuración ({self.max_position_size}), usando límite")
            
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
            
            exit_direction = fvg.get('exit_direction')
            fvg_bottom = fvg.get('fvg_bottom')
            fvg_top = fvg.get('fvg_top')
            current_price_fvg = fvg.get('current_price')
            self.logger.info(f"[{symbol}] 📊 FVG detectado: {fvg_type} | Estado: {fvg.get('status')} | Entró: {fvg.get('entered_fvg')} | Salió: {fvg.get('exited_fvg')} | Exit Direction: {exit_direction}")
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
            
            # VALIDACIÓN 1: La vela EN FORMACIÓN (vela3) DEBE haber entrado al FVG
            # REGLA ESPECÍFICA POR TIPO DE FVG:
            # - FVG BAJISTA: Usar HIGH de la vela en formación para saber si entró
            # - FVG ALCISTA: Usar LOW de la vela en formación para saber si entró
            candle_entered_fvg = False
            
            if calculated_fvg_type == 'BAJISTA':
                # FVG BAJISTA: El HIGH de la vela en formación debe estar dentro del FVG
                if fvg_bottom <= candle_high <= fvg_top:
                    candle_entered_fvg = True
                    self.logger.info(f"[{symbol}] 📍 Vela entró al FVG BAJISTA: HIGH ({candle_high:.5f}) está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f})")
                else:
                    self.logger.info(
                        f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: Para FVG BAJISTA, HIGH de vela en formación ({candle_high:.5f}) NO está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f})"
                    )
            elif calculated_fvg_type == 'ALCISTA':
                # FVG ALCISTA: El LOW de la vela en formación debe estar dentro del FVG
                if fvg_bottom <= candle_low <= fvg_top:
                    candle_entered_fvg = True
                    self.logger.info(f"[{symbol}] 📍 Vela entró al FVG ALCISTA: LOW ({candle_low:.5f}) está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f})")
                else:
                    self.logger.info(
                        f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: Para FVG ALCISTA, LOW de vela en formación ({candle_low:.5f}) NO está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f})"
                    )
            
            if not candle_entered_fvg:
                self.logger.info(
                    f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: La vela EN FORMACIÓN NO entró al FVG {calculated_fvg_type} | "
                    f"Vela: H={candle_high:.5f} L={candle_low:.5f} C={candle_close:.5f} | "
                    f"FVG: {fvg_bottom:.5f}-{fvg_top:.5f}"
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
            if calculated_fvg_type == 'BAJISTA' and direction == 'BEARISH':
                # FVG BAJISTA + dirección BEARISH: precio debe estar DEBAJO del FVG
                if current_price < fvg_bottom:
                    price_exited_fvg = True
                    exit_direction = 'BAJISTA'
                    self.logger.info(f"[{symbol}] 📍 Precio salió del FVG BAJISTA: Precio actual ({current_price:.5f}) está DEBAJO del FVG Bottom ({fvg_bottom:.5f})")
                else:
                    # Precio está arriba del FVG pero esperábamos salida bajista
                    self.logger.info(
                        f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: Precio salió del FVG pero en dirección incorrecta | "
                        f"Precio actual={current_price:.5f} está ARRIBA del FVG (esperábamos DEBAJO para {direction})"
                    )
                    return None
            elif calculated_fvg_type == 'ALCISTA' and direction == 'BULLISH':
                # FVG ALCISTA + dirección BULLISH: precio debe estar ARRIBA del FVG
                if current_price > fvg_top:
                    price_exited_fvg = True
                    exit_direction = 'ALCISTA'
                    self.logger.info(f"[{symbol}] 📍 Precio salió del FVG ALCISTA: Precio actual ({current_price:.5f}) está ARRIBA del FVG Top ({fvg_top:.5f})")
                else:
                    # Precio está debajo del FVG pero esperábamos salida alcista
                    self.logger.info(
                        f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: Precio salió del FVG pero en dirección incorrecta | "
                        f"Precio actual={current_price:.5f} está DEBAJO del FVG (esperábamos ARRIBA para {direction})"
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
            
            # Obtener precio actual
            current_candle = get_candle(self.entry_timeframe, 'ahora', symbol)
            if not current_candle:
                return None
            
            current_price = current_candle.get('close')
            if current_price is None:
                current_price = (current_candle.get('high', 0) + current_candle.get('low', 0)) / 2
            
            # Calcular niveles
            fvg_top = fvg.get('fvg_top')
            fvg_bottom = fvg.get('fvg_bottom')
            target_price = turtle_soup.get('target_price')
            
            if fvg_top is None or fvg_bottom is None or target_price is None:
                return None
            
            # Calcular Stop Loss (debe cubrir todo el FVG + margen adicional para retrocesos)
            fvg_size = fvg_top - fvg_bottom
            # Usar 50% del tamaño del FVG como margen adicional para proteger contra retrocesos
            # Esto asegura que si el precio retrocede y completa el FVG, el SL no se active
            safety_margin = fvg_size * 0.5  # 50% adicional más allá del FVG
            
            if direction == 'BULLISH':
                # Compra: SL debajo del FVG con margen adicional
                # SL = Bottom del FVG - tamaño del FVG - margen adicional
                stop_loss = fvg_bottom - fvg_size - safety_margin
                entry_price = current_price
                take_profit = target_price
                self.logger.info(f"[{symbol}] 🛑 SL calculado: {stop_loss:.5f} (FVG Bottom: {fvg_bottom:.5f} - FVG Size: {fvg_size:.5f} - Safety Margin: {safety_margin:.5f})")
            else:
                # Venta: SL arriba del FVG con margen adicional
                # SL = Top del FVG + tamaño del FVG + margen adicional
                stop_loss = fvg_top + fvg_size + safety_margin
                entry_price = current_price
                take_profit = target_price
                self.logger.info(f"[{symbol}] 🛑 SL calculado: {stop_loss:.5f} (FVG Top: {fvg_top:.5f} + FVG Size: {fvg_size:.5f} + Safety Margin: {safety_margin:.5f})")
            
            # Verificar Risk/Reward mínimo
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            
            if risk == 0:
                return None
            
            rr = reward / risk
            
            self.logger.info(f"[{symbol}] 📈 Calculando RR: Risk={risk:.5f}, Reward={reward:.5f}, RR={rr:.2f} (mínimo requerido: {self.min_rr})")
            
            if rr < self.min_rr:
                self.logger.info(f"[{symbol}] ⏸️  Esperando: RR insuficiente ({rr:.2f} < {self.min_rr}). Intentando optimizar SL...")
                # Intentar ajustar SL si es posible
                adjusted_sl = self._optimize_sl(entry_price, take_profit, direction, fvg_top, fvg_bottom)
                if adjusted_sl:
                    new_risk = abs(entry_price - adjusted_sl)
                    new_rr = reward / new_risk
                    if new_rr >= self.min_rr:
                        stop_loss = adjusted_sl
                        rr = new_rr
                        self.logger.info(f"[{symbol}] ✅ SL optimizado: Nuevo RR={rr:.2f}")
                    else:
                        self.logger.info(f"[{symbol}] ⏸️  Esperando: SL optimizado aún no alcanza RR mínimo ({new_rr:.2f} < {self.min_rr})")
                        return None
                else:
                    self.logger.info(f"[{symbol}] ⏸️  Esperando: No se pudo optimizar SL para alcanzar RR mínimo")
                    return None
            else:
                self.logger.info(f"[{symbol}] ✅ RR válido: {rr:.2f} >= {self.min_rr} - Etapa 3/4 COMPLETA")
            
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
            safety_margin = fvg_size * 0.5  # 50% adicional más allá del FVG (igual que en el cálculo principal)
            
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
            # ⚠️ CONTROL DE DUPLICADOS: Verificar que no se haya ejecutado ya una orden para esta señal de Turtle Soup
            self._reset_daily_trades_counter()
            
            # Crear identificador único para esta señal de Turtle Soup
            turtle_soup_id = f"{symbol}_{turtle_soup.get('swept_candle', 'unknown')}_{turtle_soup.get('sweep_type', 'unknown')}_{turtle_soup.get('target_price', 0):.5f}"
            
            if turtle_soup_id in self.executed_trades_today:
                self.logger.warning(
                    f"[{symbol}] ⚠️  ORDEN DUPLICADA DETECTADA: Ya se ejecutó una orden para esta señal de Turtle Soup hoy | "
                    f"ID: {turtle_soup_id} | Cancelando orden duplicada"
                )
                return None
            
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
            
            # VALIDACIÓN FINAL 1: La vela EN FORMACIÓN (vela3) DEBE haber entrado al FVG
            # REGLA ESPECÍFICA POR TIPO DE FVG:
            # - FVG BAJISTA: Usar HIGH de la vela en formación
            # - FVG ALCISTA: Usar LOW de la vela en formación
            candle_entered = False
            
            if calculated_fvg_type == 'BAJISTA':
                # FVG BAJISTA: HIGH debe estar dentro del FVG
                if fvg_bottom <= candle_high <= fvg_top:
                    candle_entered = True
                else:
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Para FVG BAJISTA, HIGH de vela en formación ({candle_high:.5f}) NO está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f}) - Cancelando orden"
                    )
                    return None
            elif calculated_fvg_type == 'ALCISTA':
                # FVG ALCISTA: LOW debe estar dentro del FVG
                if fvg_bottom <= candle_low <= fvg_top:
                    candle_entered = True
                else:
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Para FVG ALCISTA, LOW de vela en formación ({candle_low:.5f}) NO está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f}) - Cancelando orden"
                    )
                    return None
            
            if not candle_entered:
                self.logger.error(
                    f"[{symbol}] ❌ VALIDACIÓN FALLIDA: La vela EN FORMACIÓN NO entró al FVG {calculated_fvg_type} | "
                    f"Vela: H={candle_high:.5f} L={candle_low:.5f} C={candle_close:.5f} | "
                    f"FVG: {fvg_bottom:.5f}-{fvg_top:.5f} - Cancelando orden"
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
            if calculated_fvg_type == 'BAJISTA' and direction == 'BEARISH':
                # FVG BAJISTA + dirección BEARISH: precio debe estar DEBAJO del FVG
                if current_price >= fvg_bottom:
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Precio salió del FVG pero en dirección incorrecta | "
                        f"Precio actual={current_price:.5f} debe estar DEBAJO de {fvg_bottom:.5f} para {direction} - Cancelando orden"
                    )
                    return None
            elif calculated_fvg_type == 'ALCISTA' and direction == 'BULLISH':
                # FVG ALCISTA + dirección BULLISH: precio debe estar ARRIBA del FVG
                if current_price <= fvg_top:
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Precio salió del FVG pero en dirección incorrecta | "
                        f"Precio actual={current_price:.5f} debe estar ARRIBA de {fvg_top:.5f} para {direction} - Cancelando orden"
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
            
            direction = entry_signal['direction']
            entry_price = entry_signal['entry_price']
            stop_loss = entry_signal['stop_loss']
            take_profit = entry_signal['take_profit']
            rr = entry_signal['rr']
            fvg = current_fvg  # Usar el FVG actual verificado
            
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
            self.logger.info(f"[{symbol}] 📈 Risk/Reward: {rr:.2f}:1 (mínimo requerido: {self.min_rr}:1)")
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
                
                # Registrar esta señal como ejecutada para evitar duplicados
                turtle_soup_id = f"{symbol}_{turtle_soup.get('swept_candle', 'unknown')}_{turtle_soup.get('sweep_type', 'unknown')}_{turtle_soup.get('target_price', 0):.5f}"
                self.executed_trades_today.append(turtle_soup_id)
                
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
                self.logger.info(f"[{symbol}] 🔒 Señal registrada para evitar duplicados: {turtle_soup_id}")
                self.logger.info(f"[{symbol}] {'='*70}")
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

