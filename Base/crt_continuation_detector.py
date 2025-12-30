"""
Módulo para detectar CRT de Continuación en temporalidad H4
Detecta cuando la vela de 5 AM barre extremos de la vela de 1 AM y cierra con cuerpo fuera del rango
El objetivo (TP) se define desde la vela de 5 AM (HIGH o LOW según el tipo de CRT)
La vela de 9 AM es donde esperamos que el precio alcance ese objetivo
"""

import logging
from typing import Dict, Optional
from Base.candle_reader import get_candle


class CRTContinuationDetector:
    """
    Detector de CRT de Continuación en temporalidad H4
    Analiza velas de 1 AM y 5 AM (hora NY) para detectar continuaciones
    El objetivo (TP) se define desde la vela de 5 AM (HIGH o LOW según el tipo de CRT)
    La vela de 9 AM es donde esperamos que el precio alcance ese objetivo
    """
    
    def __init__(self):
        """Inicializa el detector de CRT de Continuación"""
        self.logger = logging.getLogger(__name__)
    
    def detect_continuation_crt(self, symbol: str) -> Optional[Dict]:
        """
        Detecta CRT de Continuación en H4
        
        Condiciones OBLIGATORIAS:
        1. La vela de 5 AM debe barrer un extremo de la vela de 1 AM (con mecha o cuerpo)
        2. El CLOSE de la vela de 5 AM debe estar FUERA del rango de la vela de 1 AM:
           - Continuación Alcista: Close de vela 5 AM > HIGH de vela 1 AM
           - Continuación Bajista: Close de vela 5 AM < LOW de vela 1 AM
        3. El objetivo (TP) se define desde la vela de 5 AM:
           - Continuación Alcista: TP = HIGH de vela 5 AM
           - Continuación Bajista: TP = LOW de vela 5 AM
        4. La vela de 9 AM es donde esperamos que el precio alcance ese objetivo
        
        IMPORTANTE: Si el CLOSE está dentro del rango, NO es Continuación (podría ser Revisión)
        
        Args:
            symbol: Símbolo a analizar (ej: 'EURUSD')
            
        Returns:
            Dict con información del CRT de Continuación detectado o None:
            {
                'detected': bool,
                'sweep_type': str,  # 'BULLISH_SWEEP' o 'BEARISH_SWEEP'
                'direction': str,   # 'BULLISH' o 'BEARISH' (dirección de continuación)
                'target_price': float,  # TP (HIGH o LOW de vela 5 AM según dirección)
                'sweep_price': float,   # Precio donde ocurrió el barrido
                'candle_1am': Dict,     # Vela de 1 AM
                'candle_5am': Dict,      # Vela de 5 AM (donde se define el objetivo)
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
                self.logger.warning(f"[{symbol}] CRT Continuación: No se pudo obtener la vela de 1 AM")
                return None
            
            if not candle_5am:
                self.logger.warning(f"[{symbol}] CRT Continuación: No se pudo obtener la vela de 5 AM")
                return None
            
            # Log de diagnóstico de las velas obtenidas
            self.logger.info(
                f"[{symbol}] CRT Continuación - Analizando velas: "
                f"1AM H={candle_1am.get('high'):.5f} L={candle_1am.get('low'):.5f} | "
                f"5AM H={candle_5am.get('high'):.5f} L={candle_5am.get('low'):.5f} C={candle_5am.get('close'):.5f}"
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
            
            # La vela de 9 AM puede estar en formación, así que solo validamos si existe
            candle_9am_high = candle_9am.get('high') if candle_9am else None
            candle_9am_low = candle_9am.get('low') if candle_9am else None
            
            # Determinar el rango de la vela de 1 AM (usando cuerpo de vela)
            # El rango del cuerpo es entre el menor y mayor de open/close
            candle_1am_body_top = max(candle_1am_open, candle_1am_close)
            candle_1am_body_bottom = min(candle_1am_open, candle_1am_close)
            
            # Determinar el rango del cuerpo de la vela de 5 AM
            candle_5am_body_top = max(candle_5am_open, candle_5am_close)
            candle_5am_body_bottom = min(candle_5am_open, candle_5am_close)
            
            # Determinar tipo de cierre de la vela de 5 AM
            candle_5am_is_bullish = candle_5am_close > candle_5am_open
            candle_5am_is_bearish = candle_5am_close < candle_5am_open
            
            # CONTINUACIÓN ALCISTA:
            # 1. La vela 5 AM debe barrer el HIGH de la vela 1 AM (HIGH de vela 5 AM > HIGH de vela 1 AM)
            # 2. El CLOSE de la vela 5 AM debe estar FUERA (arriba) del rango: Close > HIGH de vela 1 AM
            # TP = HIGH de vela 5 AM (objetivo definido desde la vela de 5 AM)
            # La vela de 9 AM es donde esperamos que el precio alcance ese objetivo
            
            # Verificar que la vela 5 AM barrió el HIGH de la vela 1 AM
            swept_high = candle_5am_high > candle_1am_high
            
            # Verificar que el CLOSE de la vela 5 AM está FUERA (arriba) del rango de la vela 1 AM
            close_outside_above = candle_5am_close > candle_1am_high
            
            if swept_high and close_outside_above:
                # El Close de la vela 5 AM barrió el HIGH de la vela 1 AM
                # Continuación ALCISTA (Close barrió HIGH)
                # TP = HIGH de vela 5 AM (objetivo definido desde la vela de 5 AM)
                return {
                    'detected': True,
                    'sweep_type': 'BULLISH_SWEEP',  # Close barrió el HIGH
                    'direction': 'BULLISH',  # Continuación alcista
                    'target_price': candle_5am_high,  # TP = HIGH de vela 5 AM
                    'sweep_price': candle_1am_high,  # Precio barrido (HIGH de vela 1 AM)
                    'candle_1am': candle_1am,
                    'candle_5am': candle_5am,  # Vela donde se define el objetivo
                    'candle_9am': candle_9am,  # Vela donde esperamos alcanzar el objetivo
                    'close_type': 'BULLISH' if candle_5am_is_bullish else 'BEARISH',
                    'swept_extreme': 'high',
                    'body_outside': 'above'  # Close cerró arriba del High
                }
            
            # CONTINUACIÓN BAJISTA:
            # 1. La vela 5 AM debe barrer el LOW de la vela 1 AM (LOW de vela 5 AM < LOW de vela 1 AM)
            # 2. El CLOSE de la vela 5 AM debe estar FUERA (debajo) del rango: Close < LOW de vela 1 AM
            # TP = LOW de vela 5 AM (objetivo definido desde la vela de 5 AM)
            # La vela de 9 AM es donde esperamos que el precio alcance ese objetivo
            
            # Verificar que la vela 5 AM barrió el LOW de la vela 1 AM
            swept_low = candle_5am_low < candle_1am_low
            
            # Verificar que el CLOSE de la vela 5 AM está FUERA (debajo) del rango de la vela 1 AM
            close_outside_below = candle_5am_close < candle_1am_low
            
            if swept_low and close_outside_below:
                # El Close de la vela 5 AM barrió el LOW de la vela 1 AM
                # Continuación BAJISTA (Close barrió LOW)
                # TP = LOW de vela 5 AM (objetivo definido desde la vela de 5 AM)
                return {
                    'detected': True,
                    'sweep_type': 'BEARISH_SWEEP',  # Close barrió el LOW
                    'direction': 'BEARISH',  # Continuación bajista
                    'target_price': candle_5am_low,  # TP = LOW de vela 5 AM
                    'sweep_price': candle_1am_low,  # Precio barrido (LOW de vela 1 AM)
                    'candle_1am': candle_1am,
                    'candle_5am': candle_5am,  # Vela donde se define el objetivo
                    'candle_9am': candle_9am,  # Vela donde esperamos alcanzar el objetivo
                    'close_type': 'BEARISH' if candle_5am_is_bearish else 'BULLISH',
                    'swept_extreme': 'low',
                    'body_outside': 'below'  # Close cerró abajo del Low
                }
            
            # No se detectó CRT de Continuación
            self.logger.debug(
                f"[{symbol}] CRT Continuación: No se cumplieron condiciones | "
                f"Barrió HIGH: {swept_high} | Barrió LOW: {swept_low} | "
                f"Close fuera arriba: {close_outside_above} | Close fuera abajo: {close_outside_below}"
            )
            return {
                'detected': False,
                'candle_1am': candle_1am,
                'candle_5am': candle_5am,
                'candle_9am': candle_9am
            }
            
        except Exception as e:
            self.logger.error(f"Error al detectar CRT de Continuación: {e}", exc_info=True)
            return None


def detect_crt_continuation(symbol: str) -> Optional[Dict]:
    """
    Función de conveniencia para detectar CRT de Continuación en H4
    
    Args:
        symbol: Símbolo a analizar
        
    Returns:
        Dict con información del CRT de Continuación o None
    """
    detector = CRTContinuationDetector()
    return detector.detect_continuation_crt(symbol)
