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
from Base.crt_revision_detector import detect_crt_revision
from Base.crt_continuation_detector import detect_crt_continuation
from Base.crt_extreme_detector import detect_crt_extreme
from Base.news_checker import can_trade_now
from Base.order_executor import OrderExecutor
from Base.fvg_detector import detect_fvg


class CRTStrategy(BaseStrategy):
    """
    Estrategia CRT (Candle Range Theory) - Detecta los 3 tipos de CRT en H4
    
    Los 3 tipos de CRT que detecta:
    1. CRT de REVISIÓN: Vela 5 AM barre un extremo de vela 1 AM, cuerpo cierra DENTRO del rango
    2. CRT de CONTINUACIÓN: Vela 5 AM barre un extremo de vela 1 AM, close cierra FUERA del rango
    3. CRT de EXTREMO: Vela 5 AM barre AMBOS extremos (HIGH y LOW) de vela 1 AM
    
    Lógica:
    1. Verifica noticias de alto impacto
    2. Detecta los 3 tipos de CRT en H4 (velas 1 AM, 5 AM, 9 AM)
    3. Opcionalmente busca confirmación en temporalidad baja (M15 o M5) con velas envolventes
    4. Ejecuta orden con RR mínimo 1:2
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
        # Usar entry_timeframe de la configuración (igual que Turtle Soup)
        # Si no existe, usar crt_entry_timeframe como fallback para compatibilidad
        self.entry_timeframe = strategy_config.get('entry_timeframe') or strategy_config.get('crt_entry_timeframe', 'M15')  # M1, M5, M15, etc.
        self.min_rr = strategy_config.get('min_rr', 2.0)  # Risk/Reward mínimo
        self.flexible_rr = strategy_config.get('crt_flexible_rr', True)  # Permitir ajuste de TP si RR está cerca
        self.rr_tolerance = strategy_config.get('crt_rr_tolerance', 0.2)  # Tolerancia para ajustar TP (20% por defecto)
        self.use_vayas = strategy_config.get('crt_use_vayas', False)  # Usar patrón Vayas
        self.use_fvg_entry = strategy_config.get('crt_use_fvg_entry', True)  # Usar FVG para entrada (similar a Turtle Soup)
        self.lookback = strategy_config.get('crt_lookback', 5)  # Velas a revisar
        
        # Estado de monitoreo intensivo de FVG (similar a Turtle Soup)
        self.monitoring_fvg = False  # Indica si estamos monitoreando un FVG en tiempo real
        self.monitoring_fvg_data = None  # Datos del FVG que estamos monitoreando (crt_sweep, fvg_info)
        
        # Configuración de gestión de riesgo
        risk_config = config.get('risk_management', {})
        self.risk_per_trade_percent = risk_config.get('risk_per_trade_percent', 1.0)
        self.max_trades_per_day = risk_config.get('max_trades_per_day', 2)
        self.max_position_size = risk_config.get('max_position_size', 0.1)
        
        # Contador de trades por día
        self.trades_today = 0
        self.last_trade_date = None
        
        # Flag para marcar si el día está cerrado por falta de CRT específico
        self.day_closed_no_crt = False
        self.day_closed_no_crt_date = None
        
        self.logger.info(f"CRTStrategy inicializada - High TF: {self.high_timeframe}, Entry TF: {self.entry_timeframe}, RR: {self.min_rr}")
        self.logger.info(f"Riesgo por trade: {self.risk_per_trade_percent}% | Máximo trades/día: {self.max_trades_per_day}")
        self.logger.info(f"Vayas: {'Habilitado' if self.use_vayas else 'Deshabilitado'} | FVG Entry: {'Habilitado' if self.use_fvg_entry else 'Deshabilitado'}")
        self.logger.info(f"RR Flexible: {'Habilitado' if self.flexible_rr else 'Deshabilitado'} (tolerancia: {self.rr_tolerance*100:.0f}%)")
        self.logger.info(f"⚠️  IMPORTANTE: Solo operará si se detecta CRT específico (Revisión/Continuación/Extremo) - No usará detector genérico")
    
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
            # ⚠️ VERIFICACIÓN TEMPRANA: Si el día está cerrado por falta de CRT, detener análisis
            if self._is_day_closed_no_crt():
                if not hasattr(self, '_last_no_crt_log') or (time.time() - self._last_no_crt_log) >= 300:
                    self.logger.info(
                        f"[{symbol}] ⏸️  Día operativo cerrado - No se detectó CRT específico (Revisión/Continuación/Extremo) | "
                        f"Esperando al próximo día operativo"
                    )
                    self._last_no_crt_log = time.time()
                return None
            
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
            
            # 2. Detectar los 3 tipos de CRT en H4 (velas 1 AM, 5 AM, 9 AM)
            self.logger.info(f"[{symbol}] 🔍 Etapa 2/5: Buscando CRT en H4 (velas 1 AM, 5 AM, 9 AM)...")
            
            # Si estamos monitoreando FVG, verificar que el CRT aún existe
            if self.monitoring_fvg and self.monitoring_fvg_data:
                # Verificar que el CRT aún existe antes de continuar
                crt_sweep = self.monitoring_fvg_data.get('crt_sweep')
                if crt_sweep:
                    crt_type = crt_sweep.get('crt_type')
                    # Re-detectar el CRT para verificar que aún existe
                    current_crt = None
                    if crt_type == 'EXTREMO':
                        current_crt = detect_crt_extreme(symbol)
                    elif crt_type == 'CONTINUACIÓN':
                        current_crt = detect_crt_continuation(symbol)
                    elif crt_type == 'REVISIÓN':
                        current_crt = detect_crt_revision(symbol)
                    
                    if current_crt and current_crt.get('detected'):
                        # CRT aún existe, continuar con monitoreo
                        sweep = current_crt
                        sweep['crt_type'] = crt_type
                    else:
                        # CRT desapareció, cancelar monitoreo
                        self.logger.info(f"[{symbol}] ⏸️  CRT {crt_type} desapareció - Cancelando monitoreo intensivo")
                        self.monitoring_fvg = False
                        self.monitoring_fvg_data = None
                        return None
                else:
                    # No hay CRT en monitoreo, cancelar
                    self.monitoring_fvg = False
                    self.monitoring_fvg_data = None
                    return None
            else:
                # No estamos monitoreando, detectar CRT normalmente
                # Prioridad: 1. Extremo, 2. Continuación, 3. Revisión
                # Primero verificar CRT de Extremo (más específico)
                self.logger.debug(f"[{symbol}] 🔍 Verificando CRT de EXTREMO...")
                crt_extreme = detect_crt_extreme(symbol)
                if crt_extreme and crt_extreme.get('detected'):
                    sweep = crt_extreme
                    sweep['crt_type'] = 'EXTREMO'
                    self.logger.info(
                        f"[{symbol}] ✅ Etapa 2/5 COMPLETA: CRT de EXTREMO detectado | "
                        f"Vela 5 AM barrió AMBOS extremos de vela 1 AM | "
                        f"Dirección: {sweep.get('direction')} | TP: {sweep.get('target_price'):.5f}"
                    )
                else:
                    if crt_extreme is None:
                        self.logger.debug(f"[{symbol}] ⏸️  CRT de EXTREMO: No detectado (retornó None)")
                    else:
                        self.logger.debug(f"[{symbol}] ⏸️  CRT de EXTREMO: No detectado (detected=False)")
                    
                    # Verificar CRT de Continuación
                    self.logger.debug(f"[{symbol}] 🔍 Verificando CRT de CONTINUACIÓN...")
                    crt_continuation = detect_crt_continuation(symbol)
                    if crt_continuation and crt_continuation.get('detected'):
                        sweep = crt_continuation
                        sweep['crt_type'] = 'CONTINUACIÓN'
                        self.logger.info(
                            f"[{symbol}] ✅ Etapa 2/5 COMPLETA: CRT de CONTINUACIÓN detectado | "
                            f"Vela 5 AM barrió extremo y cerró FUERA del rango | "
                            f"Dirección: {sweep.get('direction')} | TP: {sweep.get('target_price'):.5f}"
                        )
                    else:
                        if crt_continuation is None:
                            self.logger.debug(f"[{symbol}] ⏸️  CRT de CONTINUACIÓN: No detectado (retornó None)")
                        else:
                            self.logger.debug(f"[{symbol}] ⏸️  CRT de CONTINUACIÓN: No detectado (detected=False)")
                        
                        # Verificar CRT de Revisión
                        self.logger.debug(f"[{symbol}] 🔍 Verificando CRT de REVISIÓN...")
                        crt_revision = detect_crt_revision(symbol)
                        if crt_revision and crt_revision.get('detected'):
                            sweep = crt_revision
                            sweep['crt_type'] = 'REVISIÓN'
                            self.logger.info(
                                f"[{symbol}] ✅ Etapa 2/5 COMPLETA: CRT de REVISIÓN detectado | "
                                f"Vela 5 AM barrió extremo y cuerpo cerró DENTRO del rango | "
                                f"Dirección: {sweep.get('direction')} | TP: {sweep.get('target_price'):.5f}"
                            )
                        else:
                            if crt_revision is None:
                                self.logger.debug(f"[{symbol}] ⏸️  CRT de REVISIÓN: No detectado (retornó None)")
                            else:
                                self.logger.debug(f"[{symbol}] ⏸️  CRT de REVISIÓN: No detectado (detected=False)")
                            
                            # NO se detectó ningún CRT específico (Extremo, Continuación, Revisión)
                            # Cerrar el día operativo y esperar al próximo día
                            self.logger.warning(f"[{symbol}] {'='*70}")
                            self.logger.warning(f"[{symbol}] 🚫 NO SE DETECTÓ NINGÚN CRT ESPECÍFICO (Revisión/Continuación/Extremo)")
                            self.logger.warning(f"[{symbol}] {'='*70}")
                            self.logger.warning(f"[{symbol}] ⏸️  DÍA OPERATIVO CERRADO - No se realizarán más operaciones hasta el próximo día operativo")
                            self.logger.warning(f"[{symbol}] 📅 Esperando al próximo día operativo para buscar nuevos CRT")
                            self.logger.warning(f"[{symbol}] {'='*70}")
                            
                            # Si estaba monitoreando, cancelar monitoreo
                            if self.monitoring_fvg:
                                self.logger.info(f"[{symbol}] ⏸️  Cancelando monitoreo intensivo - No hay CRT")
                                self.monitoring_fvg = False
                                self.monitoring_fvg_data = None
                            
                            # Marcar que el día debe cerrarse (no operar más hoy)
                            # Esto se hace guardando un registro especial en BD o usando un flag
                            self._mark_day_closed_no_crt(symbol)
                            
                            return None
            
            # Extraer información del CRT detectado
            sweep_type = sweep.get('sweep_type', 'UNKNOWN')
            direction = sweep.get('direction')
            target_price = sweep.get('target_price')
            crt_type = sweep.get('crt_type', 'UNKNOWN')
            
            # ⚠️ VERIFICACIÓN CRÍTICA: Verificar si el precio del mercado YA ALCANZÓ el objetivo (TP) del CRT
            if self._check_crt_target_reached(symbol, target_price, direction):
                self.logger.warning(f"[{symbol}] {'='*70}")
                self.logger.warning(f"[{symbol}] 🎯 OBJETIVO (TP) DEL CRT YA FUE ALCANZADO POR EL PRECIO")
                self.logger.warning(f"[{symbol}] {'='*70}")
                self.logger.warning(f"[{symbol}] 📊 CRT: {crt_type} | TP: {target_price:.5f} | Dirección: {direction}")
                self.logger.warning(f"[{symbol}] ⏸️  El precio del mercado ya pasó por el objetivo del CRT")
                self.logger.warning(f"[{symbol}] ⏸️  DÍA OPERATIVO CERRADO - No se realizarán más operaciones hasta el próximo día operativo")
                self.logger.warning(f"[{symbol}] 📅 Esperando al próximo día operativo para buscar nuevos CRT")
                self.logger.warning(f"[{symbol}] {'='*70}")
                
                # Marcar el día como cerrado por TP alcanzado
                self._mark_day_closed_tp_reached(symbol, crt_type, target_price)
                return None
            
            # Obtener precio de barrido según el tipo de CRT
            if crt_type == 'EXTREMO':
                # En CRT de Extremo, ambos extremos fueron barridos
                # Usamos el extremo que corresponde a la dirección opuesta (donde está el SL)
                if direction == 'BULLISH':
                    sweep_price = sweep.get('swept_low', 0)  # SL por debajo del LOW barrido
                else:  # BEARISH
                    sweep_price = sweep.get('swept_high', 0)  # SL por encima del HIGH barrido
            elif crt_type in ['CONTINUACIÓN', 'REVISIÓN']:
                sweep_price = sweep.get('sweep_price', 0)
            else:
                sweep_price = sweep.get('sweep_price', 0)
            
            # 3. Opcional: Detectar patrón Vayas (agotamiento de tendencia)
            if self.use_vayas:
                self.logger.info(f"[{symbol}] 🔍 Etapa 3/5: Verificando patrón Vayas en {self.high_timeframe}...")
                vayas = detect_crt_vayas(symbol, self.high_timeframe)
                if vayas and vayas.get('detected'):
                    trend_exhaustion = vayas.get('trend_exhaustion')
                    self.logger.info(f"[{symbol}] ✅ Patrón Vayas detectado - Agotamiento de tendencia: {trend_exhaustion}")
                else:
                    self.logger.info(f"[{symbol}] ⏸️  Patrón Vayas no detectado (continuando con barrido)")
            
            # 4. Buscar entrada en FVG (similar a Turtle Soup)
            if self.use_fvg_entry:
                # Si estamos en modo monitoreo intensivo, evaluar condiciones del FVG
                if self.monitoring_fvg and self.monitoring_fvg_data:
                    return self._monitor_fvg_intensive(symbol)
                
                self.logger.info(f"[{symbol}] 🔍 Etapa 4/5: Buscando entrada en FVG ({self.entry_timeframe})...")
                entry_signal = self._find_fvg_entry(symbol, sweep)
                
                if entry_signal:
                    # 5. Ejecutar orden
                    # Cancelar monitoreo intermedio si estaba activo
                    if hasattr(self, '_waiting_for_fvg'):
                        self._waiting_for_fvg = False
                    self.logger.info(f"[{symbol}] 💹 Etapa 5/5: Ejecutando orden...")
                    return self._execute_order(symbol, sweep, entry_signal)
                else:
                    # Verificar si hay un FVG esperado para activar monitoreo intensivo
                    fvg = detect_fvg(symbol, self.entry_timeframe)
                    if fvg and self._is_expected_fvg(fvg, sweep):
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
                                'crt_sweep': sweep,
                                'fvg': fvg
                            }
                        else:
                            # Actualizar datos del FVG si ya está monitoreando
                            self.monitoring_fvg_data['fvg'] = fvg
                            self.monitoring_fvg_data['crt_sweep'] = sweep
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
                    
                    # Cuando hay CRT pero no hay FVG, activar monitoreo intermedio
                    if not self.monitoring_fvg:
                        # Activar monitoreo intermedio (cada 5-10 segundos) cuando hay CRT pero no FVG
                        if not hasattr(self, '_waiting_for_fvg') or not self._waiting_for_fvg:
                            self._waiting_for_fvg = True
                            self.logger.info(f"[{symbol}] ⏳ CRT detectado pero sin FVG - Activando monitoreo intermedio")
                            self.logger.info(f"[{symbol}]    • El bot analizará cada 10 segundos buscando FVG {self.entry_timeframe}")
                            self.logger.info(f"[{symbol}]    • CRT: {crt_type} | TP: {target_price:.5f} | Dirección: {direction}")
                            self.logger.info(f"[{symbol}]    • Esperando FVG {'BAJISTA' if direction == 'BEARISH' else 'ALCISTA'} en {self.entry_timeframe}")
                        
                        # Log periódico cada 30 segundos para indicar que sigue esperando
                        current_time = time.time()
                        if not hasattr(self, '_last_waiting_log') or (current_time - self._last_waiting_log) >= 30:
                            self.logger.info(f"[{symbol}] ⏸️  Etapa 4/5: Esperando FVG válida - CRT activo, buscando FVG en {self.entry_timeframe}...")
                            self._last_waiting_log = current_time
                    
                    return None
            else:
                # Si no se usa FVG, ejecutar orden directamente (comportamiento antiguo)
                self.logger.info(f"[{symbol}] 💹 Etapa 4/5: Ejecutando orden sin FVG...")
                return self._execute_order(symbol, sweep)
            
        except Exception as e:
            self.logger.error(f"Error en análisis CRT: {e}", exc_info=True)
            return None
    
    def needs_intensive_monitoring(self) -> bool:
        """
        Indica si la estrategia necesita monitoreo intensivo (cada segundo)
        
        Returns:
            True si necesita monitoreo intensivo, False si usa intervalo normal
        """
        return self.monitoring_fvg
    
    def _is_expected_fvg(self, fvg: Dict, crt_sweep: Dict) -> bool:
        """
        Verifica si un FVG es el esperado según el CRT
        
        Para CRT, el FVG debe estar en la MISMA dirección que la dirección del CRT:
        - CRT BULLISH → busca FVG ALCISTA
        - CRT BEARISH → busca FVG BAJISTA
        
        Args:
            fvg: Información del FVG
            crt_sweep: Información del CRT detectado
            
        Returns:
            True si el FVG es el esperado
        """
        try:
            direction = crt_sweep.get('direction')
            fvg_type = fvg.get('fvg_type')
            
            # Determinar qué tipo de FVG buscamos según la dirección del CRT
            expected_fvg_type = None
            if direction == 'BULLISH':
                expected_fvg_type = 'ALCISTA'  # CRT alcista → FVG alcista
            elif direction == 'BEARISH':
                expected_fvg_type = 'BAJISTA'  # CRT bajista → FVG bajista
            
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
            
            crt_sweep = self.monitoring_fvg_data.get('crt_sweep')
            if not crt_sweep:
                self.monitoring_fvg = False
                self.monitoring_fvg_data = None
                return None
            
            # Verificar que el CRT aún existe (re-detectar)
            # Para CRT, verificamos que el tipo específico aún esté presente
            crt_type = crt_sweep.get('crt_type')
            current_crt = None
            
            if crt_type == 'EXTREMO':
                current_crt = detect_crt_extreme(symbol)
            elif crt_type == 'CONTINUACIÓN':
                current_crt = detect_crt_continuation(symbol)
            elif crt_type == 'REVISIÓN':
                current_crt = detect_crt_revision(symbol)
            
            if not current_crt or not current_crt.get('detected'):
                self.logger.info(f"[{symbol}] ⏸️  CRT {crt_type} desapareció durante monitoreo - Cancelando")
                self.monitoring_fvg = False
                self.monitoring_fvg_data = None
                return None
            
            # Verificar que el FVG aún existe y es el esperado
            fvg = detect_fvg(symbol, self.entry_timeframe)
            if not fvg or not self._is_expected_fvg(fvg, crt_sweep):
                self.logger.info(f"[{symbol}] ⏸️  FVG esperado desapareció durante monitoreo - Cancelando")
                self.monitoring_fvg = False
                self.monitoring_fvg_data = None
                return None
            
            # Actualizar datos del FVG
            self.monitoring_fvg_data['fvg'] = fvg
            self.monitoring_fvg_data['crt_sweep'] = current_crt
            
            # Obtener precio actual para verificar estado
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                self.logger.error(f"[{symbol}] ❌ No se pudo obtener precio actual durante monitoreo")
                return None
            
            current_price = float(tick.bid)
            fvg_bottom = fvg.get('fvg_bottom')
            fvg_top = fvg.get('fvg_top')
            fvg_type = fvg.get('fvg_type')
            direction = crt_sweep.get('direction')
            
            # Verificar si el precio está dentro del FVG
            price_inside_fvg = (fvg_bottom <= current_price <= fvg_top) if fvg_bottom and fvg_top else False
            
            # Si el precio está dentro del FVG, esperar a que salga en la dirección esperada
            if price_inside_fvg:
                # Log cada 10 segundos para no saturar
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
            entry_signal = self._find_fvg_entry(symbol, current_crt)
            
            if entry_signal:
                # Condiciones cumplidas - ejecutar orden y cancelar monitoreo
                self.logger.info(f"[{symbol}] ✅ Condiciones cumplidas durante monitoreo intensivo - Precio salió del FVG en dirección esperada - Ejecutando orden")
                self.monitoring_fvg = False
                self.monitoring_fvg_data = None
                return self._execute_order(symbol, current_crt, entry_signal)
            
            # El precio salió del FVG pero no en la dirección esperada, o condiciones no cumplidas
            # Log cada 10 segundos para no saturar
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
            
            # Resetear flag de día cerrado por falta de CRT si es un nuevo día
            if self.day_closed_no_crt_date != today:
                if self.day_closed_no_crt:
                    self.logger.info(f"🔄 Nuevo día - Reseteando flag de día cerrado por falta de CRT")
                self.day_closed_no_crt = False
                self.day_closed_no_crt_date = None
    
    def _is_day_closed_no_crt(self) -> bool:
        """
        Verifica si el día está cerrado por falta de CRT específico
        
        Returns:
            True si el día está cerrado, False si puede continuar
        """
        today = date.today()
        
        # Si es un nuevo día, resetear el flag
        if self.day_closed_no_crt_date != today:
            self.day_closed_no_crt = False
            self.day_closed_no_crt_date = None
            return False
        
        return self.day_closed_no_crt
    
    def _check_crt_target_reached(self, symbol: str, target_price: float, direction: str) -> bool:
        """
        Verifica si el precio del mercado YA ALCANZÓ el objetivo (TP) del CRT
        
        Si el precio ya pasó por el TP del CRT (incluso sin haber ejecutado un trade),
        se cierra el día operativo porque el objetivo ya fue alcanzado.
        
        Args:
            symbol: Símbolo a verificar
            target_price: Precio objetivo (TP) del CRT
            direction: Dirección del CRT ('BULLISH' o 'BEARISH')
            
        Returns:
            True si el precio ya alcanzó el TP, False en caso contrario
        """
        try:
            # Obtener precio actual del mercado
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return False
            
            current_price = float(tick.bid)  # Usar bid como referencia
            
            # Verificar según la dirección del CRT
            if direction == 'BULLISH':
                # Para CRT alcista, el TP está arriba
                # Si el precio actual (bid) ya está ARRIBA del TP, el objetivo fue alcanzado
                if current_price >= target_price:
                    self.logger.info(
                        f"[{symbol}] 🎯 Precio actual ({current_price:.5f}) ya está ARRIBA del TP ({target_price:.5f}) - "
                        f"Objetivo del CRT ya fue alcanzado"
                    )
                    return True
            else:  # BEARISH
                # Para CRT bajista, el TP está abajo
                # Si el precio actual (bid) ya está DEBAJO del TP, el objetivo fue alcanzado
                if current_price <= target_price:
                    self.logger.info(
                        f"[{symbol}] 🎯 Precio actual ({current_price:.5f}) ya está DEBAJO del TP ({target_price:.5f}) - "
                        f"Objetivo del CRT ya fue alcanzado"
                    )
                    return True
            
            # También verificar el histórico de velas para ver si el precio pasó por el TP
            # Obtener velas H4 del día actual para verificar si el precio alcanzó el TP
            today = date.today()
            from datetime import time as dt_time
            start_time = datetime.combine(today, dt_time(0, 0, 0))
            end_time = datetime.combine(today, dt_time(23, 59, 59))
            
            start_timestamp = int(start_time.timestamp())
            end_timestamp = int(end_time.timestamp())
            
            # Obtener velas H4 desde el inicio del día
            rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H4, start_timestamp, end_timestamp)
            
            if rates is not None and len(rates) > 0:
                # Verificar si alguna vela del día alcanzó el TP
                for rate in rates:
                    high = float(rate['high'])
                    low = float(rate['low'])
                    
                    if direction == 'BULLISH':
                        # Para CRT alcista, verificar si alguna vela alcanzó el TP (HIGH >= TP)
                        if high >= target_price:
                            self.logger.info(
                                f"[{symbol}] 🎯 Vela H4 del día alcanzó el TP ({target_price:.5f}) - "
                                f"High de vela: {high:.5f} - Objetivo del CRT ya fue alcanzado"
                            )
                            return True
                    else:  # BEARISH
                        # Para CRT bajista, verificar si alguna vela alcanzó el TP (LOW <= TP)
                        if low <= target_price:
                            self.logger.info(
                                f"[{symbol}] 🎯 Vela H4 del día alcanzó el TP ({target_price:.5f}) - "
                                f"Low de vela: {low:.5f} - Objetivo del CRT ya fue alcanzado"
                            )
                            return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error al verificar si precio alcanzó TP de CRT: {e}", exc_info=True)
            return False
    
    def _mark_day_closed_tp_reached(self, symbol: str, crt_type: str, target_price: float):
        """
        Marca el día como cerrado porque el objetivo (TP) del CRT ya fue alcanzado
        
        Args:
            symbol: Símbolo que se estaba analizando
            crt_type: Tipo de CRT detectado
            target_price: Precio objetivo que fue alcanzado
        """
        today = date.today()
        
        # Guardar en BD si está habilitada
        db_manager = self._get_db_manager()
        if db_manager and db_manager.enabled:
            try:
                db_manager.save_log(
                    level='WARNING',
                    logger_name='CRTStrategy',
                    message=f'Día operativo cerrado - Objetivo (TP) de CRT ya fue alcanzado por el precio del mercado',
                    symbol=symbol,
                    strategy='crt_strategy',
                    extra_data={
                        'reason': 'CRT_TP_REACHED',
                        'date': today.isoformat(),
                        'crt_type': crt_type,
                        'target_price': target_price
                    }
                )
            except Exception as e:
                self.logger.debug(f"Error al guardar log de TP alcanzado en BD: {e}")
    
    def _mark_day_closed_no_crt(self, symbol: str):
        """
        Marca el día como cerrado por falta de CRT específico
        
        Args:
            symbol: Símbolo que se estaba analizando
        """
        today = date.today()
        self.day_closed_no_crt = True
        self.day_closed_no_crt_date = today
        
        # Guardar en BD si está habilitada (opcional, para persistencia)
        db_manager = self._get_db_manager()
        if db_manager and db_manager.enabled:
            try:
                # Guardar un log especial indicando que el día está cerrado
                db_manager.save_log(
                    level='WARNING',
                    logger_name='CRTStrategy',
                    message=f'Día operativo cerrado - No se detectó CRT específico (Revisión/Continuación/Extremo)',
                    symbol=symbol,
                    strategy='crt_strategy',
                    extra_data={
                        'reason': 'NO_CRT_DETECTED',
                        'date': today.isoformat(),
                        'crt_types_checked': ['EXTREMO', 'CONTINUACIÓN', 'REVISIÓN']
                    }
                )
            except Exception as e:
                self.logger.debug(f"Error al guardar log de día cerrado en BD: {e}")
    
    def _find_fvg_entry(self, symbol: str, crt_sweep: Dict) -> Optional[Dict]:
        """
        Busca entrada en FVG en la MISMA dirección del objetivo del CRT
        - CRT BULLISH → busca FVG ALCISTA (para ir hacia arriba)
        - CRT BEARISH → busca FVG BAJISTA (para ir hacia abajo)
        REUTILIZA LA MISMA LÓGICA DE TURTLE SOUP FVG
        
        Args:
            symbol: Símbolo
            crt_sweep: Información del CRT detectado
            
        Returns:
            Dict con señal de entrada o None
        """
        try:
            # Detectar FVG en la temporalidad de entrada
            fvg = detect_fvg(symbol, self.entry_timeframe)
            
            if not fvg:
                self.logger.info(f"[{symbol}] ⏸️  Esperando: No hay FVG detectado en {self.entry_timeframe}")
                return None
            
            direction = crt_sweep.get('direction')
            fvg_type = fvg.get('fvg_type')
            
            # Verificar si el FVG es el esperado según el CRT
            if not self._is_expected_fvg(fvg, crt_sweep):
                self.logger.info(f"[{symbol}] ⏸️  FVG detectado ({fvg_type}) no es el esperado según CRT (dirección: {direction})")
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
            tf = timeframe_map.get(self.entry_timeframe.upper(), mt5.TIMEFRAME_M15)
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
            
            # Verificar que el FVG formado es del tipo esperado según el CRT
            if calculated_fvg_type != fvg_type:
                self.logger.info(
                    f"[{symbol}] ⏸️  REGLA NO CUMPLIDA: FVG formado es {calculated_fvg_type} pero esperábamos {fvg_type} "
                    f"(según CRT dirección {direction})"
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
            
            self.logger.info(f"[{symbol}] ✅ Condiciones cumplidas - Listo para calcular entrada")
            
            # Obtener precio actual (bid para venta, ask para compra)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            
            # Calcular niveles
            target_price = crt_sweep.get('target_price')
            
            if fvg_top is None or fvg_bottom is None or target_price is None:
                return None
            
            # Calcular Stop Loss (debe cubrir TODO el espacio del FVG + margen adicional)
            # Reutilizar la misma lógica de Turtle Soup
            fvg_size = fvg_top - fvg_bottom
            
            # Obtener información del símbolo para calcular spread y distancia mínima
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return None
            
            spread_points = symbol_info.spread
            point = symbol_info.point
            spread_price = spread_points * point
            
            pips_to_points = 10 if symbol_info.digits == 5 else 1
            
            # Margen adicional estándar: 100% del tamaño del FVG
            safety_margin = fvg_size * 1.0
            
            # Distancia mínima según temporalidad
            fvg_size_pips = fvg_size * (10000 if symbol_info.digits == 5 else 100)
            entry_tf = self.entry_timeframe.upper()
            if entry_tf == 'M1':
                if fvg_size_pips < 3:
                    min_pips = 15
                elif fvg_size_pips < 5:
                    min_pips = 18
                else:
                    min_pips = 20
            else:
                if fvg_size_pips < 5:
                    min_pips = 40
                elif fvg_size_pips < 10:
                    min_pips = 35
                else:
                    min_pips = 30
            
            min_sl_distance_pips = min_pips * pips_to_points * point
            
            min_sl_distance = max(
                spread_price * 5,
                min_sl_distance_pips,
                fvg_size * 2.5
            )
            
            # ⚡ ORDEN A MERCADO: Usar precio actual del mercado
            if direction == 'BULLISH':
                entry_price = float(tick.ask)
                calculated_sl = fvg_bottom - fvg_size - safety_margin
                min_sl_price = entry_price - min_sl_distance
                stop_loss = min(calculated_sl, min_sl_price)
                take_profit = target_price
            else:
                entry_price = float(tick.bid)
                calculated_sl = fvg_top + fvg_size + safety_margin
                min_sl_price = entry_price + min_sl_distance
                stop_loss = max(calculated_sl, min_sl_price)
                take_profit = target_price
            
            # Verificar y ajustar Risk/Reward
            risk = abs(entry_price - stop_loss)
            if risk == 0:
                return None
            
            initial_reward = abs(take_profit - entry_price)
            initial_rr = initial_reward / risk
            
            max_rr = self.min_rr
            
            if initial_rr > max_rr:
                max_reward = risk * max_rr
                if direction == 'BULLISH':
                    take_profit = entry_price + max_reward
                else:
                    take_profit = entry_price - max_reward
                reward = max_reward
                rr = max_rr
            else:
                reward = initial_reward
                rr = initial_rr
            
            self.logger.info(f"[{symbol}] 📈 Calculando RR: Risk={risk:.5f}, Reward={reward:.5f}, RR={rr:.2f} (mínimo requerido: {self.min_rr}, máximo: {max_rr})")
            
            if rr < self.min_rr:
                if self.flexible_rr:
                    rr_deficit = self.min_rr - rr
                    rr_percent_deficit = rr_deficit / self.min_rr
                    
                    if rr_percent_deficit <= self.rr_tolerance:
                        required_reward = risk * self.min_rr
                        if direction == 'BULLISH':
                            new_tp = entry_price + required_reward
                            max_tp = target_price * 1.20
                            if new_tp <= max_tp:
                                take_profit = new_tp
                                reward = required_reward
                                rr = self.min_rr
                            else:
                                self.logger.info(f"[{symbol}] ⏸️  RR insuficiente - Ajuste requeriría TP muy lejano")
                                return None
                        else:
                            new_tp = entry_price - required_reward
                            min_tp = target_price * 0.80
                            if new_tp >= min_tp:
                                take_profit = new_tp
                                reward = required_reward
                                rr = self.min_rr
                            else:
                                self.logger.info(f"[{symbol}] ⏸️  RR insuficiente - Ajuste requeriría TP muy lejano")
                                return None
                    else:
                        self.logger.info(f"[{symbol}] ⏸️  RR insuficiente ({rr:.2f} < {self.min_rr}) - Déficit excede tolerancia")
                        return None
                else:
                    self.logger.info(f"[{symbol}] ⏸️  RR insuficiente ({rr:.2f} < {self.min_rr})")
                    return None
            
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
    
    def _execute_order(self, symbol: str, sweep: Dict, entry_signal: Optional[Dict] = None) -> Optional[Dict]:
        """
        Ejecuta la orden de trading basada en el barrido CRT
        
        Args:
            symbol: Símbolo
            sweep: Información del barrido detectado
            entry_signal: Señal de entrada del FVG (opcional). Si se proporciona, usa estos valores directamente.
            
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
            
            # Si hay entry_signal del FVG, usar esos valores directamente
            if entry_signal:
                entry_price = entry_signal.get('entry_price')
                stop_loss = entry_signal.get('stop_loss')
                take_profit = entry_signal.get('take_profit')
                risk = entry_signal.get('risk')
                reward = entry_signal.get('reward')
                rr = entry_signal.get('rr')
                
                self.logger.info(f"[{symbol}] 💹 Usando valores de entrada desde FVG:")
                self.logger.info(f"[{symbol}]    Entry: {entry_price:.5f} | SL: {stop_loss:.5f} | TP: {take_profit:.5f}")
                self.logger.info(f"[{symbol}]    Risk: {risk:.5f} | Reward: {reward:.5f} | RR: {rr:.2f}")
            else:
                # Comportamiento antiguo: calcular desde el sweep (sin FVG)
                sweep_price = sweep.get('sweep_price')
                swept_candle = sweep.get('swept_candle', {})
                
                # Obtener precio actual del mercado
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    self.logger.error(f"[{symbol}] ❌ No se pudo obtener precio actual")
                    return None
                
                # Calcular niveles de entrada, SL y TP
                # Obtener información del símbolo para calcular margen adecuado
                symbol_info = mt5.symbol_info(symbol)
                if symbol_info is None:
                    self.logger.error(f"[{symbol}] ❌ No se pudo obtener información del símbolo")
                    return None
                
                point = symbol_info.point
                spread_points = symbol_info.spread
                spread_price = spread_points * point
                stop_level = symbol_info.trade_stops_level  # Puntos mínimos requeridos por broker
                min_stop_distance = stop_level * point if stop_level > 0 else spread_price * 3
                
                # Calcular margen de seguridad basado en el rango de la vela 1 AM
                candle_1am = sweep.get('candle_1am', {})
                if candle_1am:
                    candle_1am_high = candle_1am.get('high', 0)
                    candle_1am_low = candle_1am.get('low', 0)
                    candle_1am_range = candle_1am_high - candle_1am_low
                    # Usar 20% del rango de la vela 1 AM como margen de seguridad (mínimo 10 pips)
                    safety_margin = max(candle_1am_range * 0.20, point * 10)
                else:
                    # Fallback: usar 15 pips como margen mínimo
                    safety_margin = point * 15
                
                if direction == 'BULLISH':
                    entry_price = float(tick.ask)
                    # SL: Por debajo del HIGH barrido (sweep_price = HIGH de vela 1 AM)
                    # Usar el mayor entre: margen de seguridad, distancia mínima del broker, o 10 pips
                    sl_margin = max(safety_margin, min_stop_distance, point * 10)
                    stop_loss = sweep_price - sl_margin
                    
                    # Asegurar que el SL esté por debajo del entry price
                    if stop_loss >= entry_price:
                        stop_loss = entry_price - min_stop_distance
                        self.logger.warning(f"[{symbol}] ⚠️  SL ajustado: {stop_loss:.5f} (debe estar por debajo del entry {entry_price:.5f})")
                    
                    take_profit = target_price
                else:  # BEARISH
                    entry_price = float(tick.bid)
                    # SL: Por encima del LOW barrido (sweep_price = LOW de vela 1 AM)
                    # Usar el mayor entre: margen de seguridad, distancia mínima del broker, o 10 pips
                    sl_margin = max(safety_margin, min_stop_distance, point * 10)
                    stop_loss = sweep_price + sl_margin
                    
                    # Asegurar que el SL esté por encima del entry price
                    if stop_loss <= entry_price:
                        stop_loss = entry_price + min_stop_distance
                        self.logger.warning(f"[{symbol}] ⚠️  SL ajustado: {stop_loss:.5f} (debe estar por encima del entry {entry_price:.5f})")
                    
                    take_profit = target_price
                
                # Verificar y ajustar Risk/Reward
                risk = abs(entry_price - stop_loss)
                if risk == 0:
                    return None
                
                reward = abs(take_profit - entry_price)
                rr = reward / risk
                
                self.logger.info(f"[{symbol}] 📈 Calculando RR: Risk={risk:.5f}, Reward={reward:.5f}, RR={rr:.2f} (mínimo requerido: {self.min_rr})")
                
                # RR flexible: si está cerca del mínimo, ajustar TP para alcanzarlo
                if rr < self.min_rr:
                    if self.flexible_rr:
                        # Calcular qué tan cerca está del mínimo
                        rr_deficit = self.min_rr - rr
                        rr_percent_deficit = rr_deficit / self.min_rr
                        
                        # Si el déficit está dentro de la tolerancia, ajustar TP
                        if rr_percent_deficit <= self.rr_tolerance:
                            # Ajustar TP para alcanzar el RR mínimo
                            if direction == 'BULLISH':
                                # Aumentar TP para mejorar RR
                                required_reward = risk * self.min_rr
                                new_tp = entry_price + required_reward
                                # No exceder el TP original por más del 20%
                                max_tp = target_price * 1.20
                                if new_tp <= max_tp:
                                    take_profit = new_tp
                                    reward = required_reward
                                    rr = self.min_rr
                                    self.logger.info(
                                        f"[{symbol}] 🔧 RR ajustado: TP modificado de {target_price:.5f} a {take_profit:.5f} "
                                        f"para alcanzar RR mínimo {self.min_rr:.2f} (déficit: {rr_percent_deficit*100:.1f}% dentro de tolerancia)"
                                    )
                                else:
                                    self.logger.info(
                                        f"[{symbol}] ⏸️  RR insuficiente ({rr:.2f} < {self.min_rr}) - "
                                        f"Ajuste requeriría TP muy lejano ({new_tp:.5f} > {max_tp:.5f})"
                                    )
                                    return None
                            else:  # BEARISH
                                # Disminuir TP para mejorar RR
                                required_reward = risk * self.min_rr
                                new_tp = entry_price - required_reward
                                # No exceder el TP original por más del 20%
                                min_tp = target_price * 0.80
                                if new_tp >= min_tp:
                                    take_profit = new_tp
                                    reward = required_reward
                                    rr = self.min_rr
                                    self.logger.info(
                                        f"[{symbol}] 🔧 RR ajustado: TP modificado de {target_price:.5f} a {take_profit:.5f} "
                                        f"para alcanzar RR mínimo {self.min_rr:.2f} (déficit: {rr_percent_deficit*100:.1f}% dentro de tolerancia)"
                                    )
                                else:
                                    self.logger.info(
                                        f"[{symbol}] ⏸️  RR insuficiente ({rr:.2f} < {self.min_rr}) - "
                                        f"Ajuste requeriría TP muy lejano ({new_tp:.5f} < {min_tp:.5f})"
                                    )
                                    return None
                        else:
                            # Déficit demasiado grande, no ajustar
                            self.logger.info(
                                f"[{symbol}] ⏸️  RR insuficiente ({rr:.2f} < {self.min_rr}) - "
                                f"Déficit {rr_percent_deficit*100:.1f}% excede tolerancia {self.rr_tolerance*100:.0f}%"
                            )
                            return None
                    else:
                        # RR flexible deshabilitado
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
            self.logger.info(f"[{symbol}]    • Tipo CRT: {sweep.get('crt_type', 'N/A')}")
            self.logger.info(f"[{symbol}]    • Barrido: {sweep.get('sweep_type', 'N/A')} en H4")
            sweep_price = sweep.get('sweep_price', 0)
            if sweep_price:
                self.logger.info(f"[{symbol}]    • Precio barrido: {sweep_price:.5f}")
            self.logger.info(f"[{symbol}]    • Objetivo: {target_price:.5f}")
            if entry_signal and entry_signal.get('fvg'):
                fvg_info = entry_signal.get('fvg', {})
                self.logger.info(f"[{symbol}]    • FVG {self.entry_timeframe}: {fvg_info.get('fvg_type', 'N/A')} ({fvg_info.get('fvg_bottom', 0):.5f} - {fvg_info.get('fvg_top', 0):.5f})")
            if sweep.get('candle_1am'):
                self.logger.info(f"[{symbol}]    • Vela 1 AM: H={sweep['candle_1am'].get('high', 0):.5f}, L={sweep['candle_1am'].get('low', 0):.5f}")
            if sweep.get('candle_5am'):
                self.logger.info(f"[{symbol}]    • Vela 5 AM: H={sweep['candle_5am'].get('high', 0):.5f}, L={sweep['candle_5am'].get('low', 0):.5f}")
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
