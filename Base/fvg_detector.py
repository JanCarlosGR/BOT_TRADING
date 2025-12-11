"""
Detector de Fair Value Gap (FVG) en tiempo real
Detecta si el precio actual está formando un FVG y si entró/salió de la zona
"""

import MetaTrader5 as mt5
import logging
from typing import Dict, Optional, List
from datetime import datetime
from .candle_reader import get_candle


class FVGDetector:
    """Detector de Fair Value Gaps (FVG) en tiempo real"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def _get_recent_candles(self, symbol: str, timeframe: str, count: int = 3) -> List[Dict]:
        """
        Obtiene la vela actual (en formación) + las 2 velas anteriores cerradas
        
        Args:
            symbol: Símbolo a analizar
            timeframe: Temporalidad (ej: 'H4', 'H1', 'M5')
            count: Número de velas a obtener (default: 3 = actual + 2 anteriores)
            
        Returns:
            Lista de velas ordenadas (más antigua primero): [anterior2, anterior1, actual]
        """
        candles = []
        tf = self._parse_timeframe(timeframe)
        
        # Obtener vela actual (posición 0) + 2 velas anteriores (posición 1 y 2)
        # MT5 devuelve las velas de más reciente (índice 0) a más antigua (índice n)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, 3)
        
        if rates is not None and len(rates) >= 3:
            # MT5 devuelve las velas de más reciente (índice 0) a más antigua (índice n)
            # Pero para asegurar orden correcto, siempre ordenamos por tiempo
            # Necesitamos: [más antigua, del medio, más reciente]
            
            # Procesar todas las velas y ordenarlas por tiempo
            for i, candle_data in enumerate(rates):
                candle_time = datetime.fromtimestamp(candle_data['time'])
                candles.append({
                    'time': candle_time,
                    'open': float(candle_data['open']),
                    'high': float(candle_data['high']),
                    'low': float(candle_data['low']),
                    'close': float(candle_data['close']),
                    'volume': int(candle_data['tick_volume']),
                    'is_current': (i == 0)  # La primera (más reciente) es la actual
                })
            
            # Ordenar siempre por tiempo para asegurar orden correcto (más antigua primero)
            candles = sorted(candles, key=lambda x: x['time'])
            
            # Marcar la más reciente como actual (puede haber cambiado después de ordenar)
            if len(candles) > 0:
                candles[-1]['is_current'] = True
                # Asegurar que las anteriores no sean marcadas como actuales
                for i in range(len(candles) - 1):
                    candles[i]['is_current'] = False
        
        # Ya están ordenadas por tiempo (más antigua primero)
        return candles
    
    def _parse_timeframe(self, timeframe: str) -> int:
        """Convierte string de temporalidad a constante MT5"""
        timeframe_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
            'W1': mt5.TIMEFRAME_W1,
        }
        return timeframe_map.get(timeframe.upper(), mt5.TIMEFRAME_H4)
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Obtiene el precio actual (bid)"""
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            return float(tick.bid)
        return None
    
    def detect_fvg(self, symbol: str, timeframe: str = 'H4') -> Optional[Dict]:
        """
        Detecta si el precio actual está formando un FVG
        
        Args:
            symbol: Símbolo a analizar
            timeframe: Temporalidad para análisis
            
        Returns:
            Dict con información del FVG o None si no hay FVG en formación
        """
        # Obtener vela actual + 2 velas anteriores
        candles = self._get_recent_candles(symbol, timeframe, count=3)
        
        if len(candles) < 3:
            return None
        
        # Obtener precio actual
        current_price = self._get_current_price(symbol)
        if current_price is None:
            return None
        
        # Estructura: candles[0] = vela1 (más antigua), candles[1] = vela2, candles[2] = vela3 (actual)
        vela1 = candles[0]  # Más antigua
        vela2 = candles[1]  # Del medio
        vela3 = candles[2]  # Actual
        
        # Buscar FVG entre las 3 velas:
        # Prioridad: FVG entre vela1 (más antigua) y vela3 (actual) - se forma CON la vela actual
        
        # Prioridad 1: FVG alcista entre vela1 (más antigua) y vela3 (actual)
        # FVG alcista: Low vela1 < High vela3 (sin solapamiento)
        # IMPORTANTE: Para que sea un FVG real, NO debe haber solapamiento
        # La vela 3 NO debe tocar el nivel de la vela 1 (vela3.low debe ser > vela1.high)
        # Rango del FVG: entre vela1.high y vela3.low (la brecha)
        if vela1['low'] < vela3['high'] and vela3['low'] > vela1['high']:
            fvg_bottom = vela1['high']  # HIGH de la vela 1 (más antigua) - bottom del FVG
            fvg_top = vela3['low']  # LOW de la vela 3 (actual) - top del FVG
            # FVG alcista en formación con vela actual
            return self._analyze_fvg(
                fvg_type='ALCISTA',
                fvg_bottom=fvg_bottom,
                fvg_top=fvg_top,
                current_price=current_price,
                forming_candle=vela3,
                prev_candle=vela1,
                next_candle=vela3,
                symbol=symbol,
                timeframe=timeframe
            )
        
        # Prioridad 2: FVG bajista entre vela1 (más antigua) y vela3 (actual)
        # FVG bajista: High vela1 > Low vela3 (sin solapamiento)
        # IMPORTANTE: Para que sea un FVG real, NO debe haber solapamiento
        # La vela 3 NO debe tocar el nivel de la vela 1 (vela3.high debe ser < vela1.low)
        # Rango del FVG: entre vela3.high y vela1.low (la brecha)
        elif vela1['high'] > vela3['low'] and vela3['high'] < vela1['low']:
            fvg_bottom = vela3['high']  # HIGH de la vela 3 (actual) - bottom del FVG
            fvg_top = vela1['low']  # LOW de la vela 1 (más antigua) - top del FVG
            # FVG bajista en formación con vela actual
            return self._analyze_fvg(
                fvg_type='BAJISTA',
                fvg_bottom=fvg_bottom,
                fvg_top=fvg_top,
                current_price=current_price,
                forming_candle=vela3,
                prev_candle=vela1,
                next_candle=vela3,
                symbol=symbol,
                timeframe=timeframe
            )
        
        # 3. Si no hay FVG entre vela2 y vela3, verificar entre vela1 y vela2
        # FVG alcista: vela1.high < vela2.low
        if vela1['high'] < vela2['low']:
            fvg_bottom = vela1['high']
            fvg_top = vela2['low']
            # FVG alcista ya formado, verificar si precio está interactuando
            if fvg_bottom <= current_price <= fvg_top or \
               (current_price > fvg_top and current_price - fvg_top < (fvg_top - fvg_bottom) * 2) or \
               (current_price < fvg_bottom and fvg_bottom - current_price < (fvg_top - fvg_bottom) * 2):
                return self._analyze_fvg(
                    fvg_type='ALCISTA',
                    fvg_bottom=fvg_bottom,
                    fvg_top=fvg_top,
                    current_price=current_price,
                    forming_candle=vela2,
                    prev_candle=vela1,
                    next_candle=vela3,
                    symbol=symbol,
                    timeframe=timeframe
                )
        
        # FVG bajista entre vela1 y vela2: vela1.low > vela2.high
        elif vela1['low'] > vela2['high']:
            fvg_top = vela1['low']
            fvg_bottom = vela2['high']
            # FVG bajista ya formado, verificar si precio está interactuando
            if fvg_bottom <= current_price <= fvg_top or \
               (current_price > fvg_top and current_price - fvg_top < (fvg_top - fvg_bottom) * 2) or \
               (current_price < fvg_bottom and fvg_bottom - current_price < (fvg_top - fvg_bottom) * 2):
                return self._analyze_fvg(
                    fvg_type='BAJISTA',
                    fvg_bottom=fvg_bottom,
                    fvg_top=fvg_top,
                    current_price=current_price,
                    forming_candle=vela2,
                    prev_candle=vela1,
                    next_candle=vela3,
                    symbol=symbol,
                    timeframe=timeframe
                )
        
        return None
    
    def _analyze_fvg(self, fvg_type: str, fvg_bottom: float, fvg_top: float,
                     current_price: float, forming_candle: Dict, prev_candle: Dict,
                     next_candle: Dict, symbol: str, timeframe: str) -> Dict:
        """
        Analiza el FVG detectado y verifica entrada/salida del precio, y si está siendo llenado
        Usa solo las 3 velas: prev_candle (vela1), forming_candle (vela3), y next_candle (vela3 también)
        
        Args:
            fvg_type: 'ALCISTA' o 'BAJISTA'
            fvg_bottom: Precio inferior del FVG
            fvg_top: Precio superior del FVG
            current_price: Precio actual
            forming_candle: Vela que forma el FVG (vela3 - actual)
            prev_candle: Vela anterior (vela1 - más antigua)
            next_candle: Vela siguiente (vela3 - actual, mismo que forming_candle)
            symbol: Símbolo
            timeframe: Temporalidad
            
        Returns:
            Dict con información completa del FVG
        """
        # El FVG es una BRECHA, no un rango donde el precio puede estar "dentro"
        # El precio puede estar:
        # - Por encima del FVG (current_price > fvg_top)
        # - Por debajo del FVG (current_price < fvg_bottom)
        # - Tocando/llenando el FVG (entre bottom y top)
        
        # Verificar si el precio está tocando el FVG (en el rango de la brecha)
        price_touching_fvg = fvg_bottom <= current_price <= fvg_top
        
        # Analizar entrada/salida basándose en las velas y precio actual
        entered_fvg = False
        exited_fvg = False
        exit_direction = None
        
        # Verificar si el precio entró/tocó el FVG
        # IMPORTANTE: Solo la vela3 (actual/forming_candle) determina si entró al FVG
        # El precio entró al FVG si la vela3 tocó el rango del FVG
        
        # Verificar si el HIGH de la vela3 tocó el FVG (prioridad - como menciona el usuario)
        high_touched = (fvg_bottom <= forming_candle['high'] <= fvg_top)
        # Verificar si el LOW de la vela3 tocó el FVG
        low_touched = (fvg_bottom <= forming_candle['low'] <= fvg_top)
        # Verificar si la vela3 cruzó el FVG completamente
        candle_crossed = (forming_candle['low'] < fvg_bottom and forming_candle['high'] > fvg_top)
        # Verificar si la vela3 tocó el FVG (high o low dentro del rango)
        candle_touched = (forming_candle['low'] <= fvg_top and forming_candle['high'] >= fvg_bottom)
        
        # El precio entró/tocó el FVG si la vela3 (actual) tocó el FVG:
        # - El HIGH de la vela3 tocó el FVG (más importante, como menciona el usuario)
        # - El LOW de la vela3 tocó el FVG
        # - La vela3 cruzó o tocó el FVG
        if high_touched or low_touched or candle_crossed or candle_touched:
            entered_fvg = True
        
        # Analizar llenado del FVG usando solo las 3 velas
        # NOTA IMPORTANTE: Para completar un FVG alcista, el HIGH de la vela 3 debe llegar al LOW de la vela 1
        # Para completar un FVG bajista, el LOW de la vela 3 debe llegar al HIGH de la vela 1
        bottom_touched = False
        top_touched = False
        fvg_filled_completely = False
        fvg_filling_partially = False
        
        # Tolerancia para considerar que tocó un nivel
        tolerance = (fvg_top - fvg_bottom) * 0.0001  # 0.01% de tolerancia
        
        # Para FVG ALCISTA: el precio debe llenar completamente la brecha del FVG
        if fvg_type == 'ALCISTA':
            # El bottom del FVG es prev_candle['high'] (vela1.high)
            # El top del FVG es forming_candle['low'] (vela3.low)
            # Para completarlo: el LOW de vela3 debe tocar o bajar por debajo del HIGH de vela1
            # Expresión lógica: BullishFVG_Fill = (Low_V3 <= High_V1)
            if forming_candle['low'] <= prev_candle['high'] + tolerance:
                # El LOW de vela3 tocó o bajó por debajo del HIGH de vela1 - FVG completado
                fvg_filled_completely = True
                bottom_touched = True
                top_touched = True
            else:
                # Verificar si tocó el bottom o top del FVG
                # Para FVG alcista: bottom = High vela1, top = Low vela3
                # Bottom tocado: Low vela3 <= High vela1 (mismo que llenado completo)
                if forming_candle['low'] <= prev_candle['high'] + tolerance:
                    bottom_touched = True
                # Top tocado: cuando el precio alcanza el top del FVG (Low vela3)
                if forming_candle['low'] <= fvg_top + tolerance:
                    top_touched = True
        
        # Para FVG BAJISTA: el precio debe llenar completamente la brecha del FVG
        elif fvg_type == 'BAJISTA':
            # El bottom del FVG es forming_candle['high'] (vela3.high)
            # El top del FVG es prev_candle['low'] (vela1.low)
            # Para completarlo: el HIGH de vela3 debe tocar o superar el LOW de vela1
            # Expresión lógica: BearishFVG_Fill = (High_V3 >= Low_V1)
            if forming_candle['high'] >= prev_candle['low'] - tolerance:
                # El HIGH de vela3 tocó o superó el LOW de vela1 - FVG completado
                fvg_filled_completely = True
                bottom_touched = True
                top_touched = True
            else:
                # Verificar si tocó el bottom o top del FVG
                # Para FVG bajista: bottom = High vela3, top = Low vela1
                # Top tocado: High vela3 >= Low vela1 (mismo que llenado completo)
                if forming_candle['high'] >= prev_candle['low'] - tolerance:
                    top_touched = True
                # Bottom tocado: cuando el precio alcanza el bottom del FVG (High vela3)
                if forming_candle['high'] >= fvg_bottom - tolerance:
                    bottom_touched = True
        
        # Verificar también con el precio actual
        if current_price <= fvg_bottom + tolerance:
            bottom_touched = True
        if current_price >= fvg_top - tolerance:
            top_touched = True
        
        # Determinar si está llenando parcialmente
        # Está llenando parcialmente si:
        # - Entró/tocó el FVG (entered_fvg = True)
        # - Tocó el bottom o el top (pero no ambos)
        # - Pero no ha llenado completamente
        if entered_fvg and not fvg_filled_completely and (bottom_touched or top_touched):
            fvg_filling_partially = True
        
        # Verificar salida del FVG
        # El precio salió del FVG si:
        # 1. Anteriormente entró/tocó el FVG (entered_fvg = True)
        # 2. Y ahora está fuera del rango del FVG
        if entered_fvg and not price_touching_fvg:
            exited_fvg = True
            if current_price > fvg_top:
                # Precio salió por arriba (dirección alcista)
                exit_direction = 'ALCISTA'
            elif current_price < fvg_bottom:
                # Precio salió por abajo (dirección bajista)
                exit_direction = 'BAJISTA'
        
        # Si el precio está tocando el FVG, no ha salido aún
        if price_touching_fvg:
            exited_fvg = False
            exit_direction = None
        
        # Calcular tamaño del FVG
        fvg_size = fvg_top - fvg_bottom
        
        # Determinar estado actual
        if fvg_filled_completely:
            status = 'LLENO_COMPLETO'
        elif fvg_filling_partially:
            status = 'LLENANDO_PARCIAL'
        elif price_touching_fvg:
            status = 'TOCANDO'
        elif exited_fvg:
            status = 'SALIO'
        else:
            status = 'FUERA'
        
        return {
            'fvg_detected': True,
            'fvg_type': fvg_type,  # 'ALCISTA' o 'BAJISTA'
            'fvg_bottom': fvg_bottom,
            'fvg_top': fvg_top,
            'fvg_size': fvg_size,
            'current_price': current_price,
            'is_inside_fvg': price_touching_fvg,  # Mantener compatibilidad, pero ahora significa "tocando"
            'price_touching_fvg': price_touching_fvg,  # Precio tocando el FVG (en el rango de la brecha)
            'entered_fvg': entered_fvg,
            'exited_fvg': exited_fvg,
            'exit_direction': exit_direction,  # 'ALCISTA' o 'BAJISTA' o None
            'status': status,  # 'DENTRO', 'SALIO', 'FUERA', 'LLENANDO_PARCIAL', 'LLENO_COMPLETO'
            'fvg_filling_partially': fvg_filling_partially,  # True si está llenando parcialmente
            'fvg_filled_completely': fvg_filled_completely,  # True si está completamente lleno
            'bottom_touched': bottom_touched,  # True si el precio tocó el bottom del FVG
            'top_touched': top_touched,  # True si el precio tocó el top del FVG
            'forming_candle': {
                'time': forming_candle['time'],
                'open': forming_candle['open'],
                'high': forming_candle['high'],
                'low': forming_candle['low'],
                'close': forming_candle['close'],
            },
            'prev_candle': {
                'time': prev_candle['time'],
                'open': prev_candle['open'],
                'high': prev_candle['high'],
                'low': prev_candle['low'],
                'close': prev_candle['close'],
            },
            'next_candle': {
                'time': next_candle['time'],
                'open': next_candle['open'],
                'high': next_candle['high'],
                'low': next_candle['low'],
                'close': next_candle['close'],
            },
            'symbol': symbol,
            'timeframe': timeframe,
            'timestamp': datetime.now()
        }


# Función global para facilitar el uso
def detect_fvg(symbol: str, timeframe: str = 'H4') -> Optional[Dict]:
    """
    Detecta si el precio actual está formando un FVG
    
    Args:
        symbol: Símbolo a analizar (ej: 'EURUSD')
        timeframe: Temporalidad (ej: 'H4', 'H1', 'M5')
        
    Returns:
        Dict con información del FVG o None si no hay FVG en formación
        
    Ejemplo:
        fvg = detect_fvg('EURUSD', 'H4')
        if fvg:
            print(f"FVG {fvg['fvg_type']} detectado")
            print(f"Entró: {fvg['entered_fvg']}")
            print(f"Salió: {fvg['exited_fvg']}")
            print(f"Dirección salida: {fvg['exit_direction']}")
    """
    detector = FVGDetector()
    return detector.detect_fvg(symbol, timeframe)

