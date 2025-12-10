"""
Estrategia Turtle Soup H4 + FVG
Combina detección de Turtle Soup en H4 con entradas basadas en FVG
"""

import logging
from typing import Optional, Dict
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
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
        self.volume = config.get('risk_management', {}).get('volume', 0.01)
        
        # Frecuencia de evaluación según timeframe
        if self.entry_timeframe == 'M1':
            self.evaluation_interval = 30  # 30 segundos
        else:
            self.evaluation_interval = 60  # 1 minuto
        
        # Estado de la estrategia
        self.turtle_soup_signal = None
        self.last_news_check = None
        self.last_evaluation = None
        
        self.logger.info(f"TurtleSoupFVGStrategy inicializada - Entry: {self.entry_timeframe}, RR: {self.min_rr}")
    
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
                self.logger.info(f"[{symbol}] ⏸️  Etapa 3/4: Esperando - No hay señal de entrada FVG válida aún")
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error en análisis: {e}", exc_info=True)
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
            
            # Verificar que el precio haya entrado y salido del FVG PRIMERO
            # Esto es lo más importante - si el precio entró y salió en la dirección correcta, proceder
            if not fvg.get('entered_fvg'):
                self.logger.info(f"[{symbol}] ⏸️  Esperando: El precio aún no ha entrado al FVG")
                return None
            
            if not fvg.get('exited_fvg'):
                self.logger.info(f"[{symbol}] ⏸️  Esperando: El precio entró al FVG pero aún no ha salido (Estado: {fvg.get('status')})")
                return None
            
            # Verificar dirección de salida - DEBE coincidir con la dirección del Turtle Soup
            # Normalizar exit_direction: ALCISTA -> BULLISH, BAJISTA -> BEARISH
            normalized_exit_direction = None
            if exit_direction == 'ALCISTA':
                normalized_exit_direction = 'BULLISH'
            elif exit_direction == 'BAJISTA':
                normalized_exit_direction = 'BEARISH'
            
            if normalized_exit_direction != direction:
                self.logger.info(f"[{symbol}] ⏸️  Esperando: El precio salió del FVG en dirección {exit_direction} ({normalized_exit_direction}), pero necesitamos {direction} (según Turtle Soup H4)")
                return None
            
            self.logger.info(f"[{symbol}] ✅ Precio entró y salió del FVG en la dirección correcta ({direction})")
            
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
            
            # Calcular Stop Loss (debe cubrir todo el FVG)
            if direction == 'BULLISH':
                # Compra: SL debajo del FVG
                stop_loss = fvg_bottom - (fvg_top - fvg_bottom) * 0.1  # 10% adicional de seguridad
                entry_price = current_price
                take_profit = target_price
            else:
                # Venta: SL arriba del FVG
                stop_loss = fvg_top + (fvg_top - fvg_bottom) * 0.1  # 10% adicional de seguridad
                entry_price = current_price
                take_profit = target_price
            
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
        Intenta optimizar el SL para lograr RR mínimo más rápido
        
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
            
            if direction == 'BULLISH':
                # Compra: SL debe estar debajo del entry
                optimal_sl = entry_price - required_risk
                # Verificar que no esté muy cerca del FVG bottom
                if optimal_sl >= fvg_bottom * 0.99:  # 1% de margen
                    return optimal_sl
            else:
                # Venta: SL debe estar arriba del entry
                optimal_sl = entry_price + required_risk
                # Verificar que no esté muy cerca del FVG top
                if optimal_sl <= fvg_top * 1.01:  # 1% de margen
                    return optimal_sl
            
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
            direction = entry_signal['direction']
            entry_price = entry_signal['entry_price']
            stop_loss = entry_signal['stop_loss']
            take_profit = entry_signal['take_profit']
            rr = entry_signal['rr']
            fvg = entry_signal.get('fvg', {})
            
            # Log estructurado de la orden
            self.logger.info(f"[{symbol}] {'='*70}")
            self.logger.info(f"[{symbol}] 💹 EJECUTANDO ORDEN DE TRADING")
            self.logger.info(f"[{symbol}] {'='*70}")
            self.logger.info(f"[{symbol}] 📊 Dirección: {direction} ({'COMPRA' if direction == 'BULLISH' else 'VENTA'})")
            self.logger.info(f"[{symbol}] 💰 Precio de Entrada: {entry_price:.5f}")
            self.logger.info(f"[{symbol}] 🛑 Stop Loss: {stop_loss:.5f} (Risk: {entry_signal.get('risk', 0):.5f})")
            self.logger.info(f"[{symbol}] 🎯 Take Profit: {take_profit:.5f} (Reward: {entry_signal.get('reward', 0):.5f})")
            self.logger.info(f"[{symbol}] 📈 Risk/Reward: {rr:.2f}:1 (mínimo requerido: {self.min_rr}:1)")
            self.logger.info(f"[{symbol}] 📦 Volumen: {self.volume}")
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
                    volume=self.volume,
                    price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    comment=f"TurtleSoup H4 + FVG {self.entry_timeframe}"
                )
            else:
                result = self.executor.sell(
                    symbol=symbol,
                    volume=self.volume,
                    price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    comment=f"TurtleSoup H4 + FVG {self.entry_timeframe}"
                )
            
            if result['success']:
                self.logger.info(f"[{symbol}] {'='*70}")
                self.logger.info(f"[{symbol}] ✅ ORDEN EJECUTADA EXITOSAMENTE")
                self.logger.info(f"[{symbol}] {'='*70}")
                self.logger.info(f"[{symbol}] 🎫 Ticket: {result['order_ticket']}")
                self.logger.info(f"[{symbol}] 📊 Símbolo: {symbol}")
                self.logger.info(f"[{symbol}] 💰 Precio: {entry_price:.5f}")
                self.logger.info(f"[{symbol}] 📦 Volumen: {self.volume}")
                self.logger.info(f"[{symbol}] 🛑 Stop Loss: {stop_loss:.5f}")
                self.logger.info(f"[{symbol}] 🎯 Take Profit: {take_profit:.5f}")
                self.logger.info(f"[{symbol}] 📈 Risk/Reward: {rr:.2f}:1")
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

