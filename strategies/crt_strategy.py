"""
Estrategia CRT (Candle Range Theory) - Reversión
Combina detección de barridos de liquidez con confirmación multi-temporal
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
from Base.crt_detector import detect_crt_sweep, detect_crt_vayas, detect_engulfing
from Base.news_checker import can_trade_now
from Base.order_executor import OrderExecutor
from Base.fvg_detector import detect_fvg


class CRTStrategy(BaseStrategy):
    """
    Estrategia CRT (Candle Range Theory) - Tipo 1: Reversión
    
    Lógica:
    1. Detecta barridos de liquidez en temporalidad alta (H4 o D1)
    2. Opcionalmente detecta patrón Vayas (agotamiento de tendencia)
    3. Busca confirmación en temporalidad baja (M15 o M5) con velas envolventes
    4. Verifica noticias de alto impacto
    5. Ejecuta orden con RR mínimo 1:2 hacia el extremo opuesto
    """
    
    def __init__(self, config: Dict):
        """
        Inicializa la estrategia CRT
        
        Args:
            config: Configuración del bot
        """
        super().__init__(config)
        self.executor = OrderExecutor()
        
        # Configuración de la estrategia
        strategy_config = config.get('strategy_config', {})
        self.high_timeframe = strategy_config.get('crt_high_timeframe', 'H4')  # H4 o D1
        self.entry_timeframe = strategy_config.get('crt_entry_timeframe', 'M15')  # M15 o M5
        self.min_rr = strategy_config.get('min_rr', 2.0)  # Risk/Reward mínimo
        self.use_vayas = strategy_config.get('crt_use_vayas', False)  # Usar patrón Vayas
        self.use_engulfing = strategy_config.get('crt_use_engulfing', True)  # Confirmar con velas envolventes
        self.lookback = strategy_config.get('crt_lookback', 5)  # Velas a revisar
        
        # Configuración de gestión de riesgo
        risk_config = config.get('risk_management', {})
        self.risk_per_trade_percent = risk_config.get('risk_per_trade_percent', 1.0)
        self.max_trades_per_day = risk_config.get('max_trades_per_day', 2)
        self.max_position_size = risk_config.get('max_position_size', 0.1)
        
        # Contador de trades por día
        self.trades_today = 0
        self.last_trade_date = None
        
        self.logger.info(f"CRTStrategy inicializada - High TF: {self.high_timeframe}, Entry TF: {self.entry_timeframe}, RR: {self.min_rr}")
        self.logger.info(f"Riesgo por trade: {self.risk_per_trade_percent}% | Máximo trades/día: {self.max_trades_per_day}")
        self.logger.info(f"Vayas: {'Habilitado' if self.use_vayas else 'Deshabilitado'} | Engulfing: {'Habilitado' if self.use_engulfing else 'Deshabilitado'}")
    
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        """
        Analiza el mercado usando CRT y genera señales de trading
        
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
                if not hasattr(self, '_last_limit_log') or (time.time() - self._last_limit_log) >= 60:
                    self.logger.info(
                        f"[{symbol}] ⏸️  Límite de trades diarios alcanzado: {self.trades_today}/{self.max_trades_per_day} | "
                        f"Análisis detenido hasta próxima sesión operativa"
                    )
                    self._last_limit_log = time.time()
                return None
            
            # 1. Verificar noticias de alto impacto (5 min antes/después)
            self.logger.info(f"[{symbol}] 📰 Etapa 1/5: Verificando noticias económicas...")
            if not self._check_news(symbol):
                return None
            self.logger.info(f"[{symbol}] ✅ Etapa 1/5: Noticias OK - Puede operar")
            
            # 2. Detectar barrido de liquidez en temporalidad alta
            self.logger.info(f"[{symbol}] 🔍 Etapa 2/5: Buscando barrido de liquidez en {self.high_timeframe}...")
            sweep = detect_crt_sweep(symbol, self.high_timeframe, self.lookback)
            
            if not sweep or not sweep.get('detected'):
                self.logger.info(f"[{symbol}] ⏸️  Etapa 2/5: Esperando - No hay barrido detectado en {self.high_timeframe}")
                return None
            
            sweep_type = sweep.get('sweep_type')
            direction = sweep.get('direction')
            target_price = sweep.get('target_price')
            sweep_price = sweep.get('sweep_price')
            
            self.logger.info(
                f"[{symbol}] ✅ Etapa 2/5 COMPLETA: Barrido detectado - {sweep_type} | "
                f"Dirección esperada: {direction} | TP: {target_price:.5f} | Barrido: {sweep_price:.5f}"
            )
            
            # 3. Opcional: Detectar patrón Vayas (agotamiento de tendencia)
            if self.use_vayas:
                self.logger.info(f"[{symbol}] 🔍 Etapa 3/5: Verificando patrón Vayas en {self.high_timeframe}...")
                vayas = detect_crt_vayas(symbol, self.high_timeframe)
                if vayas and vayas.get('detected'):
                    trend_exhaustion = vayas.get('trend_exhaustion')
                    self.logger.info(f"[{symbol}] ✅ Patrón Vayas detectado - Agotamiento de tendencia: {trend_exhaustion}")
                else:
                    self.logger.info(f"[{symbol}] ⏸️  Patrón Vayas no detectado (continuando con barrido)")
            
            # 4. Buscar confirmación en temporalidad baja (vela envolvente)
            if self.use_engulfing:
                self.logger.info(f"[{symbol}] 🔍 Etapa 4/5: Buscando confirmación con vela envolvente en {self.entry_timeframe}...")
                engulfing = detect_engulfing(symbol, self.entry_timeframe)
                
                if not engulfing or not engulfing.get('detected'):
                    self.logger.info(f"[{symbol}] ⏸️  Etapa 4/5: Esperando - No hay vela envolvente confirmatoria en {self.entry_timeframe}")
                    return None
                
                engulfing_type = engulfing.get('engulfing_type')
                
                # Verificar que la vela envolvente confirme la dirección del barrido
                if direction == 'BEARISH' and engulfing_type != 'BEARISH_ENGULFING':
                    self.logger.info(f"[{symbol}] ⏸️  Vela envolvente ({engulfing_type}) no confirma dirección {direction}")
                    return None
                elif direction == 'BULLISH' and engulfing_type != 'BULLISH_ENGULFING':
                    self.logger.info(f"[{symbol}] ⏸️  Vela envolvente ({engulfing_type}) no confirma dirección {direction}")
                    return None
                
                self.logger.info(f"[{symbol}] ✅ Etapa 4/5 COMPLETA: Vela envolvente {engulfing_type} confirma dirección {direction}")
            
            # 5. Calcular entrada y ejecutar orden
            self.logger.info(f"[{symbol}] 💹 Etapa 5/5: Calculando entrada y ejecutando orden...")
            return self._execute_order(symbol, sweep)
            
        except Exception as e:
            self.logger.error(f"Error en análisis CRT: {e}", exc_info=True)
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
        
        Args:
            symbol: Símbolo a verificar
            
        Returns:
            True si se puede ejecutar, False si hay algún bloqueo
        """
        # Verificar límite de trades diarios desde base de datos
        db_manager = self._get_db_manager()
        if db_manager.enabled:
            strategy_name = 'crt_strategy'
            trades_today_db = db_manager.count_trades_today(strategy=strategy_name, symbol=symbol)
            if trades_today_db >= self.max_trades_per_day:
                self.logger.info(f"[{symbol}] ⏸️  Límite de trades diarios alcanzado (desde BD): {trades_today_db}/{self.max_trades_per_day}")
                self.trades_today = trades_today_db
                return False
            self.trades_today = trades_today_db
        else:
            self._reset_daily_trades_counter()
            if self.trades_today >= self.max_trades_per_day:
                self.logger.info(f"[{symbol}] ⏸️  Límite de trades diarios alcanzado: {self.trades_today}/{self.max_trades_per_day}")
                return False
        
        # Verificar si hay posiciones abiertas
        if self._has_open_positions(symbol):
            return False
        
        return True
    
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
    
    def _calculate_volume_by_risk(self, symbol: str, entry_price: float, stop_loss: float) -> Optional[float]:
        """
        Calcula el volumen basado en el riesgo porcentual de la cuenta
        (Reutiliza la lógica de TurtleSoupFVGStrategy)
        """
        try:
            account_info = mt5.account_info()
            if account_info is None:
                self.logger.error("No se pudo obtener información de la cuenta")
                return None
            
            balance = account_info.balance
            margin_free = account_info.margin_free if hasattr(account_info, 'margin_free') else balance
            
            if balance <= 0:
                self.logger.error(f"[{symbol}] ❌ Balance inválido: {balance}")
                return None
            
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                self.logger.error(f"[{symbol}] No se pudo obtener información del símbolo {symbol}")
                return None
            
            risk_amount = balance * (self.risk_per_trade_percent / 100.0)
            min_balance_required = risk_amount * 2
            if balance < min_balance_required:
                self.logger.error(f"[{symbol}] ❌ Balance insuficiente: Balance={balance:.2f} | Riesgo={risk_amount:.2f}")
                return None
            
            min_margin_required = risk_amount * 3
            if margin_free < min_margin_required:
                self.logger.error(f"[{symbol}] ❌ Margen libre insuficiente: Margen libre={margin_free:.2f}")
                return None
            
            risk_in_price = abs(entry_price - stop_loss)
            if risk_in_price == 0:
                self.logger.error("El riesgo en precio es 0, no se puede calcular volumen")
                return None
            
            tick_size = symbol_info.trade_tick_size
            tick_value = symbol_info.trade_tick_value
            
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
    
    def _execute_order(self, symbol: str, sweep: Dict) -> Optional[Dict]:
        """
        Ejecuta la orden de trading basada en el barrido CRT
        
        Args:
            symbol: Símbolo
            sweep: Información del barrido detectado
            
        Returns:
            Dict con resultado de la orden
        """
        try:
            # Verificar límite de trades por día
            if not self._check_daily_trade_limit(symbol):
                return None
            
            # Verificar posiciones abiertas
            if self._has_open_positions(symbol):
                return None
            
            direction = sweep.get('direction')
            target_price = sweep.get('target_price')
            sweep_price = sweep.get('sweep_price')
            swept_candle = sweep.get('swept_candle', {})
            
            # Obtener precio actual del mercado
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                self.logger.error(f"[{symbol}] ❌ No se pudo obtener precio actual")
                return None
            
            # Calcular niveles de entrada, SL y TP
            if direction == 'BULLISH':
                entry_price = float(tick.ask)
                # SL: Por debajo del precio barrido (con margen)
                stop_loss = sweep_price - (sweep_price * 0.001)  # 0.1% de margen
                take_profit = target_price
            else:  # BEARISH
                entry_price = float(tick.bid)
                # SL: Por encima del precio barrido (con margen)
                stop_loss = sweep_price + (sweep_price * 0.001)  # 0.1% de margen
                take_profit = target_price
            
            # Verificar y ajustar Risk/Reward
            risk = abs(entry_price - stop_loss)
            if risk == 0:
                return None
            
            reward = abs(take_profit - entry_price)
            rr = reward / risk
            
            self.logger.info(f"[{symbol}] 📈 Calculando RR: Risk={risk:.5f}, Reward={reward:.5f}, RR={rr:.2f} (mínimo requerido: {self.min_rr})")
            
            if rr < self.min_rr:
                self.logger.info(f"[{symbol}] ⏸️  RR insuficiente ({rr:.2f} < {self.min_rr})")
                return None
            
            # Calcular volumen
            volume = self._calculate_volume_by_risk(symbol, entry_price, stop_loss)
            if volume is None or volume <= 0:
                self.logger.error(f"[{symbol}] ❌ No se pudo calcular el volumen")
                return None
            
            # Log estructurado de la orden
            self.logger.info(f"[{symbol}] {'='*70}")
            self.logger.info(f"[{symbol}] 💹 EJECUTANDO ORDEN CRT")
            self.logger.info(f"[{symbol}] {'='*70}")
            self.logger.info(f"[{symbol}] 📊 Dirección: {direction} ({'COMPRA' if direction == 'BULLISH' else 'VENTA'})")
            self.logger.info(f"[{symbol}] 💰 Precio de Entrada: {entry_price:.5f}")
            self.logger.info(f"[{symbol}] 🛑 Stop Loss: {stop_loss:.5f} (Risk: {risk:.5f})")
            self.logger.info(f"[{symbol}] 🎯 Take Profit: {take_profit:.5f} (Reward: {reward:.5f})")
            self.logger.info(f"[{symbol}] 📈 Risk/Reward: {rr:.2f}:1")
            self.logger.info(f"[{symbol}] 📦 Volumen: {volume:.2f} lotes")
            self.logger.info(f"[{symbol}] {'-'*70}")
            self.logger.info(f"[{symbol}] 📋 Contexto CRT:")
            self.logger.info(f"[{symbol}]    • Barrido: {sweep.get('sweep_type', 'N/A')} en {sweep.get('timeframe', 'N/A')}")
            self.logger.info(f"[{symbol}]    • Precio barrido: {sweep_price:.5f}")
            self.logger.info(f"[{symbol}]    • Objetivo: {target_price:.5f}")
            self.logger.info(f"[{symbol}] {'='*70}")
            
            # Ejecutar orden
            if direction == 'BULLISH':
                result = self.executor.buy(
                    symbol=symbol,
                    volume=volume,
                    price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    comment=f"CRT {self.high_timeframe} + {self.entry_timeframe}"
                )
            else:
                result = self.executor.sell(
                    symbol=symbol,
                    volume=volume,
                    price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    comment=f"CRT {self.high_timeframe} + {self.entry_timeframe}"
                )
            
            if result['success']:
                self.trades_today += 1
                
                self.logger.info(f"[{symbol}] {'='*70}")
                self.logger.info(f"[{symbol}] ✅ ORDEN EJECUTADA EXITOSAMENTE")
                self.logger.info(f"[{symbol}] {'='*70}")
                self.logger.info(f"[{symbol}] 🎫 Ticket: {result['order_ticket']}")
                self.logger.info(f"[{symbol}] 📊 Trades hoy: {self.trades_today}/{self.max_trades_per_day}")
                self.logger.info(f"[{symbol}] {'='*70}")
                
                # Guardar orden en base de datos
                extra_data = {
                    'sweep': sweep,
                    'trades_today': self.trades_today,
                    'max_trades_per_day': self.max_trades_per_day
                }
                
                self.save_order_to_db(
                    ticket=result['order_ticket'],
                    symbol=symbol,
                    order_type=direction,  # 'BULLISH' o 'BEARISH'
                    entry_price=entry_price,
                    volume=volume,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    rr=rr,
                    comment=f"CRT {self.high_timeframe} + {self.entry_timeframe}",
                    extra_data=extra_data
                )
                
                return {
                    'action': f'{direction}_EXECUTED',
                    'ticket': result['order_ticket'],
                    'sweep': sweep
                }
            else:
                self.logger.error(f"[{symbol}] ❌ ERROR AL EJECUTAR ORDEN: {result.get('message', 'Error desconocido')}")
                return None
                
        except Exception as e:
            self.logger.error(f"[{symbol}] ❌ Error al ejecutar orden CRT: {e}", exc_info=True)
            return None
