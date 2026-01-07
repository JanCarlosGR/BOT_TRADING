"""
Estrategia de Barrido de Niveles Diarios (Daily Levels Sweep)
Detecta cuando un Daily High o Low es tomado y entra cuando el precio regresa en dirección contraria
Funciona 24/7 (sin restricciones de horario)
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
from Base.daily_levels_detector import (
    detect_daily_high_take,
    detect_daily_low_take,
    get_previous_daily_levels
)
from Base.order_executor import OrderExecutor


class DailyLevelsSweepStrategy(BaseStrategy):
    """
    Estrategia de Barrido de Niveles Diarios
    
    Lógica:
    1. Monitorea cuando un Daily High o Low es tomado (barrido)
    2. Espera que el precio regrese al menos 10 pips en dirección contraria
    3. Entra con SL de 100 pips y TP de 200 pips (RR 1:2)
    4. Dirección: Si barrió HIGH → SELL, Si barrió LOW → BUY
    
    Características:
    - Funciona 24/7 (sin restricciones de horario)
    - Detecta la toma incluso si es por solo 1 pip
    - Riesgo configurable (default: 2% de la cuenta)
    """
    
    def __init__(self, config: Dict):
        """
        Inicializa la estrategia de barrido de niveles diarios
        
        Args:
            config: Configuración del bot
        """
        super().__init__(config)
        self.executor = OrderExecutor()
        
        # Configuración de la estrategia
        strategy_config = config.get('strategy_config', {})
        self.lookback_days = strategy_config.get('daily_levels_lookback_days', 5)
        self.tolerance_pips = strategy_config.get('daily_levels_tolerance_pips', 1.0)
        self.retracement_pips = strategy_config.get('daily_levels_retracement_pips', 10.0)
        self.stop_loss_pips = strategy_config.get('daily_levels_stop_loss_pips', 100.0)
        self.take_profit_pips = strategy_config.get('daily_levels_take_profit_pips', 200.0)
        
        # Configuración de gestión de riesgo
        risk_config = config.get('risk_management', {})
        self.risk_per_trade_percent = risk_config.get('risk_per_trade_percent', 2.0)  # Default 2%
        self.max_position_size = risk_config.get('max_position_size', 0.1)
        self.max_trades_per_day = risk_config.get('max_trades_per_day', 10)  # Default 10 para estrategia 24/7
        
        # Contador de trades por día
        self.trades_today = 0
        self.last_trade_date = None
        
        # Flag para indicar si ya se ejecutó una orden por barrido diario hoy
        self.daily_sweep_trade_executed = False
        self.daily_sweep_trade_date = None
        
        # Estado de monitoreo
        self.monitoring_sweep = None  # Dict con información del barrido que estamos monitoreando
        self.sweep_extreme_price = None  # Precio del extremo barrido
        self.sweep_type = None  # 'HIGH' o 'LOW'
        self.sweep_date = None  # Fecha del nivel barrido
        self.sweep_timestamp = None  # Timestamp cuando se detectó el barrido
        
        self.logger.info(f"DailyLevelsSweepStrategy inicializada - Funciona 24/7")
        self.logger.info(f"Lookback: {self.lookback_days} días | Tolerancia: {self.tolerance_pips} pips")
        self.logger.info(f"Retracement mínimo: {self.retracement_pips} pips")
        self.logger.info(f"SL: {self.stop_loss_pips} pips | TP: {self.take_profit_pips} pips (RR 1:2)")
        self.logger.info(f"Riesgo por trade: {self.risk_per_trade_percent}%")
    
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
            # Obtener precio actual
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            
            current_price = float(tick.bid)
            
            # 1. Verificar si hay un barrido activo que estamos monitoreando
            if self.monitoring_sweep:
                # Verificar si el precio ha regresado lo suficiente
                signal = self._check_retracement_and_enter(symbol, current_price)
                if signal:
                    # Limpiar estado de monitoreo después de entrar
                    self.monitoring_sweep = None
                    self.sweep_extreme_price = None
                    self.sweep_type = None
                    self.sweep_date = None
                    self.sweep_timestamp = None
                    return signal
                
                # Si el barrido ya no es válido, limpiar estado
                if not self._is_sweep_still_valid(symbol):
                    self.logger.info(
                        f"[{symbol}] El barrido de {self.sweep_type} ya no es válido - Limpiando monitoreo"
                    )
                    self.monitoring_sweep = None
                    self.sweep_extreme_price = None
                    self.sweep_type = None
                    self.sweep_date = None
                    self.sweep_timestamp = None
            
            # 2. Detectar nuevos barridos de Daily High y Low simultáneamente
            high_take = detect_daily_high_take(
                symbol, 
                lookback_days=self.lookback_days, 
                tolerance_pips=self.tolerance_pips
            )
            
            low_take = detect_daily_low_take(
                symbol, 
                lookback_days=self.lookback_days, 
                tolerance_pips=self.tolerance_pips
            )
            
            # Verificar si AMBOS fueron tomados
            high_taken = high_take and high_take.get('has_taken')
            low_taken = low_take and low_take.get('has_taken')
            
            if high_taken and low_taken:
                # AMBOS fueron tomados - Esperar al próximo día operativo
                if not hasattr(self, '_last_both_swept_log') or (time.time() - self._last_both_swept_log) >= 300:
                    self.logger.info(
                        f"[{symbol}] ⏸️  AMBOS niveles barridos (HIGH y LOW) detectados | "
                        f"Esperando al próximo día operativo para buscar nuevos barridos"
                    )
                    self._last_both_swept_log = time.time()
                
                # Marcar el día como cerrado
                today = date.today()
                self.daily_sweep_trade_executed = True
                self.daily_sweep_trade_date = today
                return None
            
            # 3. Detectar barrido de Daily High (solo si no se barrió también el LOW)
            if high_taken:
                # Verificar si el barrido es "en vivo" (recién ocurrió)
                if self._is_sweep_live(symbol, current_price, high_take['level_price'], 'HIGH'):
                    # Se detectó un barrido de Daily High EN VIVO
                    level_price = high_take['level_price']
                    level_date = high_take['level_date']
                    
                    # Iniciar monitoreo del barrido
                    self.monitoring_sweep = high_take
                    self.sweep_extreme_price = level_price
                    self.sweep_type = 'HIGH'
                    self.sweep_date = level_date
                    self.sweep_timestamp = time.time()
                    
                    self.logger.info(
                        f"[{symbol}] 🔍 Daily HIGH barrido detectado EN VIVO: {level_price:.5f} ({level_date}) | "
                        f"Precio actual: {current_price:.5f} | "
                        f"Monitoreando retracement de {self.retracement_pips} pips para entrada SELL"
                    )
                    return None  # Aún no hay señal, solo monitoreo
                else:
                    # El barrido ya ocurrió hace tiempo, no es "en vivo"
                    if not hasattr(self, '_last_old_sweep_log') or (time.time() - self._last_old_sweep_log) >= 300:
                        self.logger.debug(
                            f"[{symbol}] Daily HIGH fue barrido pero no es en vivo (ya pasó) - Esperando detección en vivo"
                        )
                        self._last_old_sweep_log = time.time()
            
            # 4. Detectar barrido de Daily Low (solo si no se barrió también el HIGH)
            if low_taken:
                # Verificar si el barrido es "en vivo" (recién ocurrió)
                if self._is_sweep_live(symbol, current_price, low_take['level_price'], 'LOW'):
                    # Se detectó un barrido de Daily Low EN VIVO
                    level_price = low_take['level_price']
                    level_date = low_take['level_date']
                    
                    # Iniciar monitoreo del barrido
                    self.monitoring_sweep = low_take
                    self.sweep_extreme_price = level_price
                    self.sweep_type = 'LOW'
                    self.sweep_date = level_date
                    self.sweep_timestamp = time.time()
                    
                    self.logger.info(
                        f"[{symbol}] 🔍 Daily LOW barrido detectado EN VIVO: {level_price:.5f} ({level_date}) | "
                        f"Precio actual: {current_price:.5f} | "
                        f"Monitoreando retracement de {self.retracement_pips} pips para entrada BUY"
                    )
                    return None  # Aún no hay señal, solo monitoreo
                else:
                    # El barrido ya ocurrió hace tiempo, no es "en vivo"
                    if not hasattr(self, '_last_old_sweep_log') or (time.time() - self._last_old_sweep_log) >= 300:
                        self.logger.debug(
                            f"[{symbol}] Daily LOW fue barrido pero no es en vivo (ya pasó) - Esperando detección en vivo"
                        )
                        self._last_old_sweep_log = time.time()
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error en análisis de Daily Levels Sweep: {e}", exc_info=True)
            return None
    
    def _is_sweep_still_valid(self, symbol: str) -> bool:
        """
        Verifica si el barrido que estamos monitoreando aún es válido
        
        Args:
            symbol: Símbolo a analizar
            
        Returns:
            True si el barrido aún es válido, False si no
        """
        if not self.monitoring_sweep or not self.sweep_type:
            return False
        
        try:
            # Re-detectar el barrido para verificar que aún existe
            if self.sweep_type == 'HIGH':
                high_take = detect_daily_high_take(
                    symbol, 
                    lookback_days=self.lookback_days, 
                    tolerance_pips=self.tolerance_pips
                )
                if high_take and high_take.get('has_taken'):
                    # Verificar que es el mismo nivel
                    if abs(high_take['level_price'] - self.sweep_extreme_price) < 0.0001:
                        return True
            elif self.sweep_type == 'LOW':
                low_take = detect_daily_low_take(
                    symbol, 
                    lookback_days=self.lookback_days, 
                    tolerance_pips=self.tolerance_pips
                )
                if low_take and low_take.get('has_taken'):
                    # Verificar que es el mismo nivel
                    if abs(low_take['level_price'] - self.sweep_extreme_price) < 0.0001:
                        return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error al verificar validez del barrido: {e}", exc_info=True)
            return False
    
    def _check_retracement_and_enter(self, symbol: str, current_price: float) -> Optional[Dict]:
        """
        Verifica si el precio ha regresado lo suficiente y genera señal de entrada
        
        Args:
            symbol: Símbolo a analizar
            current_price: Precio actual
            
        Returns:
            Dict con señal de trading o None
        """
        if not self.monitoring_sweep or not self.sweep_extreme_price or not self.sweep_type:
            return None
        
        try:
            # Obtener información del símbolo para calcular pips
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return None
            
            point = symbol_info.point
            pip_value = point * 10 if symbol_info.digits == 5 else point * 1
            retracement_price = self.retracement_pips * pip_value
            
            if self.sweep_type == 'HIGH':
                # Si barrió HIGH, esperamos que el precio baje (retracement)
                # El precio debe estar al menos 10 pips por debajo del HIGH barrido
                if current_price < (self.sweep_extreme_price - retracement_price):
                    # Calcular distancia del retracement
                    retracement_distance = self.sweep_extreme_price - current_price
                    retracement_pips_actual = retracement_distance / pip_value
                    
                    self.logger.info(
                        f"[{symbol}] ✅ Retracement detectado después de barrido de HIGH | "
                        f"Precio regresó {retracement_pips_actual:.1f} pips | "
                        f"Generando señal SELL"
                    )
                    
                    # Generar señal SELL
                    return self._create_sell_signal(symbol, current_price)
            
            elif self.sweep_type == 'LOW':
                # Si barrió LOW, esperamos que el precio suba (retracement)
                # El precio debe estar al menos 10 pips por encima del LOW barrido
                if current_price > (self.sweep_extreme_price + retracement_price):
                    # Calcular distancia del retracement
                    retracement_distance = current_price - self.sweep_extreme_price
                    retracement_pips_actual = retracement_distance / pip_value
                    
                    self.logger.info(
                        f"[{symbol}] ✅ Retracement detectado después de barrido de LOW | "
                        f"Precio regresó {retracement_pips_actual:.1f} pips | "
                        f"Generando señal BUY"
                    )
                    
                    # Generar señal BUY
                    return self._create_buy_signal(symbol, current_price)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error al verificar retracement: {e}", exc_info=True)
            return None
    
    def _create_buy_signal(self, symbol: str, entry_price: float) -> Optional[Dict]:
        """
        Crea una señal de compra (BUY)
        
        Args:
            symbol: Símbolo
            entry_price: Precio de entrada
            
        Returns:
            Dict con señal de trading
        """
        try:
            # Calcular SL y TP en pips
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return None
            
            point = symbol_info.point
            pip_value = point * 10 if symbol_info.digits == 5 else point * 1
            
            # SL: 100 pips por debajo del entry
            stop_loss = entry_price - (self.stop_loss_pips * pip_value)
            # TP: 200 pips por encima del entry
            take_profit = entry_price + (self.take_profit_pips * pip_value)
            
            # Normalizar precios
            stop_loss = self.executor._normalize_price(symbol, stop_loss)
            take_profit = self.executor._normalize_price(symbol, take_profit)
            
            # Calcular volumen basado en riesgo
            volume = self._calculate_volume_by_risk(symbol, entry_price, stop_loss)
            if volume is None:
                return None
            
            self.logger.info(
                f"[{symbol}] 📊 Señal BUY generada | "
                f"Entry: {entry_price:.5f} | SL: {stop_loss:.5f} ({self.stop_loss_pips} pips) | "
                f"TP: {take_profit:.5f} ({self.take_profit_pips} pips) | RR: 1:2 | "
                f"Volumen: {volume:.2f} lotes"
            )
            
            # Ejecutar orden
            result = self.executor.buy(
                symbol=symbol,
                volume=volume,
                stop_loss=stop_loss,
                take_profit=take_profit,
                comment="Daily Levels Sweep - BUY"
            )
            
            if result['success']:
                # Incrementar contador de trades
                self._reset_daily_trades_counter()
                self.trades_today += 1
                
                # Marcar que se ejecutó una orden por barrido diario hoy
                today = date.today()
                self.daily_sweep_trade_executed = True
                self.daily_sweep_trade_date = today
                
                self.logger.info(
                    f"[{symbol}] ✅ Orden BUY ejecutada exitosamente | "
                    f"Ticket: {result['order_ticket']} | "
                    f"Entry: {entry_price:.5f} | "
                    f"Trades hoy: {self.trades_today}/{self.max_trades_per_day} | "
                    f"Barrido diario ejecutado - Esperando próximo día tradeable"
                )
                return {
                    'action': 'BUY_EXECUTED',
                    'ticket': result['order_ticket'],
                    'entry_price': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'volume': volume,
                    'sweep_type': self.sweep_type,
                    'sweep_level': self.sweep_extreme_price,
                    'sweep_date': self.sweep_date
                }
            else:
                self.logger.error(
                    f"[{symbol}] ❌ Error al ejecutar orden BUY: {result.get('error', 'Unknown error')}"
                )
                return None
                
        except Exception as e:
            self.logger.error(f"Error al crear señal BUY: {e}", exc_info=True)
            return None
    
    def _create_sell_signal(self, symbol: str, entry_price: float) -> Optional[Dict]:
        """
        Crea una señal de venta (SELL)
        
        Args:
            symbol: Símbolo
            entry_price: Precio de entrada
            
        Returns:
            Dict con señal de trading
        """
        try:
            # Calcular SL y TP en pips
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return None
            
            point = symbol_info.point
            pip_value = point * 10 if symbol_info.digits == 5 else point * 1
            
            # SL: 100 pips por encima del entry
            stop_loss = entry_price + (self.stop_loss_pips * pip_value)
            # TP: 200 pips por debajo del entry
            take_profit = entry_price - (self.take_profit_pips * pip_value)
            
            # Normalizar precios
            stop_loss = self.executor._normalize_price(symbol, stop_loss)
            take_profit = self.executor._normalize_price(symbol, take_profit)
            
            # Calcular volumen basado en riesgo
            volume = self._calculate_volume_by_risk(symbol, entry_price, stop_loss)
            if volume is None:
                return None
            
            self.logger.info(
                f"[{symbol}] 📊 Señal SELL generada | "
                f"Entry: {entry_price:.5f} | SL: {stop_loss:.5f} ({self.stop_loss_pips} pips) | "
                f"TP: {take_profit:.5f} ({self.take_profit_pips} pips) | RR: 1:2 | "
                f"Volumen: {volume:.2f} lotes"
            )
            
            # Ejecutar orden
            result = self.executor.sell(
                symbol=symbol,
                volume=volume,
                stop_loss=stop_loss,
                take_profit=take_profit,
                comment="Daily Levels Sweep - SELL"
            )
            
            if result['success']:
                # Incrementar contador de trades
                self._reset_daily_trades_counter()
                self.trades_today += 1
                
                # Marcar que se ejecutó una orden por barrido diario hoy
                today = date.today()
                self.daily_sweep_trade_executed = True
                self.daily_sweep_trade_date = today
                
                self.logger.info(
                    f"[{symbol}] ✅ Orden SELL ejecutada exitosamente | "
                    f"Ticket: {result['order_ticket']} | "
                    f"Entry: {entry_price:.5f} | "
                    f"Trades hoy: {self.trades_today}/{self.max_trades_per_day} | "
                    f"Barrido diario ejecutado - Esperando próximo día tradeable"
                )
                return {
                    'action': 'SELL_EXECUTED',
                    'ticket': result['order_ticket'],
                    'entry_price': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'volume': volume,
                    'sweep_type': self.sweep_type,
                    'sweep_level': self.sweep_extreme_price,
                    'sweep_date': self.sweep_date
                }
            else:
                self.logger.error(
                    f"[{symbol}] ❌ Error al ejecutar orden SELL: {result.get('error', 'Unknown error')}"
                )
                return None
                
        except Exception as e:
            self.logger.error(f"Error al crear señal SELL: {e}", exc_info=True)
            return None
    
    def _calculate_volume_by_risk(self, symbol: str, entry_price: float, stop_loss: float) -> Optional[float]:
        """
        Calcula el volumen basado en el porcentaje de riesgo
        
        Args:
            symbol: Símbolo
            entry_price: Precio de entrada
            stop_loss: Precio de stop loss
            
        Returns:
            Volumen calculado o None si hay error
        """
        try:
            # Obtener balance de la cuenta
            account_info = mt5.account_info()
            if account_info is None:
                self.logger.error(f"[{symbol}] No se pudo obtener información de la cuenta")
                return None
            
            balance = float(account_info.balance)
            risk_amount = balance * (self.risk_per_trade_percent / 100.0)
            
            # Calcular riesgo en precio
            risk_in_price = abs(entry_price - stop_loss)
            
            # Obtener información del símbolo
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return None
            
            tick_size = symbol_info.trade_tick_size
            tick_value = symbol_info.trade_tick_value
            
            volume = None
            
            if tick_size > 0 and tick_value > 0:
                ticks_in_risk = risk_in_price / tick_size
                risk_value_per_lot = ticks_in_risk * tick_value
                
                if risk_value_per_lot > 0:
                    volume = risk_amount / risk_value_per_lot
                else:
                    return None
            else:
                # Fallback aproximado
                pips_in_risk = risk_in_price / 0.0001
                value_per_pip_per_lot = 10.0
                risk_value_per_lot = pips_in_risk * value_per_pip_per_lot
                
                if risk_value_per_lot > 0:
                    volume = risk_amount / risk_value_per_lot
                else:
                    return None
            
            # Normalizar volumen
            volume_step = symbol_info.volume_step
            volume_min = symbol_info.volume_min
            volume_max = symbol_info.volume_max
            
            if volume_step > 0:
                volume = round(volume / volume_step) * volume_step
                if volume < volume_min:
                    volume = volume_min
            
            if volume > volume_max:
                volume = volume_max
                self.logger.warning(f"[{symbol}] ⚠️  Volumen excede máximo, usando máximo: {volume_max}")
            
            if volume < volume_min:
                self.logger.error(f"[{symbol}] ❌ Volumen calculado ({volume:.4f}) es menor al mínimo ({volume_min})")
                return None
            
            self.logger.info(
                f"[{symbol}] 💰 Volumen calculado: {volume:.2f} lotes | "
                f"Riesgo: {self.risk_per_trade_percent}% = {risk_amount:.2f}"
            )
            
            return volume
            
        except Exception as e:
            self.logger.error(f"Error al calcular volumen por riesgo: {e}", exc_info=True)
            return None
    
    def needs_intensive_monitoring(self) -> bool:
        """
        Indica si la estrategia necesita monitoreo intensivo
        
        Returns:
            True si está monitoreando un barrido, False si no
        """
        return self.monitoring_sweep is not None
    
    def is_24_7_strategy(self) -> bool:
        """
        Indica si la estrategia funciona 24/7 (sin restricciones de horario)
        
        Returns:
            True siempre, ya que esta estrategia funciona 24/7
        """
        return True
    
    def _reset_daily_trades_counter(self):
        """Reinicia el contador de trades si cambió el día"""
        today = date.today()
        if self.last_trade_date != today:
            self.trades_today = 0
            self.last_trade_date = today
    
    def _reset_daily_sweep_flag(self):
        """Reinicia el flag de barrido diario si cambió el día"""
        today = date.today()
        if self.daily_sweep_trade_date != today:
            self.daily_sweep_trade_executed = False
            self.daily_sweep_trade_date = None
    
    def has_reached_daily_limit(self) -> bool:
        """
        Verifica si se alcanzó el límite de trades diarios
        
        Returns:
            True si se alcanzó el límite, False si no
        """
        self._reset_daily_trades_counter()
        return self.trades_today >= self.max_trades_per_day
    
    def _is_sweep_live(self, symbol: str, current_price: float, level_price: float, level_type: str) -> bool:
        """
        Verifica si el barrido es "en vivo" (recién ocurrió, no hace tiempo)
        
        Un barrido se considera "en vivo" si:
        - Para HIGH: El precio actual está muy cerca del HIGH (dentro de 5 pips por encima o por debajo)
        - Para LOW: El precio actual está muy cerca del LOW (dentro de 5 pips por encima o por debajo)
        
        Esto indica que el barrido está ocurriendo ahora o acaba de ocurrir, no hace horas.
        
        Args:
            symbol: Símbolo
            current_price: Precio actual
            level_price: Precio del nivel barrido
            level_type: 'HIGH' o 'LOW'
            
        Returns:
            True si el barrido es "en vivo", False si ya pasó hace tiempo
        """
        try:
            # Obtener información del símbolo para calcular pips
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return False
            
            point = symbol_info.point
            pip_value = point * 10 if symbol_info.digits == 5 else point * 1
            
            # Tolerancia para considerar "en vivo": 5 pips
            live_tolerance_pips = 5.0
            live_tolerance_price = live_tolerance_pips * pip_value
            
            if level_type == 'HIGH':
                # Para HIGH: El precio debe estar cerca del HIGH (dentro de 5 pips)
                # Puede estar ligeramente por encima (ya lo barrió) o ligeramente por debajo (está a punto)
                distance = abs(current_price - level_price)
                is_live = distance <= live_tolerance_price
                
                if is_live:
                    self.logger.debug(
                        f"[{symbol}] Barrido HIGH es EN VIVO: Precio {current_price:.5f} está a "
                        f"{distance/pip_value:.1f} pips del HIGH {level_price:.5f}"
                    )
                return is_live
            
            elif level_type == 'LOW':
                # Para LOW: El precio debe estar cerca del LOW (dentro de 5 pips)
                # Puede estar ligeramente por debajo (ya lo barrió) o ligeramente por encima (está a punto)
                distance = abs(current_price - level_price)
                is_live = distance <= live_tolerance_price
                
                if is_live:
                    self.logger.debug(
                        f"[{symbol}] Barrido LOW es EN VIVO: Precio {current_price:.5f} está a "
                        f"{distance/pip_value:.1f} pips del LOW {level_price:.5f}"
                    )
                return is_live
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error al verificar si barrido es en vivo: {e}", exc_info=True)
            return False

