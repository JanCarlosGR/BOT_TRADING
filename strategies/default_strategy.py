"""
Estrategia por defecto (placeholder)
Esta estrategia debe ser reemplazada por tus estrategias reales
"""

from strategies import BaseStrategy
import numpy as np
from typing import Optional, Dict


class DefaultStrategy(BaseStrategy):
    """
    Estrategia por defecto (placeholder)
    Esta estrategia debe ser reemplazada por tus estrategias reales
    """
    
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        """
        Análisis básico - placeholder para estrategia real
        
        Args:
            symbol: Símbolo a analizar
            rates: Array de velas OHLCV
            
        Returns:
            None (no genera señales por ahora)
        """
        if len(rates) < 2:
            return None
        
        # Ejemplo básico: obtener último precio
        last_candle = rates[-1]
        current_price = last_candle['close']
        
        self.logger.debug(f"{symbol} - Precio actual: {current_price}")
        
        # TODO: Implementar lógica de estrategia aquí
        # Por ahora retorna None (no hay señal)
        
        return None

