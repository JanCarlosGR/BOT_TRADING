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

from strategies import BaseStrategy
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
            if not self._check_news(symbol):
                return None
            
            # 2. Detectar Turtle Soup en H4
            turtle_soup = detect_turtle_soup_h4(symbol)
            
            if not turtle_soup or not turtle_soup.get('detected'):
                self.turtle_soup_signal = None
                return None
            
            # Guardar señal de Turtle Soup
            self.turtle_soup_signal = turtle_soup
            
            self.logger.info(
                f"Turtle Soup detectado: {turtle_soup['sweep_type']} | "
                f"Barrido: {turtle_soup['swept_candle']} | "
                f"TP: {turtle_soup['target_price']:.5f} | "
                f"Dirección: {turtle_soup['direction']}"
            )
            
            # 3. Buscar entrada en FVG contrario al barrido
            entry_signal = self._find_fvg_entry(symbol, turtle_soup)
            
            if entry_signal:
                # 4. Ejecutar orden
                return self._execute_order(symbol, turtle_soup, entry_signal)
            
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
                self.logger.info(f"Bloqueado por noticias: {reason}")
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
                return None
            
            # Determinar qué tipo de FVG buscamos
            # Si el barrido fue alcista (sweep_type = BULLISH_SWEEP)
            # → Buscamos FVG alcista para entrada bajista
            # Si el barrido fue bajista (sweep_type = BEARISH_SWEEP)
            # → Buscamos FVG bajista para entrada alcista
            
            sweep_type = turtle_soup.get('sweep_type')
            direction = turtle_soup.get('direction')
            fvg_type = fvg.get('fvg_type')
            
            # Verificar que el FVG sea del tipo correcto
            if sweep_type == 'BULLISH_SWEEP' and direction == 'BEARISH':
                # Barrido alcista → buscamos FVG alcista para vender
                if fvg_type != 'ALCISTA':
                    return None
            elif sweep_type == 'BEARISH_SWEEP' and direction == 'BULLISH':
                # Barrido bajista → buscamos FVG bajista para comprar
                if fvg_type != 'BAJISTA':
                    return None
            else:
                return None
            
            # Verificar que el precio haya entrado y salido del FVG
            if not fvg.get('entered_fvg') or not fvg.get('exited_fvg'):
                return None
            
            # Verificar dirección de salida
            exit_direction = fvg.get('exit_direction')
            if exit_direction != direction:
                return None
            
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
            
            if rr < self.min_rr:
                self.logger.debug(f"RR insuficiente: {rr:.2f} < {self.min_rr}")
                # Intentar ajustar SL si es posible
                adjusted_sl = self._optimize_sl(entry_price, take_profit, direction, fvg_top, fvg_bottom)
                if adjusted_sl:
                    new_risk = abs(entry_price - adjusted_sl)
                    new_rr = reward / new_risk
                    if new_rr >= self.min_rr:
                        stop_loss = adjusted_sl
                        rr = new_rr
                    else:
                        return None
                else:
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
            
            self.logger.info(
                f"Ejecutando orden: {direction} | "
                f"Entry: {entry_price:.5f} | "
                f"SL: {stop_loss:.5f} | "
                f"TP: {take_profit:.5f} | "
                f"RR: {rr:.2f}"
            )
            
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
                self.logger.info(f"✅ Orden ejecutada: Ticket {result['order_ticket']}")
                return {
                    'action': f'{direction}_EXECUTED',
                    'ticket': result['order_ticket'],
                    'turtle_soup': turtle_soup,
                    'entry_signal': entry_signal
                }
            else:
                self.logger.error(f"❌ Error al ejecutar orden: {result['message']}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error al ejecutar orden: {e}", exc_info=True)
            return None

