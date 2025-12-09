"""
Estrategia basada en FVG (Fair Value Gap)
Ejemplo de estrategia usando los módulos de Base
"""

from strategies import BaseStrategy
import numpy as np
from typing import Optional, Dict
from Base import can_trade_now, detect_fvg


class FVGStrategy(BaseStrategy):
    """
    Estrategia que usa FVG y verificación de noticias
    """
    
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        """
        Analiza el mercado usando FVG y noticias
        
        Args:
            symbol: Símbolo a analizar
            rates: Array de velas OHLCV
            
        Returns:
            Dict con señal de trading o None
        """
        # 1. Verificar noticias primero
        can_trade, reason, next_news = can_trade_now(symbol, minutes_before=5, minutes_after=5)
        if not can_trade:
            self.logger.info(f"Bloqueado por noticias: {reason}")
            return None
        
        # 2. Detectar FVG en H4
        fvg = detect_fvg(symbol, 'H4')
        if not fvg:
            return None
        
        # 3. Estrategia: FVG completamente lleno y precio salió
        if fvg['fvg_filled_completely'] and fvg['exited_fvg']:
            current_price = rates[-1]['close']
            
            if fvg['exit_direction'] == 'ALCISTA':
                # Señal de compra: FVG alcista lleno, precio salió por arriba
                return self._create_signal(
                    'BUY',
                    symbol,
                    current_price,
                    stop_loss=fvg['fvg_bottom'],
                    take_profit=current_price + fvg['fvg_size'] * 2
                )
            elif fvg['exit_direction'] == 'BAJISTA':
                # Señal de venta: FVG bajista lleno, precio salió por abajo
                return self._create_signal(
                    'SELL',
                    symbol,
                    current_price,
                    stop_loss=fvg['fvg_top'],
                    take_profit=current_price - fvg['fvg_size'] * 2
                )
        
        return None

