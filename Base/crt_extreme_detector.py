"""
Módulo para detectar CRT de Extremo en temporalidad H4
Detecta cuando la vela de 5 AM barre AMBOS extremos (HIGH y LOW) de la vela de 1 AM
El objetivo (TP) se define según el tipo de cierre de la vela 5 AM:
- Si cerró alcista (Close > Open) → TP = HIGH de vela 5 AM
- Si cerró bajista (Close < Open) → TP = LOW de vela 5 AM
"""

import logging
from typing import Dict, Optional
from Base.candle_reader import get_candle


class CRTextremeDetector:
    """
    Detector de CRT de Extremo en temporalidad H4
    Analiza velas de 1 AM y 5 AM (hora NY) para detectar cuando se barren ambos extremos
    El objetivo (TP) se define según el tipo de cierre de la vela 5 AM
    """
    
    def __init__(self):
        """Inicializa el detector de CRT de Extremo"""
        self.logger = logging.getLogger(__name__)
    
    def detect_extreme_crt(self, symbol: str) -> Optional[Dict]:
        """
        Detecta CRT de Extremo en H4
        
        Condiciones OBLIGATORIAS:
        1. La vela de 5 AM debe barrer AMBOS extremos de la vela de 1 AM:
           - HIGH de vela 5 AM > HIGH de vela 1 AM
           - LOW de vela 5 AM < LOW de vela 1 AM
        2. El objetivo (TP) se define según el tipo de cierre de la vela 5 AM:
           - Si cerró alcista (Close > Open) → TP = HIGH de vela 5 AM
           - Si cerró bajista (Close < Open) → TP = LOW de vela 5 AM
        3. La vela de 9 AM es donde esperamos que el precio alcance ese objetivo
        
        Args:
            symbol: Símbolo a analizar (ej: 'EURUSD')
            
        Returns:
            Dict con información del CRT de Extremo detectado o None:
            {
                'detected': bool,
                'sweep_type': str,  # 'EXTREME_SWEEP'
                'direction': str,   # 'BULLISH' o 'BEARISH' (dirección hacia el TP)
                'target_price': float,  # TP (HIGH o LOW de vela 5 AM según cierre)
                'swept_high': float,    # Precio barrido (HIGH de vela 1 AM)
                'swept_low': float,     # Precio barrido (LOW de vela 1 AM)
                'candle_1am': Dict,      # Vela de 1 AM
                'candle_5am': Dict,       # Vela de 5 AM (donde se define el objetivo)
                'candle_9am': Dict,      # Vela de 9 AM (donde esperamos alcanzar el objetivo)
                'close_type': str,       # 'BULLISH' o 'BEARISH' (tipo de cierre de vela 5 AM)
            }
        """
        try:
            # Obtener velas H4 de 1 AM, 5 AM y 9 AM
            candle_1am = get_candle('H4', '1am', symbol)
            candle_5am = get_candle('H4', '5am', symbol)
            candle_9am = get_candle('H4', '9am', symbol)
            
            if not candle_1am:
                self.logger.warning(f"[{symbol}] CRT Extremo: No se pudo obtener la vela de 1 AM")
                return None
            
            if not candle_5am:
                self.logger.warning(f"[{symbol}] CRT Extremo: No se pudo obtener la vela de 5 AM")
                return None
            
            # Log de diagnóstico de las velas obtenidas
            self.logger.info(
                f"[{symbol}] CRT Extremo - Analizando velas: "
                f"1AM H={candle_1am.get('high'):.5f} L={candle_1am.get('low'):.5f} | "
                f"5AM H={candle_5am.get('high'):.5f} L={candle_5am.get('low'):.5f}"
            )
            
            # La vela de 9 AM es opcional para la detección inicial, pero necesaria para el contexto
            # Si no existe aún, podemos continuar con la detección del patrón
            # (la vela de 9 AM puede estar en formación)
            
            # Obtener extremos de las velas
            candle_1am_high = candle_1am.get('high')
            candle_1am_low = candle_1am.get('low')
            candle_1am_open = candle_1am.get('open')
            candle_1am_close = candle_1am.get('close')
            
            candle_5am_high = candle_5am.get('high')
            candle_5am_low = candle_5am.get('low')
            candle_5am_open = candle_5am.get('open')
            candle_5am_close = candle_5am.get('close')
            
            # Validar que las velas 1 AM y 5 AM tengan todos los datos necesarios
            if any(x is None for x in [candle_1am_high, candle_1am_low, candle_1am_open, candle_1am_close,
                                       candle_5am_high, candle_5am_low, candle_5am_open, candle_5am_close]):
                self.logger.warning(f"Velas incompletas para {symbol}")
                return None
            
            # Verificar que la vela 5 AM barrió AMBOS extremos de la vela 1 AM
            swept_high = candle_5am_high > candle_1am_high
            swept_low = candle_5am_low < candle_1am_low
            
            if not (swept_high and swept_low):
                # No se cumplió la condición: debe barrer ambos extremos
                self.logger.debug(
                    f"[{symbol}] CRT Extremo: No barrió AMBOS extremos | "
                    f"Barrió HIGH: {swept_high} | Barrió LOW: {swept_low}"
                )
                return None
            
            # Se cumplió: la vela 5 AM barrió ambos extremos
            # Ahora determinar el objetivo según el tipo de cierre de la vela 5 AM
            
            # Determinar tipo de cierre de la vela de 5 AM
            candle_5am_is_bullish = candle_5am_close > candle_5am_open
            candle_5am_is_bearish = candle_5am_close < candle_5am_open
            
            # Determinar objetivo (TP) según el tipo de cierre
            if candle_5am_is_bullish:
                # Vela 5 AM cerró alcista → TP = HIGH de vela 5 AM
                target_price = candle_5am_high
                direction = 'BULLISH'  # Dirección hacia el HIGH
                close_type = 'BULLISH'
            elif candle_5am_is_bearish:
                # Vela 5 AM cerró bajista → TP = LOW de vela 5 AM
                target_price = candle_5am_low
                direction = 'BEARISH'  # Dirección hacia el LOW
                close_type = 'BEARISH'
            else:
                # Vela 5 AM cerró sin cuerpo (doji) - no se puede determinar dirección
                # Por defecto, usar HIGH como objetivo
                self.logger.warning(f"Vela 5 AM cerró sin cuerpo (doji) para {symbol}, usando HIGH como objetivo por defecto")
                target_price = candle_5am_high
                direction = 'BULLISH'
                close_type = 'DOJI'
            
            return {
                'detected': True,
                'sweep_type': 'EXTREME_SWEEP',  # Barrió ambos extremos
                'direction': direction,  # Dirección hacia el TP
                'target_price': target_price,  # TP (HIGH o LOW de vela 5 AM según cierre)
                'swept_high': candle_1am_high,  # Precio barrido (HIGH de vela 1 AM)
                'swept_low': candle_1am_low,   # Precio barrido (LOW de vela 1 AM)
                'candle_1am': candle_1am,
                'candle_5am': candle_5am,  # Vela donde se define el objetivo
                'candle_9am': candle_9am,  # Vela donde esperamos alcanzar el objetivo
                'close_type': close_type,  # Tipo de cierre de vela 5 AM
            }
            
        except Exception as e:
            self.logger.error(f"Error al detectar CRT de Extremo para {symbol}: {e}", exc_info=True)
            return None


def detect_crt_extreme(symbol: str) -> Optional[Dict]:
    """
    Función de conveniencia para detectar CRT de Extremo en H4
    
    Args:
        symbol: Símbolo a analizar
        
    Returns:
        Dict con información del CRT de Extremo o None
    """
    detector = CRTextremeDetector()
    return detector.detect_extreme_crt(symbol)
