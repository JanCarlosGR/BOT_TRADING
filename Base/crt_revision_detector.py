"""
Módulo para detectar CRT de Revisión en temporalidad H4
Detecta cuando la vela de 5 AM barre extremos de la vela de 1 AM con mecha
pero el cuerpo de la vela 5 AM cierra dentro del rango de la vela 1 AM
El objetivo (TP) es el extremo opuesto de la vela 1 AM (el que no fue barrido)
"""

import logging
from typing import Dict, Optional
from Base.candle_reader import get_candle


class CRTRevisionDetector:
    """
    Detector de CRT de Revisión en temporalidad H4
    Analiza velas de 1 AM y 5 AM (hora NY) para detectar revisiones
    El objetivo (TP) es el extremo opuesto de la vela 1 AM (el que no fue barrido)
    """
    
    def __init__(self):
        """Inicializa el detector de CRT de Revisión"""
        self.logger = logging.getLogger(__name__)
    
    def detect_revision_crt(self, symbol: str) -> Optional[Dict]:
        """
        Detecta CRT de Revisión en H4
        
        Condiciones OBLIGATORIAS:
        1. La vela de 5 AM debe barrer un extremo de la vela de 1 AM (con mecha o cuerpo)
        2. El CUERPO de la vela 5 AM debe cerrar DENTRO del rango de la vela 1 AM (HIGH-LOW)
           - Body Bottom de vela 5 AM >= LOW de vela 1 AM
           - Body Top de vela 5 AM <= HIGH de vela 1 AM
        3. El objetivo (TP) es el extremo OPUESTO de la vela 1 AM:
           - Si se barrió el LOW de vela 1 AM → TP = HIGH de vela 1 AM
           - Si se barrió el HIGH de vela 1 AM → TP = LOW de vela 1 AM
        
        IMPORTANTE: Si el cuerpo cierra dentro del rango (HIGH-LOW) de la vela 1 AM, es Revisión automáticamente
        
        Args:
            symbol: Símbolo a analizar (ej: 'EURUSD')
            
        Returns:
            Dict con información del CRT de Revisión detectado o None:
            {
                'detected': bool,
                'sweep_type': str,  # 'BULLISH_SWEEP' o 'BEARISH_SWEEP'
                'direction': str,   # 'BULLISH' o 'BEARISH' (dirección hacia el TP)
                'target_price': float,  # TP (extremo opuesto de vela 1 AM)
                'swept_extreme': str,   # 'high' o 'low' (extremo barrido)
                'sweep_price': float,   # Precio donde ocurrió el barrido
                'candle_1am': Dict,     # Vela de 1 AM
                'candle_5am': Dict,     # Vela de 5 AM (donde ocurrió el barrido)
                'candle_9am': Dict,     # Vela de 9 AM (donde esperamos alcanzar el objetivo)
                'body_inside_range': bool,  # True si el cuerpo cierra dentro del rango
            }
        """
        try:
            # Obtener velas H4 de 1 AM, 5 AM y 9 AM
            candle_1am = get_candle('H4', '1am', symbol)
            candle_5am = get_candle('H4', '5am', symbol)
            candle_9am = get_candle('H4', '9am', symbol)
            
            if not candle_1am:
                self.logger.warning(f"[{symbol}] CRT Revisión: No se pudo obtener la vela de 1 AM")
                return None
            
            if not candle_5am:
                self.logger.warning(f"[{symbol}] CRT Revisión: No se pudo obtener la vela de 5 AM")
                return None
            
            # Log de diagnóstico de las velas obtenidas
            self.logger.info(
                f"[{symbol}] CRT Revisión - Analizando velas: "
                f"1AM H={candle_1am.get('high'):.5f} L={candle_1am.get('low'):.5f} | "
                f"5AM H={candle_5am.get('high'):.5f} L={candle_5am.get('low'):.5f}"
            )
            
            # La vela de 9 AM es opcional para la detección inicial, pero necesaria para el contexto
            # Si no existe aún, podemos continuar con la detección del patrón
            # (la vela de 9 AM puede estar en formación)
            
            # Obtener extremos y cuerpo de las velas
            candle_1am_high = candle_1am.get('high')
            candle_1am_low = candle_1am.get('low')
            candle_1am_open = candle_1am.get('open')
            candle_1am_close = candle_1am.get('close')
            
            candle_5am_high = candle_5am.get('high')
            candle_5am_low = candle_5am.get('low')
            candle_5am_open = candle_5am.get('open')
            candle_5am_close = candle_5am.get('close')
            
            if None in [candle_1am_high, candle_1am_low, candle_5am_high, candle_5am_low, 
                       candle_1am_open, candle_1am_close, candle_5am_open, candle_5am_close]:
                self.logger.warning(f"Datos incompletos en velas H4 para {symbol}")
                return None
            
            # Calcular cuerpo de las velas
            candle_1am_body_top = max(candle_1am_open, candle_1am_close)
            candle_1am_body_bottom = min(candle_1am_open, candle_1am_close)
            
            candle_5am_body_top = max(candle_5am_open, candle_5am_close)
            candle_5am_body_bottom = min(candle_5am_open, candle_5am_close)
            
            # Determinar si la vela 5 AM es alcista o bajista
            candle_5am_is_bullish = candle_5am_close > candle_5am_open
            
            # Verificar si el cuerpo de la vela 5 AM cierra DENTRO del rango de la vela 1 AM (HIGH-LOW)
            # El cuerpo debe estar completamente dentro del rango completo de la vela 1 AM
            # Body Bottom de vela 5 AM >= LOW de vela 1 AM
            # Body Top de vela 5 AM <= HIGH de vela 1 AM
            body_inside_range = (
                candle_5am_body_bottom >= candle_1am_low and
                candle_5am_body_top <= candle_1am_high
            )
            
            # Si el cuerpo NO está dentro del rango (HIGH-LOW) de la vela 1 AM, no es CRT de Revisión
            if not body_inside_range:
                self.logger.debug(
                    f"[{symbol}] CRT Revisión: Cuerpo de vela 5 AM NO está dentro del rango de vela 1 AM | "
                    f"Body 5AM: {candle_5am_body_bottom:.5f}-{candle_5am_body_top:.5f} | "
                    f"Rango 1AM: {candle_1am_low:.5f}-{candle_1am_high:.5f}"
                )
                return None
            
            # Si el cuerpo está dentro del rango (HIGH-LOW) de la vela 1 AM, es Revisión automáticamente
            # PERO: Si barrió AMBOS extremos, es CRT de EXTREMO, no de Revisión
            # Verificar si barrió ambos extremos
            swept_high = candle_5am_high > candle_1am_high
            swept_low = candle_5am_low < candle_1am_low
            
            # Si barrió ambos extremos, NO es CRT de Revisión (es CRT de Extremo)
            if swept_high and swept_low:
                self.logger.debug(f"[{symbol}] CRT Revisión: Vela 5 AM barrió AMBOS extremos → Es CRT de EXTREMO, no Revisión")
                return None
            
            # Ahora verificamos qué extremo fue barrido para determinar la dirección
            # (solo uno de los dos, ya que descartamos el caso de ambos)
            
            # Verificar si la vela 5 AM barrió el HIGH de la vela 1 AM (con mecha o cuerpo)
            # Para ser barrido, el HIGH de la vela 5 AM debe ser mayor al HIGH de la vela 1 AM
            if swept_high:
                # Se barrió el HIGH de la vela 1 AM
                # El cuerpo cierra dentro del rango (ya verificado arriba)
                # TP = LOW de la vela 1 AM (extremo opuesto)
                result = {
                    'detected': True,
                    'sweep_type': 'BULLISH_SWEEP',  # Barrió el HIGH (alcista)
                    'direction': 'BEARISH',  # Dirección hacia el TP (LOW de vela 1 AM)
                    'target_price': candle_1am_low,  # TP = LOW de vela 1 AM
                    'swept_extreme': 'high',  # Extremo barrido
                    'sweep_price': candle_1am_high,  # Precio barrido (HIGH de vela 1 AM)
                    'candle_1am': candle_1am,
                    'candle_5am': candle_5am,  # Vela donde ocurrió el barrido
                    'candle_9am': candle_9am,  # Vela donde esperamos alcanzar el objetivo
                    'body_inside_range': True,  # Confirmado: cuerpo dentro del rango
                    'close_type': 'BULLISH' if candle_5am_is_bullish else 'BEARISH',
                }
                # Log de validación para diagnóstico
                self.logger.info(
                    f"[{symbol}] ✅ CRT REVISIÓN detectado - Barrió HIGH | "
                    f"TP asignado: {candle_1am_low:.5f} (LOW de vela 1 AM) | "
                    f"HIGH de vela 1 AM: {candle_1am_high:.5f} | "
                    f"Dirección: BEARISH (hacia LOW)"
                )
                return result
            
            # Verificar si la vela 5 AM barrió el LOW de la vela 1 AM (con mecha o cuerpo)
            # Para ser barrido, el LOW de la vela 5 AM debe ser menor al LOW de la vela 1 AM
            elif swept_low:
                # Se barrió el LOW de la vela 1 AM
                # El cuerpo cierra dentro del rango (ya verificado arriba)
                # TP = HIGH de la vela 1 AM (extremo opuesto)
                result = {
                    'detected': True,
                    'sweep_type': 'BEARISH_SWEEP',  # Barrió el LOW (bajista)
                    'direction': 'BULLISH',  # Dirección hacia el TP (HIGH de vela 1 AM)
                    'target_price': candle_1am_high,  # TP = HIGH de vela 1 AM
                    'swept_extreme': 'low',  # Extremo barrido
                    'sweep_price': candle_1am_low,  # Precio barrido (LOW de vela 1 AM)
                    'candle_1am': candle_1am,
                    'candle_5am': candle_5am,  # Vela donde ocurrió el barrido
                    'candle_9am': candle_9am,  # Vela donde esperamos alcanzar el objetivo
                    'body_inside_range': True,  # Confirmado: cuerpo dentro del rango
                    'close_type': 'BULLISH' if candle_5am_is_bullish else 'BEARISH',
                }
                # Log de validación para diagnóstico
                self.logger.info(
                    f"[{symbol}] ✅ CRT REVISIÓN detectado - Barrió LOW | "
                    f"TP asignado: {candle_1am_high:.5f} (HIGH de vela 1 AM) | "
                    f"LOW de vela 1 AM: {candle_1am_low:.5f} | "
                    f"Dirección: BULLISH (hacia HIGH)"
                )
                return result
            
            # No se cumplieron las condiciones para CRT de Revisión
            self.logger.debug(
                f"[{symbol}] CRT Revisión: No se cumplieron condiciones | "
                f"Barrió HIGH: {swept_high} | Barrió LOW: {swept_low} | "
                f"Cuerpo dentro rango: {body_inside_range}"
            )
            return None
            
        except Exception as e:
            self.logger.error(f"Error al detectar CRT de Revisión para {symbol}: {e}", exc_info=True)
            return None


def detect_crt_revision(symbol: str) -> Optional[Dict]:
    """
    Función de conveniencia para detectar CRT de Revisión
    
    Args:
        symbol: Símbolo a analizar
        
    Returns:
        Dict con información del CRT de Revisión o None
    """
    detector = CRTRevisionDetector()
    return detector.detect_revision_crt(symbol)
