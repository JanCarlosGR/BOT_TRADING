"""
Estrategia CRT de Revisión H4 + FVG
Combina detección de CRT de Revisión en H4 con entradas basadas en FVG
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
from Base.crt_revision_detector import detect_crt_revision
from Base.fvg_detector import detect_fvg
from Base.news_checker import can_trade_now
from Base.order_executor import OrderExecutor


class CRTRevisionStrategy(BaseStrategy):
    """
    Estrategia CRT de Revisión H4 + FVG
    
    Lógica:
    1. Detecta CRT de Revisión en H4 (vela 5 AM barre extremos de 1 AM con mecha pero cuerpo cierra dentro del rango)
    2. Define TP basado en extremo OPUESTO de vela 1 AM (el que no fue barrido)
       - Si se barrió el LOW de vela 1 AM → TP = HIGH de vela 1 AM
       - Si se barrió el HIGH de vela 1 AM → TP = LOW de vela 1 AM
       - Esperamos que el precio alcance ese objetivo durante la vela de 9 AM NY
    3. Verifica noticias de alto impacto
    4. Busca entrada en FVG según la dirección hacia el TP (extremo opuesto)
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
        self.entry_timeframe = strategy_config.get('crt_entry_timeframe', 'M5')  # M1, M5, M15, etc. (configurable)
        self.min_rr = strategy_config.get('min_rr', 2.0)  # Risk/Reward mínimo
        
        # Configuración de gestión de riesgo
        risk_config = config.get('risk_management', {})
        self.risk_per_trade_percent = risk_config.get('risk_per_trade_percent', 1.0)
        self.max_trades_per_day = risk_config.get('max_trades_per_day', 2)
        self.max_position_size = risk_config.get('max_position_size', 0.1)
        
        # Contador de trades por día
        self.trades_today = 0
        self.last_trade_date = None
        
        # Estado de monitoreo intensivo de FVG
        self.monitoring_fvg = False
        self.monitoring_fvg_data = None
        
        self.logger.info(f"CRTRevisionStrategy inicializada - Entry: {self.entry_timeframe}, RR: {self.min_rr}")
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
            
            # 2. Detectar CRT de Revisión en H4
            self.logger.info(f"[{symbol}] 🔍 Etapa 2/4: Buscando CRT de Revisión en H4...")
            crt_revision = detect_crt_revision(symbol)
            
            if not crt_revision or not crt_revision.get('detected'):
                # Si estaba monitoreando, cancelar monitoreo
                if self.monitoring_fvg:
                    self.logger.info(f"[{symbol}] ⏸️  CRT de Revisión desapareció - Cancelando monitoreo intensivo")
                    self.monitoring_fvg = False
                    self.monitoring_fvg_data = None
                self.logger.info(f"[{symbol}] ⏸️  Etapa 2/4: Esperando - No hay CRT de Revisión detectado en H4")
                return None
            
            sweep_type = crt_revision.get('sweep_type')
            direction = crt_revision.get('direction')
            target_price = crt_revision.get('target_price')
            sweep_price = crt_revision.get('sweep_price')
            swept_extreme = crt_revision.get('swept_extreme')
            body_inside_range = crt_revision.get('body_inside_range', False)
            
            # Determinar tipo de CRT de forma clara
            crt_type_name = "REVISIÓN"
            
            # Determinar objetivo según el tipo de CRT de Revisión
            # El objetivo es el extremo OPUESTO de la vela 1 AM (el que no fue barrido)
            target_extreme = None
            if swept_extreme == 'low':
                # Se barrió el LOW de vela 1 AM → TP = HIGH de vela 1 AM
                target_extreme = "HIGH de vela 1 AM (extremo opuesto)"
            elif swept_extreme == 'high':
                # Se barrió el HIGH de vela 1 AM → TP = LOW de vela 1 AM
                target_extreme = "LOW de vela 1 AM (extremo opuesto)"
            
            # Log estructurado y claro
            self.logger.info(f"[{symbol}] {'='*70}")
            self.logger.info(f"[{symbol}] ✅ CRT DE REVISIÓN DETECTADO - Etapa 2/4 COMPLETA")
            self.logger.info(f"[{symbol}] {'='*70}")
            self.logger.info(f"[{symbol}] 📊 TIPO DE CRT: {crt_type_name}")
            self.logger.info(f"[{symbol}] 📍 Detalles del Patrón:")
            self.logger.info(f"[{symbol}]    • Barrido: Vela 5 AM barrió {swept_extreme.upper()} de vela 1 AM (con mecha)")
            sweep_price_str = f"{sweep_price:.5f}" if sweep_price is not None else 'N/A'
            self.logger.info(f"[{symbol}]    • Precio barrido: {sweep_price_str}")
            self.logger.info(f"[{symbol}]    • Cierre: Cuerpo de vela 5 AM cerró DENTRO del rango de vela 1 AM")
            self.logger.info(f"[{symbol}]    • Confirmación: Cuerpo dentro del rango = {body_inside_range}")
            self.logger.info(f"[{symbol}] {'-'*70}")
            self.logger.info(f"[{symbol}] 🎯 OBJETIVO (TP) SEGÚN CRT DE REVISIÓN:")
            self.logger.info(f"[{symbol}]    • Tipo: {crt_type_name}")
            self.logger.info(f"[{symbol}]    • Extremo barrido: {swept_extreme.upper()} de vela 1 AM")
            self.logger.info(f"[{symbol}]    • Objetivo: {target_extreme}")
            target_price_str = f"{target_price:.5f}" if target_price is not None else 'N/A'
            self.logger.info(f"[{symbol}]    • Precio objetivo (TP): {target_price_str}")
            self.logger.info(f"[{symbol}]    • Vela donde esperamos alcanzar: Vela 9 AM NY")
            self.logger.info(f"[{symbol}]    • Dirección esperada: {direction}")
            self.logger.info(f"[{symbol}] {'='*70}")
            
            # ⚠️ VERIFICACIÓN CRÍTICA: Si el objetivo fue alcanzado por la vela 9 AM y no hay entradas, detener análisis
            candle_9am = crt_revision.get('candle_9am')
            if candle_9am:
                candle_9am_high = candle_9am.get('high')
                candle_9am_low = candle_9am.get('low')
                
                # Verificar si el objetivo fue alcanzado
                objective_reached = False
                if direction == 'BULLISH' and candle_9am_high and target_price:
                    # Para Revisión con objetivo HIGH: El HIGH de la vela 9 AM debe ser >= al objetivo (HIGH de vela 1 AM)
                    if candle_9am_high >= target_price:
                        objective_reached = True
                elif direction == 'BEARISH' and candle_9am_low and target_price:
                    # Para Revisión con objetivo LOW: El LOW de la vela 9 AM debe ser <= al objetivo (LOW de vela 1 AM)
                    if candle_9am_low <= target_price:
                        objective_reached = True
                
                if objective_reached:
                    # Verificar si hay posiciones abiertas para este símbolo
                    positions = mt5.positions_get(symbol=symbol)
                    has_open_positions = positions is not None and len(positions) > 0
                    
                    if not has_open_positions:
                        # El objetivo fue alcanzado y no hay entradas al mercado
                        self.logger.info(f"[{symbol}] {'='*70}")
                        self.logger.info(f"[{symbol}] 🎯 OBJETIVO DEL CRT DE REVISIÓN ALCANZADO")
                        self.logger.info(f"[{symbol}] {'='*70}")
                        self.logger.info(f"[{symbol}] 📊 Tipo de CRT: {crt_type_name}")
                        self.logger.info(f"[{symbol}] 🎯 Objetivo esperado: {target_price_str}")
                        if direction == 'BULLISH':
                            self.logger.info(f"[{symbol}] 📈 Vela 9 AM HIGH: {candle_9am_high:.5f} >= Objetivo: {target_price:.5f}")
                        else:
                            self.logger.info(f"[{symbol}] 📉 Vela 9 AM LOW: {candle_9am_low:.5f} <= Objetivo: {target_price:.5f}")
                        self.logger.info(f"[{symbol}] 💼 Posiciones abiertas: {len(positions) if positions else 0}")
                        self.logger.info(f"[{symbol}] {'-'*70}")
                        self.logger.info(f"[{symbol}] ⏸️  DETENIENDO ANÁLISIS: El objetivo fue tomado por la vela 9 AM")
                        self.logger.info(f"[{symbol}]    y no se realizaron entradas al mercado.")
                        self.logger.info(f"[{symbol}]    El análisis continuará en la próxima sesión operativa.")
                        self.logger.info(f"[{symbol}] {'='*70}")
                        return None
                    else:
                        # El objetivo fue alcanzado pero hay posiciones abiertas, continuar monitoreo
                        self.logger.info(f"[{symbol}] 🎯 Objetivo alcanzado por vela 9 AM, pero hay posiciones abiertas - Continuando análisis")
            
            # 3. Buscar entrada en FVG según la dirección hacia el TP (extremo opuesto)
            self.logger.info(f"[{symbol}] 🔍 Etapa 3/4: Buscando entrada en FVG ({self.entry_timeframe})...")
            entry_signal = self._find_fvg_entry(symbol, crt_revision)
            
            if entry_signal:
                # 4. Ejecutar orden
                self.logger.info(f"[{symbol}] 💹 Etapa 4/4: Ejecutando orden...")
                return self._execute_order(symbol, crt_revision, entry_signal)
            else:
                # Verificar si hay un FVG esperado para activar monitoreo intensivo
                fvg = detect_fvg(symbol, self.entry_timeframe)
                if fvg and self._is_expected_fvg(fvg, crt_revision):
                    # Activar monitoreo intensivo solo si no está ya activo
                    if not self.monitoring_fvg:
                        # Determinar tipo de CRT para logs
                        crt_type_name = "REVISIÓN"
                        
                        swept_extreme_log = crt_revision.get('swept_extreme')
                        target_extreme = None
                        if swept_extreme_log == 'low':
                            target_extreme = "HIGH de vela 1 AM (extremo opuesto)"
                        elif swept_extreme_log == 'high':
                            target_extreme = "LOW de vela 1 AM (extremo opuesto)"
                        
                        target_price_log = crt_revision.get('target_price')
                        target_price_str = f"{target_price_log:.5f}" if target_price_log is not None else 'N/A'
                        
                        self.logger.info(f"[{symbol}] {'='*70}")
                        self.logger.info(f"[{symbol}] 🔄 FVG ESPERADO DETECTADO - ACTIVANDO MONITOREO INTENSIVO")
                        self.logger.info(f"[{symbol}] {'='*70}")
                        self.logger.info(f"[{symbol}] 📊 CRT DETECTADO: {crt_type_name}")
                        self.logger.info(f"[{symbol}] 🎯 OBJETIVO SEGÚN CRT DE REVISIÓN: {target_extreme} = {target_price_str}")
                        self.logger.info(f"[{symbol}] {'-'*70}")
                        self.logger.info(f"[{symbol}] 📊 FVG {fvg.get('fvg_type')} detectado: {fvg.get('fvg_bottom', 0):.5f} - {fvg.get('fvg_top', 0):.5f}")
                        self.logger.info(f"[{symbol}] 📊 Estado FVG: {fvg.get('status')} | Entró: {fvg.get('entered_fvg')} | Salió: {fvg.get('exited_fvg')}")
                        self.logger.info(f"[{symbol}] 🔄 El bot ahora analizará cada SEGUNDO evaluando:")
                        self.logger.info(f"[{symbol}]    • Si las 3 velas forman el FVG esperado")
                        self.logger.info(f"[{symbol}]    • Si la vela EN FORMACIÓN entró al FVG (HIGH para BAJISTA, LOW para ALCISTA)")
                        self.logger.info(f"[{symbol}]    • Si el precio actual salió del FVG en la dirección correcta")
                        self.logger.info(f"[{symbol}] {'='*70}")
                        self.monitoring_fvg = True
                        self.monitoring_fvg_data = {
                            'crt_revision': crt_revision,
                            'fvg': fvg
                        }
                    else:
                        # Actualizar datos del FVG si ya está monitoreando
                        self.monitoring_fvg_data['fvg'] = fvg
                        self.monitoring_fvg_data['crt_revision'] = crt_revision
                        if not hasattr(self, '_last_fvg_update_log') or (time.time() - self._last_fvg_update_log) >= 10:
                            self.logger.debug(f"[{symbol}] 🔄 Monitoreando FVG en tiempo real... Estado: {fvg.get('status')}")
                            self._last_fvg_update_log = time.time()
                else:
                    # Si estaba monitoreando pero el FVG desapareció o no es el esperado, cancelar monitoreo
                    if self.monitoring_fvg:
                        self.logger.info(f"[{symbol}] ⏸️  FVG esperado desapareció o cambió - Cancelando monitoreo intensivo")
                        self.monitoring_fvg = False
                        self.monitoring_fvg_data = None
                
                # Solo log si no está en monitoreo intensivo
                if not self.monitoring_fvg:
                    # Mostrar información del CRT detectado mientras espera entrada FVG
                    crt_type_name = "REVISIÓN"
                    
                    swept_extreme_log = crt_revision.get('swept_extreme')
                    target_extreme = None
                    if swept_extreme_log == 'low':
                        target_extreme = "HIGH de vela 1 AM (extremo opuesto)"
                    elif swept_extreme_log == 'high':
                        target_extreme = "LOW de vela 1 AM (extremo opuesto)"
                    
                    target_price_log = crt_revision.get('target_price')
                    target_price_str = f"{target_price_log:.5f}" if target_price_log is not None else 'N/A'
                    
                    self.logger.info(f"[{symbol}] ⏸️  Etapa 3/4: Esperando entrada FVG válida")
                    self.logger.info(f"[{symbol}]    • CRT detectado: {crt_type_name}")
                    self.logger.info(f"[{symbol}]    • Objetivo según CRT de Revisión: {target_extreme} = {target_price_str}")
                    self.logger.info(f"[{symbol}]    • Esperamos alcanzar durante: Vela 9 AM NY")
                    self.logger.info(f"[{symbol}]    • Buscando FVG {self.entry_timeframe} para entrada...")
            
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
    
    def _is_expected_fvg(self, fvg: Dict, crt_revision: Dict) -> bool:
        """
        Verifica si un FVG es el esperado según el CRT de Revisión
        
        Args:
            fvg: Información del FVG
            crt_revision: Información del CRT de Revisión
            
        Returns:
            True si el FVG es el esperado
        """
        try:
            direction = crt_revision.get('direction')
            fvg_type = fvg.get('fvg_type')
            
            # Determinar qué tipo de FVG buscamos según la dirección hacia el TP (extremo opuesto)
            # El FVG debe estar en la MISMA dirección del objetivo (extremo opuesto de vela 1 AM)
            # - Revisión: Si se barrió LOW → TP = HIGH de vela 1 AM → busca FVG ALCISTA (para ir hacia arriba)
            # - Revisión: Si se barrió HIGH → TP = LOW de vela 1 AM → busca FVG BAJISTA (para ir hacia abajo)
            expected_fvg_type = None
            if direction == 'BULLISH':
                # Objetivo es HIGH de vela 1 AM (extremo opuesto) → necesitamos FVG ALCISTA para ir hacia arriba
                expected_fvg_type = 'ALCISTA'
            elif direction == 'BEARISH':
                # Objetivo es LOW de vela 1 AM (extremo opuesto) → necesitamos FVG BAJISTA para ir hacia abajo
                expected_fvg_type = 'BAJISTA'
            
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
            
            crt_revision = self.monitoring_fvg_data.get('crt_revision')
            if not crt_revision:
                self.monitoring_fvg = False
                self.monitoring_fvg_data = None
                return None
            
            # Verificar que el CRT de Revisión aún existe
            current_crt = detect_crt_revision(symbol)
            if not current_crt or not current_crt.get('detected'):
                self.logger.info(f"[{symbol}] ⏸️  CRT de Revisión desapareció durante monitoreo - Cancelando")
                self.monitoring_fvg = False
                self.monitoring_fvg_data = None
                return None
            
            # ⚠️ VERIFICACIÓN: Si el objetivo fue alcanzado por la vela 9 AM y no hay entradas, detener análisis
            direction = crt_revision.get('direction')
            target_price = crt_revision.get('target_price')
            candle_9am = crt_revision.get('candle_9am')
            
            if candle_9am and target_price:
                candle_9am_high = candle_9am.get('high')
                candle_9am_low = candle_9am.get('low')
                
                # Verificar si el objetivo fue alcanzado
                objective_reached = False
                if direction == 'BULLISH' and candle_9am_high:
                    if candle_9am_high >= target_price:
                        objective_reached = True
                elif direction == 'BEARISH' and candle_9am_low:
                    if candle_9am_low <= target_price:
                        objective_reached = True
                
                if objective_reached:
                    # Verificar si hay posiciones abiertas
                    positions = mt5.positions_get(symbol=symbol)
                    has_open_positions = positions is not None and len(positions) > 0
                    
                    if not has_open_positions:
                        # Determinar tipo de CRT para logs
                        crt_type_name = "REVISIÓN"
                        target_price_str = f"{target_price:.5f}"
                        
                        self.logger.info(f"[{symbol}] {'='*70}")
                        self.logger.info(f"[{symbol}] 🎯 OBJETIVO DEL CRT DE CONTINUACIÓN ALCANZADO (durante monitoreo)")
                        self.logger.info(f"[{symbol}] {'='*70}")
                        self.logger.info(f"[{symbol}] 📊 Tipo de CRT: {crt_type_name}")
                        self.logger.info(f"[{symbol}] 🎯 Objetivo esperado: {target_price_str}")
                        if direction == 'BULLISH':
                            self.logger.info(f"[{symbol}] 📈 Vela 9 AM HIGH: {candle_9am_high:.5f} >= Objetivo: {target_price:.5f}")
                        else:
                            self.logger.info(f"[{symbol}] 📉 Vela 9 AM LOW: {candle_9am_low:.5f} <= Objetivo: {target_price:.5f}")
                        self.logger.info(f"[{symbol}] 💼 Posiciones abiertas: {len(positions) if positions else 0}")
                        self.logger.info(f"[{symbol}] {'-'*70}")
                        self.logger.info(f"[{symbol}] ⏸️  DETENIENDO MONITOREO Y ANÁLISIS: El objetivo fue tomado por la vela 9 AM")
                        self.logger.info(f"[{symbol}]    y no se realizaron entradas al mercado.")
                        self.logger.info(f"[{symbol}]    El análisis continuará en la próxima sesión operativa.")
                        self.logger.info(f"[{symbol}] {'='*70}")
                        
                        # Cancelar monitoreo
                        self.monitoring_fvg = False
                        self.monitoring_fvg_data = None
                        return None
            
            # Verificar que el FVG aún existe y es el esperado
            fvg = detect_fvg(symbol, self.entry_timeframe)
            if not fvg or not self._is_expected_fvg(fvg, crt_revision):
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
            direction = crt_revision.get('direction')
            
            # Verificar si el precio está dentro del FVG
            price_inside_fvg = (fvg_bottom <= current_price <= fvg_top) if fvg_bottom and fvg_top else False
            
            # Si el precio está dentro del FVG, esperar a que salga en la dirección esperada
            if price_inside_fvg:
                current_time = time.time()
                if not hasattr(self, '_last_inside_fvg_log') or (current_time - self._last_inside_fvg_log) >= 10:
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
                return None
            
            # El precio está fuera del FVG - evaluar condiciones de entrada
            entry_signal = self._find_fvg_entry(symbol, crt_revision)
            
            if entry_signal:
                # Condiciones cumplidas - ejecutar orden y cancelar monitoreo
                self.logger.info(f"[{symbol}] ✅ Condiciones cumplidas durante monitoreo intensivo - Precio salió del FVG en dirección esperada - Ejecutando orden")
                self.monitoring_fvg = False
                self.monitoring_fvg_data = None
                return self._execute_order(symbol, crt_revision, entry_signal)
            
            # El precio salió del FVG pero no en la dirección esperada, o condiciones no cumplidas
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
        
        Args:
            symbol: Símbolo a verificar
            
        Returns:
            True si se puede ejecutar, False si hay algún bloqueo
        """
        # Verificar límite de trades diarios desde base de datos
        db_manager = self._get_db_manager()
        if db_manager.enabled:
            strategy_name = 'crt_revision'
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
    
    def _find_fvg_entry(self, symbol: str, crt_revision: Dict) -> Optional[Dict]:
        """
        Busca entrada en FVG en la MISMA dirección del objetivo del CRT
        - Revisión: Si se barrió LOW de vela 1 AM → TP = HIGH de vela 1 AM → busca FVG ALCISTA (para ir hacia arriba)
        - Revisión: Si se barrió HIGH de vela 1 AM → TP = LOW de vela 1 AM → busca FVG BAJISTA (para ir hacia abajo)
        REUTILIZA LA MISMA LÓGICA DE TURTLE SOUP FVG
        
        Args:
            symbol: Símbolo
            crt_revision: Información del CRT de Continuación detectado
            
        Returns:
            Dict con señal de entrada o None
        """
        try:
            # Detectar FVG en la temporalidad de entrada
            fvg = detect_fvg(symbol, self.entry_timeframe)
            
            if not fvg:
                self.logger.info(f"[{symbol}] ⏸️  Esperando: No hay FVG detectado en {self.entry_timeframe}")
                return None
            
            sweep_type = crt_revision.get('sweep_type')
            direction = crt_revision.get('direction')
            fvg_type = fvg.get('fvg_type')
            
            # Verificar si el FVG es el esperado según el CRT de Revisión
            if not self._is_expected_fvg(fvg, crt_revision):
                swept_extreme = crt_revision.get('swept_extreme')
                self.logger.info(f"[{symbol}] ⏸️  FVG detectado ({fvg_type}) no es el esperado según CRT de Revisión (barrió {swept_extreme} → dirección {direction})")
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
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, 3)
            
            if rates is None or len(rates) < 3:
                self.logger.error(f"[{symbol}] ❌ No se pudo obtener las 3 velas necesarias (necesitamos vela en formación + 2 anteriores)")
                return None
            
            # Ordenar por tiempo para tener: vela1 (más antigua), vela2 (del medio), vela3 (actual/en formación)
            candles_data = []
            for i, candle_data in enumerate(rates):
                candles_data.append({
                    'open': float(candle_data['open']),
                    'high': float(candle_data['high']),
                    'low': float(candle_data['low']),
                    'close': float(candle_data['close']),
                    'time': datetime.fromtimestamp(candle_data['time']),
                    'index': i
                })
            
            candles_data = sorted(candles_data, key=lambda x: x['time'])
            vela1 = candles_data[0]  # Más antigua
            vela2 = candles_data[1]    # Del medio
            vela3 = candles_data[2]    # Actual/en formación
            
            self.logger.info(f"[{symbol}] 📊 Analizando 3 velas para formar FVG:")
            self.logger.info(f"[{symbol}]    • Vela1 (antigua): {vela1['time'].strftime('%Y-%m-%d %H:%M:%S')} | H={vela1['high']:.5f} L={vela1['low']:.5f}")
            self.logger.info(f"[{symbol}]    • Vela2 (medio): {vela2['time'].strftime('%Y-%m-%d %H:%M:%S')} | H={vela2['high']:.5f} L={vela2['low']:.5f}")
            self.logger.info(f"[{symbol}]    • Vela3 (EN FORMACIÓN): {vela3['time'].strftime('%Y-%m-%d %H:%M:%S')} | H={vela3['high']:.5f} L={vela3['low']:.5f} C={vela3['close']:.5f}")
            
            # VALIDACIÓN 0: Verificar que las 3 velas forman el FVG esperado
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
                self.logger.info(f"[{symbol}] ✅ FVG ALCISTA formado por las 3 velas: {calculated_fvg_bottom:.5f} - {calculated_fvg_top:.5f}")
            
            # Verificar FVG BAJISTA entre vela1 y vela3
            elif vela1['high'] > vela3['low'] and vela3['high'] < vela1['low']:
                calculated_fvg_bottom = vela3['high']
                calculated_fvg_top = vela1['low']
                calculated_fvg_type = 'BAJISTA'
                fvg_formed = True
                self.logger.info(f"[{symbol}] ✅ FVG BAJISTA formado por las 3 velas: {calculated_fvg_bottom:.5f} - {calculated_fvg_top:.5f}")
            
            if not fvg_formed:
                self.logger.info(f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: Las 3 velas NO forman un FVG válido")
                return None
            
            # Verificar que el FVG formado es del tipo esperado según el CRT de Revisión
            if calculated_fvg_type != fvg_type:
                self.logger.info(
                    f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: FVG formado es {calculated_fvg_type} pero esperábamos {fvg_type} "
                    f"(según CRT {sweep_type} + dirección {direction})"
                )
                return None
            
            # Verificar que el FVG calculado coincide con el detectado (con tolerancia pequeña)
            tolerance = abs(fvg_top - fvg_bottom) * 0.01
            if abs(calculated_fvg_bottom - fvg_bottom) > tolerance or abs(calculated_fvg_top - fvg_top) > tolerance:
                self.logger.warning(
                    f"[{symbol}] ⚠️  FVG calculado difiere del detectado: "
                    f"Calculado: {calculated_fvg_bottom:.5f}-{calculated_fvg_top:.5f} | "
                    f"Detectado: {fvg_bottom:.5f}-{fvg_top:.5f}"
                )
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
            candle_entered_fvg = False
            
            if calculated_fvg_type == 'BAJISTA':
                if fvg_bottom <= candle_high <= fvg_top:
                    candle_entered_fvg = True
                    self.logger.info(f"[{symbol}] ✅ Vela entró al FVG BAJISTA: HIGH ({candle_high:.5f}) está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f})")
                else:
                    self.logger.warning(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Para FVG BAJISTA, HIGH de vela ({candle_high:.5f}) NO está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f}) | "
                        f"La vela NO entró al FVG - NO SE PUEDE EJECUTAR ORDEN"
                    )
                    return None
            elif calculated_fvg_type == 'ALCISTA':
                if fvg_bottom <= candle_low <= fvg_top:
                    candle_entered_fvg = True
                    self.logger.info(f"[{symbol}] ✅ Vela entró al FVG ALCISTA: LOW ({candle_low:.5f}) está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f})")
                else:
                    self.logger.warning(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Para FVG ALCISTA, LOW de vela ({candle_low:.5f}) NO está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f}) | "
                        f"La vela NO entró al FVG - NO SE PUEDE EJECUTAR ORDEN"
                    )
                    return None
            
            if not candle_entered_fvg:
                self.logger.error(
                    f"[{symbol}] ❌ VALIDACIÓN FALLIDA: La vela EN FORMACIÓN NO entró al FVG {calculated_fvg_type} | "
                    f"Vela: H={candle_high:.5f} L={candle_low:.5f} C={candle_close:.5f} | "
                    f"FVG: {fvg_bottom:.5f}-{fvg_top:.5f} | NO SE EJECUTARÁ ORDEN"
                )
                return None
            
            self.logger.info(f"[{symbol}] ✅ Vela EN FORMACIÓN entró al FVG {calculated_fvg_type}: H={candle_high:.5f} L={candle_low:.5f}")
            
            # VALIDACIÓN 2: El precio actual DEBE haber salido del FVG en la dirección correcta
            price_exited_fvg = False
            exit_direction = None
            
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
                if current_price < fvg_bottom:
                    price_exited_fvg = True
                    exit_direction = 'BAJISTA'
                    self.logger.info(f"[{symbol}] 📍 Precio salió del FVG BAJISTA: Precio actual ({current_price:.5f}) está DEBAJO del FVG Bottom ({fvg_bottom:.5f})")
                else:
                    self.logger.info(
                        f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: Precio salió del FVG pero en dirección incorrecta | "
                        f"Precio actual={current_price:.5f} está ARRIBA del FVG (esperábamos DEBAJO para {direction})"
                    )
                    return None
            elif calculated_fvg_type == 'ALCISTA' and direction == 'BULLISH':
                if current_price > fvg_top:
                    price_exited_fvg = True
                    exit_direction = 'ALCISTA'
                    self.logger.info(f"[{symbol}] 📍 Precio salió del FVG ALCISTA: Precio actual ({current_price:.5f}) está ARRIBA del FVG Top ({fvg_top:.5f})")
                else:
                    self.logger.info(
                        f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: Precio salió del FVG pero en dirección incorrecta | "
                        f"Precio actual={current_price:.5f} está DEBAJO del FVG (esperábamos ARRIBA para {direction})"
                    )
                    return None
            else:
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
            
            # Verificar tipo de FVG según la dirección del objetivo del CRT de Revisión
            # El FVG debe estar en la MISMA dirección del objetivo (extremo opuesto de vela 1 AM)
            expected_fvg_type = None
            if direction == 'BULLISH':
                # Revisión: objetivo es HIGH de vela 1 AM (extremo opuesto) → necesitamos FVG ALCISTA
                expected_fvg_type = 'ALCISTA'
            elif direction == 'BEARISH':
                # Revisión: objetivo es LOW de vela 1 AM (extremo opuesto) → necesitamos FVG BAJISTA
                expected_fvg_type = 'BAJISTA'
            
            if expected_fvg_type and fvg_type != expected_fvg_type:
                self.logger.info(f"[{symbol}] ⏸️  Esperando: FVG {fvg_type} detectado, pero necesitamos FVG {expected_fvg_type} (dirección {direction} → objetivo hacia {'ARRIBA' if direction == 'BULLISH' else 'ABAJO'})")
                return None
            
            self.logger.info(f"[{symbol}] ✅ FVG {fvg_type} correcto para la estrategia (dirección {direction} → objetivo hacia {'ARRIBA' if direction == 'BULLISH' else 'ABAJO'})")
            self.logger.info(f"[{symbol}] ✅ Condiciones cumplidas - Listo para calcular entrada")
            
            # Obtener precio actual (bid para venta, ask para compra)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            
            # Calcular niveles
            fvg_top = fvg.get('fvg_top')
            fvg_bottom = fvg.get('fvg_bottom')
            target_price = crt_revision.get('target_price')  # TP viene del extremo opuesto de la vela 1 AM (CRT de Revisión)
            
            if fvg_top is None or fvg_bottom is None or target_price is None:
                return None
            
            # Calcular Stop Loss (debe cubrir todo el FVG + margen adicional para retrocesos)
            fvg_size = fvg_top - fvg_bottom
            
            # Obtener información del símbolo para calcular spread y distancia mínima
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return None
            
            spread_points = symbol_info.spread
            point = symbol_info.point
            spread_price = spread_points * point
            
            # Usar 50% del tamaño del FVG como margen adicional para proteger contra retrocesos
            safety_margin = fvg_size * 0.5
            
            # Distancia mínima del SL: spread + margen de seguridad
            min_sl_distance = max(
                spread_price * 3,
                point * 10,
                fvg_size * 1.5
            )
            
            # ⚡ ORDEN A MERCADO: Usar precio actual del mercado (bid/ask)
            if direction == 'BULLISH':
                entry_price = float(tick.ask)
                self.logger.info(f"[{symbol}] 💹 Entrada a mercado (BUY): Precio ASK actual = {entry_price:.5f}")
                
                calculated_sl = fvg_bottom - fvg_size - safety_margin
                min_sl_price = entry_price - min_sl_distance
                stop_loss = min(calculated_sl, min_sl_price)
                
                if stop_loss < calculated_sl:
                    self.logger.info(f"[{symbol}] ⚠️  SL ajustado por distancia mínima: {calculated_sl:.5f} → {stop_loss:.5f} (mínimo requerido: {min_sl_price:.5f})")
                
                take_profit = target_price
                self.logger.info(f"[{symbol}] 🛑 SL calculado: {stop_loss:.5f} (FVG Bottom: {fvg_bottom:.5f} - FVG Size: {fvg_size:.5f} - Safety Margin: {safety_margin:.5f} - Min Distance: {min_sl_distance:.5f})")
            else:
                entry_price = float(tick.bid)
                self.logger.info(f"[{symbol}] 💹 Entrada a mercado (SELL): Precio BID actual = {entry_price:.5f}")
                
                calculated_sl = fvg_top + fvg_size + safety_margin
                min_sl_price = entry_price + min_sl_distance
                stop_loss = max(calculated_sl, min_sl_price)
                
                if stop_loss > calculated_sl:
                    self.logger.info(f"[{symbol}] ⚠️  SL ajustado por distancia mínima: {calculated_sl:.5f} → {stop_loss:.5f} (mínimo requerido: {min_sl_price:.5f})")
                
                take_profit = target_price
                self.logger.info(f"[{symbol}] 🛑 SL calculado: {stop_loss:.5f} (FVG Top: {fvg_top:.5f} + FVG Size: {fvg_size:.5f} + Safety Margin: {safety_margin:.5f} + Min Distance: {min_sl_distance:.5f})")
            
            # Verificar y ajustar Risk/Reward
            risk = abs(entry_price - stop_loss)
            
            if risk == 0:
                return None
            
            initial_reward = abs(take_profit - entry_price)
            initial_rr = initial_reward / risk
            
            # Para CRT: Permitir RR mayor que 1:2 si el TP lógico lo requiere
            # Solo ajustar si el RR es menor que el mínimo
            if initial_rr < self.min_rr:
                # El RR es menor que el mínimo, ajustar TP para cumplir mínimo
                min_reward = risk * self.min_rr
                if direction == 'BULLISH':
                    take_profit = entry_price + min_reward
                else:
                    take_profit = entry_price - min_reward
                
                reward = min_reward
                rr = self.min_rr
                
                self.logger.info(
                    f"[{symbol}] ⚠️  RR inicial ({initial_rr:.2f}) menor que mínimo ({self.min_rr:.2f}) | "
                    f"TP ajustado: {crt_revision.get('target_price'):.5f} → {take_profit:.5f} para cumplir RR mínimo"
                )
            else:
                # Mantener TP lógico del CRT (puede ser mayor que 1:2)
                reward = initial_reward
                rr = initial_rr
                self.logger.info(
                    f"[{symbol}] ✅ RR inicial ({initial_rr:.2f}) >= mínimo ({self.min_rr:.2f}) | "
                    f"Manteniendo TP lógico del CRT: {take_profit:.5f} (RR: {rr:.2f}:1)"
                )
            
            self.logger.info(f"[{symbol}] 📈 Calculando RR: Risk={risk:.5f}, Reward={reward:.5f}, RR={rr:.2f} (mínimo requerido: {self.min_rr}, sin máximo - permite RR mayor si TP lógico lo requiere)")
            
            if rr < self.min_rr:
                self.logger.info(f"[{symbol}] ⏸️  Esperando: RR insuficiente ({rr:.2f} < {self.min_rr}). Intentando optimizar SL...")
                adjusted_sl = self._optimize_sl(entry_price, take_profit, direction, fvg_top, fvg_bottom)
                if adjusted_sl:
                    new_risk = abs(entry_price - adjusted_sl)
                    new_rr = reward / new_risk
                    if new_rr >= self.min_rr:
                        stop_loss = adjusted_sl
                        rr = new_rr
                        risk = new_risk
                        self.logger.info(f"[{symbol}] ✅ SL optimizado: Nuevo RR={rr:.2f}")
                    else:
                        self.logger.info(f"[{symbol}] ⏸️  Esperando: SL optimizado no alcanza RR mínimo (RR={new_rr:.2f}, requiere: >= {self.min_rr})")
                        return None
                else:
                    self.logger.info(f"[{symbol}] ⏸️  Esperando: No se pudo optimizar SL para alcanzar RR mínimo")
                    return None
            else:
                self.logger.info(f"[{symbol}] ✅ RR válido: {rr:.2f} (>= mínimo {self.min_rr}) - Etapa 3/4 COMPLETA")
            
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
        """
        try:
            reward = abs(take_profit - entry_price)
            required_risk = reward / self.min_rr
            fvg_size = fvg_top - fvg_bottom
            safety_margin = fvg_size * 0.5
            
            if direction == 'BULLISH':
                optimal_sl = entry_price - required_risk
                min_sl_required = fvg_bottom - fvg_size - safety_margin
                if optimal_sl <= min_sl_required:
                    return optimal_sl
                else:
                    if min_sl_required < entry_price:
                        return min_sl_required
            else:
                optimal_sl = entry_price + required_risk
                min_sl_required = fvg_top + fvg_size + safety_margin
                if optimal_sl >= min_sl_required:
                    return optimal_sl
                else:
                    if min_sl_required > entry_price:
                        return min_sl_required
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error al optimizar SL: {e}")
            return None
    
    def _execute_order(self, symbol: str, crt_revision: Dict, entry_signal: Dict) -> Optional[Dict]:
        """
        Ejecuta la orden de trading
        REUTILIZA LA MISMA LÓGICA DE TURTLE SOUP FVG
        
        Args:
            symbol: Símbolo
            crt_revision: Información del CRT de Continuación
            entry_signal: Señal de entrada
            
        Returns:
            Dict con resultado de la orden
        """
        try:
            # ⚠️ VALIDACIÓN CRÍTICA FINAL: Verificar que la VELA EN FORMACIÓN (junto con las 2 anteriores) formen el FVG esperado
            self.logger.info(f"[{symbol}] 🔍 Validación final estricta: Verificando vela EN FORMACIÓN + 2 anteriores forman FVG esperado...")
            
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
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, 3)
            
            if rates is None or len(rates) < 3:
                self.logger.error(f"[{symbol}] ❌ VALIDACIÓN FALLIDA: No se pudo obtener las 3 velas necesarias - Cancelando orden")
                return None
            
            # Ordenar por tiempo
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
            vela1 = candles_data[0]
            vela2 = candles_data[1]
            vela3 = candles_data[2]
            
            # VALIDACIÓN FINAL 0: Verificar que las 3 velas forman el FVG esperado
            fvg_formed = False
            calculated_fvg_bottom = None
            calculated_fvg_top = None
            calculated_fvg_type = None
            
            if vela1['low'] < vela3['high'] and vela3['low'] > vela1['high']:
                calculated_fvg_bottom = vela1['high']
                calculated_fvg_top = vela3['low']
                calculated_fvg_type = 'ALCISTA'
                fvg_formed = True
            elif vela1['high'] > vela3['low'] and vela3['high'] < vela1['low']:
                calculated_fvg_bottom = vela3['high']
                calculated_fvg_top = vela1['low']
                calculated_fvg_type = 'BAJISTA'
                fvg_formed = True
            
            if not fvg_formed:
                self.logger.error(f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Las 3 velas NO forman un FVG válido - Cancelando orden")
                return None
            
            # Verificar que el FVG formado es del tipo esperado según la dirección del objetivo
            # El FVG debe estar en la MISMA dirección del objetivo del CRT
            expected_fvg_type = None
            direction = entry_signal['direction']
            if direction == 'BULLISH':
                # Continuación Alcista: objetivo es HIGH de vela 5 AM → necesitamos FVG ALCISTA
                expected_fvg_type = 'ALCISTA'
            elif direction == 'BEARISH':
                # Continuación Bajista: objetivo es LOW de vela 5 AM → necesitamos FVG BAJISTA
                expected_fvg_type = 'BAJISTA'
            
            if calculated_fvg_type != expected_fvg_type:
                self.logger.error(
                    f"[{symbol}] ❌ VALIDACIÓN FALLIDA: FVG formado es {calculated_fvg_type} pero esperábamos {expected_fvg_type} - Cancelando orden"
                )
                return None
            
            fvg_bottom = calculated_fvg_bottom
            fvg_top = calculated_fvg_top
            
            # Obtener información de la vela EN FORMACIÓN
            candle_high = vela3.get('high')
            candle_low = vela3.get('low')
            candle_close = vela3.get('close')
            candle_time = vela3.get('time')
            
            # Obtener precio actual
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                self.logger.error(f"[{symbol}] ❌ VALIDACIÓN FALLIDA: No se pudo obtener precio actual - Cancelando orden")
                return None
            current_price = float(tick.bid)
            
            self.logger.info(f"[{symbol}] 📊 Validando vela EN FORMACIÓN: {candle_time.strftime('%Y-%m-%d %H:%M:%S')} | H={candle_high:.5f} L={candle_low:.5f} C={candle_close:.5f} | Precio actual: {current_price:.5f}")
            self.logger.info(f"[{symbol}] 📊 FVG calculado: {calculated_fvg_type} | Bottom: {fvg_bottom:.5f} | Top: {fvg_top:.5f}")
            
            # ⚠️ VALIDACIÓN CRÍTICA FINAL 1: La vela EN FORMACIÓN DEBE haber entrado al FVG
            candle_entered = False
            
            if calculated_fvg_type == 'BAJISTA':
                if fvg_bottom <= candle_high <= fvg_top:
                    candle_entered = True
                    self.logger.info(f"[{symbol}] ✅ VALIDACIÓN: HIGH ({candle_high:.5f}) está dentro del FVG BAJISTA ({fvg_bottom:.5f}-{fvg_top:.5f})")
                else:
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Para FVG BAJISTA, HIGH ({candle_high:.5f}) NO está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f}) | "
                        f"La vela NO entró al FVG - CANCELANDO ORDEN"
                    )
                    return None
            elif calculated_fvg_type == 'ALCISTA':
                if fvg_bottom <= candle_low <= fvg_top:
                    candle_entered = True
                    self.logger.info(f"[{symbol}] ✅ VALIDACIÓN: LOW ({candle_low:.5f}) está dentro del FVG ALCISTA ({fvg_bottom:.5f}-{fvg_top:.5f})")
                else:
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Para FVG ALCISTA, LOW ({candle_low:.5f}) NO está dentro del FVG ({fvg_bottom:.5f}-{fvg_top:.5f}) | "
                        f"La vela NO entró al FVG - CANCELANDO ORDEN"
                    )
                    return None
            
            if not candle_entered:
                self.logger.error(
                    f"[{symbol}] ❌ VALIDACIÓN FALLIDA: La vela EN FORMACIÓN NO entró al FVG {calculated_fvg_type} | "
                    f"CANCELANDO ORDEN - NO SE EJECUTARÁ"
                )
                return None
            
            # VALIDACIÓN FINAL 2: El precio actual DEBE haber salido del FVG en la dirección correcta
            price_outside = (current_price < fvg_bottom) or (current_price > fvg_top)
            if not price_outside:
                self.logger.error(
                    f"[{symbol}] ❌ VALIDACIÓN FALLIDA: El precio actual ({current_price:.5f}) NO salió del FVG | "
                    f"Precio está DENTRO del FVG ({fvg_bottom:.5f}-{fvg_top:.5f}) - Cancelando orden"
                )
                return None
            
            # VALIDACIÓN FINAL 3: La dirección de salida DEBE ser correcta
            if calculated_fvg_type == 'BAJISTA' and direction == 'BEARISH':
                if current_price >= fvg_bottom:
                    self.logger.error(
                        f"[{symbol}] ❌ VALIDACIÓN FALLIDA: Precio salió del FVG pero en dirección incorrecta | "
                        f"Precio actual={current_price:.5f} debe estar DEBAJO de {fvg_bottom:.5f} para {direction} - Cancelando orden"
                    )
                    return None
            elif calculated_fvg_type == 'ALCISTA' and direction == 'BULLISH':
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
            
            # Verificar posiciones abiertas JUSTO ANTES de ejecutar
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
            
            # Obtener precio actual del mercado en este momento exacto
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                self.logger.error(f"[{symbol}] ❌ No se pudo obtener precio actual del mercado - Cancelando orden")
                return None
            
            # Precio de entrada = precio actual del mercado
            if direction == 'BULLISH':
                entry_price = float(tick.ask)
                self.logger.info(f"[{symbol}] 💹 Precio de entrada a mercado (BUY): {entry_price:.5f} (ASK actual)")
            else:
                entry_price = float(tick.bid)
                self.logger.info(f"[{symbol}] 💹 Precio de entrada a mercado (SELL): {entry_price:.5f} (BID actual)")
            
            # Recalcular RIESGO con el precio real de entrada
            risk = abs(entry_price - stop_loss)
            if risk <= 0:
                self.logger.error(f"[{symbol}] ❌ Risk calculado 0 o negativo después de ajustar entry_price - Cancelando orden")
                return None
            
            # ⚠️ AJUSTAR RR: Mínimo 1:2, pero mantener TP lógico si da RR mayor
            # El TP viene del CRT (extremo opuesto de vela 1 AM para Revisión)
            # Si el TP lógico da RR >= 1:2, mantenerlo
            # Si el TP lógico da RR < 1:2, ajustar para cumplir mínimo
            original_tp = take_profit
            
            # Calcular RR con el TP lógico del CRT
            if direction == 'BULLISH':
                reward_logical = take_profit - entry_price
            else:
                reward_logical = entry_price - take_profit
            
            rr_logical = reward_logical / risk if risk > 0 else 0
            
            # Si el RR lógico es menor que el mínimo, ajustar TP para cumplir mínimo
            if rr_logical < self.min_rr:
                # Ajustar TP para cumplir RR mínimo
                min_reward = risk * self.min_rr
                if direction == 'BULLISH':
                    take_profit = entry_price + min_reward
                else:
                    take_profit = entry_price - min_reward
                reward_actual = min_reward
                rr = self.min_rr
                self.logger.info(
                    f"[{symbol}] ⚠️  RR lógico ({rr_logical:.2f}:1) menor que mínimo ({self.min_rr}:1) | "
                    f"TP ajustado: {original_tp:.5f} → {take_profit:.5f} para cumplir RR mínimo"
                )
            else:
                # Mantener TP lógico (puede ser mayor que 1:2)
                reward_actual = reward_logical
                rr = rr_logical
                self.logger.info(
                    f"[{symbol}] ✅ RR lógico ({rr_logical:.2f}:1) >= mínimo ({self.min_rr}:1) | "
                    f"Manteniendo TP lógico: {take_profit:.5f} (RR: {rr:.2f}:1)"
                )
            
            self.logger.info(
                f"[{symbol}] 📈 RR final: {rr:.2f}:1 (mínimo requerido: {self.min_rr}:1) | "
                f"Entry={entry_price:.5f}, SL={stop_loss:.5f} (Risk: {risk:.5f}), "
                f"TP={take_profit:.5f} (Reward: {reward_actual:.5f})"
            )
            
            # Crear diccionario FVG con la información calculada y validada
            fvg = {
                'fvg_type': calculated_fvg_type,
                'fvg_bottom': fvg_bottom,
                'fvg_top': fvg_top,
                'status': 'VALIDADO',
                'entered_fvg': True,
                'exited_fvg': True,
                'exit_direction': 'BAJISTA' if (calculated_fvg_type == 'BAJISTA' and direction == 'BEARISH') else 'ALCISTA' if (calculated_fvg_type == 'ALCISTA' and direction == 'BULLISH') else None
            }
            
            # Calcular volumen basado en el riesgo porcentual
            volume = self._calculate_volume_by_risk(symbol, entry_price, stop_loss)
            if volume is None or volume <= 0:
                self.logger.error(f"[{symbol}] ❌ No se pudo calcular el volumen por riesgo")
                return None
            
            # Determinar tipo de CRT de forma clara para logs
            crt_type_name = None
            if crt_revision.get('direction') == 'BULLISH':
                crt_type_name = "REVISIÓN"
            elif crt_revision.get('direction') == 'BEARISH':
                crt_type_name = "REVISIÓN"
            
            # Determinar objetivo según el tipo de CRT
            # El objetivo se define desde la vela de 5 AM, pero esperamos alcanzarlo durante la vela de 9 AM
            target_extreme = None
            if crt_revision.get('direction') == 'BULLISH':
                target_extreme = "HIGH de vela 5 AM"
            elif crt_revision.get('direction') == 'BEARISH':
                target_extreme = "LOW de vela 5 AM"
            
            # Log estructurado de la orden
            self.logger.info(f"[{symbol}] {'='*70}")
            self.logger.info(f"[{symbol}] 💹 EJECUTANDO ORDEN CRT DE CONTINUACIÓN")
            self.logger.info(f"[{symbol}] {'='*70}")
            self.logger.info(f"[{symbol}] 📊 TIPO DE CRT: {crt_type_name}")
            self.logger.info(f"[{symbol}] 📊 Dirección: {direction} ({'COMPRA' if direction == 'BULLISH' else 'VENTA'})")
            self.logger.info(f"[{symbol}] 💰 Precio de Entrada: {entry_price:.5f}")
            self.logger.info(f"[{symbol}] 🛑 Stop Loss: {stop_loss:.5f} (Risk: {entry_signal.get('risk', 0):.5f})")
            self.logger.info(f"[{symbol}] 🎯 Take Profit: {take_profit:.5f} (Reward: {entry_signal.get('reward', 0):.5f})")
            self.logger.info(f"[{symbol}] 📈 Risk/Reward: {rr:.2f}:1 (mínimo requerido: {self.min_rr}:1)")
            self.logger.info(f"[{symbol}] 📦 Volumen: {volume:.2f} lotes (calculado por {self.risk_per_trade_percent}% de riesgo)")
            self.logger.info(f"[{symbol}] {'-'*70}")
            self.logger.info(f"[{symbol}] 📋 Contexto de la Señal CRT:")
            self.logger.info(f"[{symbol}]    • Tipo de CRT: {crt_type_name}")
            self.logger.info(f"[{symbol}]    • Barrido: Vela 5 AM barrió {crt_revision.get('swept_extreme', 'N/A').upper()} de vela 1 AM")
            sweep_price = crt_revision.get('sweep_price')
            sweep_price_str = f"{sweep_price:.5f}" if sweep_price is not None else 'N/A'
            self.logger.info(f"[{symbol}]    • Precio barrido: {sweep_price_str}")
            self.logger.info(f"[{symbol}]    • Cierre: Cuerpo de vela 5 AM cerró DENTRO del rango de vela 1 AM")
            self.logger.info(f"[{symbol}] {'-'*70}")
            self.logger.info(f"[{symbol}] 🎯 OBJETIVO SEGÚN CRT DETECTADO:")
            target_price_log = crt_revision.get('target_price')
            target_price_str = f"{target_price_log:.5f}" if target_price_log is not None else 'N/A'
            self.logger.info(f"[{symbol}]    • Objetivo (TP) definido desde: {target_extreme}")
            self.logger.info(f"[{symbol}]    • Precio objetivo: {target_price_str}")
            self.logger.info(f"[{symbol}]    • Vela donde esperamos alcanzar: Vela 9 AM NY")
            self.logger.info(f"[{symbol}]    • TP original del CRT: {target_price_str}")
            if take_profit != target_price_log:
                self.logger.info(f"[{symbol}]    • TP ajustado por RR: {take_profit:.5f} (ajustado desde {target_price_str})")
            self.logger.info(f"[{symbol}] {'-'*70}")
            if fvg:
                self.logger.info(f"[{symbol}] 📋 Entrada FVG ({self.entry_timeframe}):")
                self.logger.info(f"[{symbol}]    • Tipo FVG: {fvg.get('fvg_type', 'N/A')}")
                self.logger.info(f"[{symbol}]    • Rango FVG: {fvg.get('fvg_bottom', 0):.5f} - {fvg.get('fvg_top', 0):.5f}")
                self.logger.info(f"[{symbol}]    • Estado: {fvg.get('status', 'N/A')} | Entró: {fvg.get('entered_fvg', False)} | Salió: {fvg.get('exited_fvg', False)}")
            self.logger.info(f"[{symbol}] {'='*70}")
            
            # Ejecutar orden según dirección
            if direction == 'BULLISH':
                result = self.executor.buy(
                    symbol=symbol,
                    volume=volume,
                    price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    comment=f"CRT Revisión H4 + FVG {self.entry_timeframe}"
                )
            else:
                result = self.executor.sell(
                    symbol=symbol,
                    volume=volume,
                    price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    comment=f"CRT Revisión H4 + FVG {self.entry_timeframe}"
                )
            
            if result['success']:
                self.trades_today += 1
                
                # Determinar tipo de CRT para logs finales
                crt_type_name = None
                if crt_revision.get('direction') == 'BULLISH':
                    crt_type_name = "CONTINUACIÓN ALCISTA"
                elif crt_revision.get('direction') == 'BEARISH':
                    crt_type_name = "CONTINUACIÓN BAJISTA"
                
                target_extreme = None
                if crt_revision.get('direction') == 'BULLISH':
                    target_extreme = "HIGH de vela 5 AM"
                elif crt_revision.get('direction') == 'BEARISH':
                    target_extreme = "LOW de vela 5 AM"
                
                self.logger.info(f"[{symbol}] {'='*70}")
                self.logger.info(f"[{symbol}] ✅ ORDEN EJECUTADA EXITOSAMENTE")
                self.logger.info(f"[{symbol}] {'='*70}")
                self.logger.info(f"[{symbol}] 📊 TIPO DE CRT: {crt_type_name}")
                self.logger.info(f"[{symbol}] 🎫 Ticket: {result['order_ticket']}")
                self.logger.info(f"[{symbol}] 📊 Símbolo: {symbol}")
                self.logger.info(f"[{symbol}] 💰 Precio: {entry_price:.5f}")
                self.logger.info(f"[{symbol}] 📦 Volumen: {volume:.2f} lotes")
                self.logger.info(f"[{symbol}] 🛑 Stop Loss: {stop_loss:.5f}")
                self.logger.info(f"[{symbol}] 🎯 Take Profit: {take_profit:.5f}")
                self.logger.info(f"[{symbol}] 📈 Risk/Reward: {rr:.2f}:1")
                self.logger.info(f"[{symbol}] {'-'*70}")
                self.logger.info(f"[{symbol}] 🎯 OBJETIVO SEGÚN CRT DETECTADO:")
                target_price_log = crt_revision.get('target_price')
                target_price_str = f"{target_price_log:.5f}" if target_price_log is not None else 'N/A'
                self.logger.info(f"[{symbol}]    • Objetivo (TP) definido desde: {target_extreme}")
                self.logger.info(f"[{symbol}]    • Precio objetivo original: {target_price_str}")
                self.logger.info(f"[{symbol}]    • Vela donde esperamos alcanzar: Vela 9 AM NY")
                if take_profit != target_price_log:
                    self.logger.info(f"[{symbol}]    • Precio objetivo ajustado: {take_profit:.5f} (ajustado por RR)")
                self.logger.info(f"[{symbol}] 📊 Trades hoy: {self.trades_today}/{self.max_trades_per_day}")
                self.logger.info(f"[{symbol}] {'='*70}")
                
                # Guardar orden en base de datos
                extra_data = {
                    'crt_revision': crt_revision,
                    'entry_signal': entry_signal,
                    'trades_today': self.trades_today,
                    'max_trades_per_day': self.max_trades_per_day
                }
                
                self.save_order_to_db(
                    ticket=result['order_ticket'],
                    symbol=symbol,
                    order_type=direction,
                    entry_price=entry_price,
                    volume=volume,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    rr=rr,
                    comment=f"CRT Revisión H4 + FVG {self.entry_timeframe}",
                    extra_data=extra_data
                )
                
                return {
                    'action': f'{direction}_EXECUTED',
                    'ticket': result['order_ticket'],
                    'crt_revision': crt_revision,
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
