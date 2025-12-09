# Documentación: Función get_candle() para Estrategias de Trading

## 📖 Introducción

La función `get_candle()` es una herramienta reutilizable para obtener información de velas de MetaTrader 5 de forma sencilla. Está diseñada para ser usada dentro de estrategias de trading y maneja automáticamente la conversión entre zonas horarias (NY y MT5).

---

## 🚀 Uso Básico

### Importar la función

```python
from candle_reader import get_candle
```

### Sintaxis

```python
candle = get_candle(timeframe, time_ref, symbol)
```

### Parámetros

- **`timeframe`** (str): Temporalidad de la vela
  - Opciones: `'M1'`, `'M5'`, `'M15'`, `'M30'`, `'H1'`, `'H4'`, `'D1'`, `'W1'`, `'MN1'`
  
- **`time_ref`** (str): Referencia de tiempo
  - `'ahora'` o `'actual'`: Vela actual (en formación o última cerrada)
  - `'1am'`, `'5am'`, `'9am'`, etc.: Hora específica en formato 12h (horario NY)
  - `'13:00'`, `'9:00'`, etc.: Hora específica en formato 24h (horario NY)
  
- **`symbol`** (str): Símbolo a consultar (ej: `'EURUSD'`, `'GBPUSD'`)
  - Requerido si no se configura un símbolo por defecto

### Retorno

Retorna un diccionario (`Dict`) con la información de la vela o `None` si no se encuentra.

---

## 📊 Estructura de Datos Retornada

```python
{
    'open': float,           # Precio de apertura
    'high': float,           # Precio máximo
    'low': float,            # Precio mínimo
    'close': float,          # Precio de cierre
    'volume': int,            # Volumen de ticks
    'time': int,              # Timestamp Unix
    'datetime': datetime,      # Objeto datetime de la vela
    'type': str,              # "ALCISTA", "BAJISTA" o "DOJI"
    'is_bullish': bool,       # True si es alcista
    'is_bearish': bool,       # True si es bajista
    'is_current': bool,        # True si es la vela actual
    'body_size': float,       # Tamaño del cuerpo (abs(close - open))
    'total_range': float,     # Rango total (high - low)
    'upper_wick': float,      # Tamaño de la mecha superior
    'lower_wick': float,      # Tamaño de la mecha inferior
}
```

---

## 💡 Ejemplos de Uso

### Ejemplo 1: Obtener vela actual

```python
from candle_reader import get_candle

# Vela H4 actual
candle = get_candle('H4', 'ahora', 'EURUSD')

if candle:
    print(f"Precio actual: {candle['close']}")
    print(f"Tipo: {candle['type']}")
    if candle['is_bullish']:
        print("Vela alcista detectada")
```

### Ejemplo 2: Obtener velas de horarios específicos

```python
# Vela H4 de las 1am NY
candle_1am = get_candle('H4', '1am', 'EURUSD')

# Vela H4 de las 5am NY
candle_5am = get_candle('H4', '5am', 'EURUSD')

# Vela H4 de las 9am NY
candle_9am = get_candle('H4', '9am', 'EURUSD')

if candle_1am and candle_5am and candle_9am:
    # Análisis de las tres velas
    if candle_1am['is_bullish'] and candle_5am['is_bullish'] and candle_9am['is_bullish']:
        print("Todas las velas son alcistas")
```

### Ejemplo 3: Usar en una estrategia

```python
from candle_reader import get_candle
from strategies import BaseStrategy
import numpy as np
from typing import Optional, Dict

class MiEstrategia(BaseStrategy):
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        # Obtener vela H4 de las 1am NY
        candle_1am = get_candle('H4', '1am', symbol)
        
        if not candle_1am:
            return None
        
        # Obtener vela H4 de las 9am NY
        candle_9am = get_candle('H4', '9am', symbol)
        
        if not candle_9am:
            return None
        
        # Lógica de la estrategia
        # Ejemplo: Si ambas velas son alcistas y hay ruptura
        if candle_1am['is_bullish'] and candle_9am['is_bullish']:
            if candle_9am['close'] > candle_1am['high']:
                # Señal de compra
                current_price = rates[-1]['close']
                return self._create_signal(
                    'BUY',
                    symbol,
                    current_price,
                    stop_loss=candle_9am['low'],
                    take_profit=current_price + (current_price - candle_9am['low']) * 2
                )
        
        return None
```

### Ejemplo 4: Análisis de múltiples temporalidades

```python
# Obtener velas de diferentes timeframes
candle_m5 = get_candle('M5', 'ahora', 'EURUSD')
candle_h1 = get_candle('H1', 'ahora', 'EURUSD')
candle_h4 = get_candle('H4', '9am', 'EURUSD')

if candle_m5 and candle_h1 and candle_h4:
    # Análisis multi-timeframe
    if (candle_m5['is_bullish'] and 
        candle_h1['is_bullish'] and 
        candle_h4['is_bullish']):
        print("Tendencia alcista en todos los timeframes")
```

### Ejemplo 5: Análisis de rango y volatilidad

```python
candle = get_candle('H4', '1am', 'EURUSD')

if candle:
    # Calcular volatilidad
    volatility = candle['total_range'] / candle['close']
    
    # Análisis de mechas
    if candle['upper_wick'] > candle['body_size']:
        print("Presión vendedora (mecha superior grande)")
    
    if candle['lower_wick'] > candle['body_size']:
        print("Presión compradora (mecha inferior grande)")
    
    # Rango de la vela
    print(f"Rango: {candle['low']:.5f} - {candle['high']:.5f}")
    print(f"Rango total: {candle['total_range']:.5f}")
```

---

## ⚙️ Conversión de Zona Horaria

La función maneja automáticamente la conversión entre:
- **Zona horaria de referencia**: Nueva York (America/New_York)
- **Zona horaria de MT5**: Detectada automáticamente (offset de 7 horas)

### Ejemplos de conversión:

| Hora NY | Hora MT5 | Vela H4 que contiene |
|---------|----------|---------------------|
| 1am     | 8am      | Vela que inicia 4am MT5 (cubre 4am-8am) |
| 5am     | 12pm     | Vela que inicia 8am MT5 (cubre 8am-12pm) |
| 9am     | 4pm      | Vela que inicia 12pm MT5 (cubre 12pm-4pm) |

**Nota importante**: La función busca la vela que **contiene** la hora especificada, no la que inicia en esa hora.

---

## 🔧 Uso Avanzado: Instancia Reutilizable

Para múltiples consultas, es más eficiente crear una instancia:

```python
from candle_reader import create_candle_reader

# Crear lector con símbolo por defecto
reader = create_candle_reader('EURUSD')

# Usar múltiples veces sin especificar símbolo
candle_1am = reader.get_candle('H4', '1am')
candle_5am = reader.get_candle('H4', '5am')
candle_9am = reader.get_candle('H4', '9am')
```

---

## 📝 Casos de Uso Comunes en Estrategias

### 1. Estrategia basada en velas de apertura

```python
def check_opening_candles(symbol):
    """Verifica las velas de apertura del día"""
    candle_1am = get_candle('H4', '1am', symbol)
    candle_5am = get_candle('H4', '5am', symbol)
    
    if candle_1am and candle_5am:
        # Si ambas son alcistas, tendencia alcista
        if candle_1am['is_bullish'] and candle_5am['is_bullish']:
            return 'BULLISH'
        # Si ambas son bajistas, tendencia bajista
        elif candle_1am['is_bearish'] and candle_5am['is_bearish']:
            return 'BEARISH'
    
    return 'NEUTRAL'
```

### 2. Detección de ruptura de rango

```python
def check_breakout(symbol):
    """Detecta ruptura del rango de la vela de las 1am"""
    candle_1am = get_candle('H4', '1am', symbol)
    candle_current = get_candle('H4', 'ahora', symbol)
    
    if candle_1am and candle_current:
        high_1am = candle_1am['high']
        low_1am = candle_1am['low']
        current_price = candle_current['close']
        
        if current_price > high_1am:
            return 'BREAKOUT_UP'
        elif current_price < low_1am:
            return 'BREAKOUT_DOWN'
    
    return None
```

### 3. Análisis de volumen y precio

```python
def analyze_volume_price(symbol):
    """Analiza relación volumen-precio"""
    candle = get_candle('H4', '1am', symbol)
    
    if candle:
        # Vela con alto volumen y movimiento fuerte
        if candle['volume'] > 10000 and candle['body_size'] > 0.0005:
            if candle['is_bullish']:
                return 'STRONG_BUY'
            else:
                return 'STRONG_SELL'
    
    return None
```

### 4. Comparación de velas consecutivas

```python
def compare_consecutive_candles(symbol):
    """Compara velas de diferentes horarios"""
    candle_1am = get_candle('H4', '1am', symbol)
    candle_5am = get_candle('H4', '5am', symbol)
    candle_9am = get_candle('H4', '9am', symbol)
    
    if all([candle_1am, candle_5am, candle_9am]):
        # Verificar si hay progresión alcista
        if (candle_1am['close'] < candle_5am['close'] < candle_9am['close']):
            return 'UPTREND'
        # Verificar si hay progresión bajista
        elif (candle_1am['close'] > candle_5am['close'] > candle_9am['close']):
            return 'DOWNTREND'
    
    return None
```

---

## ⚠️ Manejo de Errores

Siempre verifica que la vela existe antes de usarla:

```python
candle = get_candle('H4', '1am', 'EURUSD')

if candle:
    # Usar los datos de la vela
    price = candle['close']
    # ... tu lógica aquí
else:
    # Manejar el caso de error
    print("No se pudo obtener la vela")
    return None
```

---

## 🎯 Mejores Prácticas

1. **Siempre verifica None**: La función puede retornar `None` si no encuentra la vela
2. **Usa instancias para múltiples consultas**: Más eficiente que llamar la función global repetidamente
3. **Combina con análisis técnico**: Usa `get_candle()` junto con indicadores técnicos
4. **Considera el contexto**: Las velas deben analizarse en conjunto, no de forma aislada
5. **Maneja zonas horarias**: Recuerda que las horas se interpretan en horario NY

---

## 📚 Referencia Rápida

### Temporalidades disponibles:
- `'M1'` - 1 minuto
- `'M5'` - 5 minutos
- `'M15'` - 15 minutos
- `'M30'` - 30 minutos
- `'H1'` - 1 hora
- `'H4'` - 4 horas
- `'D1'` - 1 día
- `'W1'` - 1 semana
- `'MN1'` - 1 mes

### Formatos de hora aceptados:
- `'ahora'`, `'actual'` - Vela actual
- `'1am'`, `'5am'`, `'9am'` - Formato 12h
- `'1pm'`, `'5pm'`, `'9pm'` - Formato 12h
- `'13:00'`, `'9:00'` - Formato 24h

---

## 🔗 Integración con Estrategias

Para usar en tus estrategias, simplemente importa y usa:

```python
from candle_reader import get_candle
from strategies import BaseStrategy

class TuEstrategia(BaseStrategy):
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        # Tu lógica usando get_candle()
        candle = get_candle('H4', '1am', symbol)
        
        if candle and candle['is_bullish']:
            # Generar señal
            return self._create_signal('BUY', symbol, rates[-1]['close'])
        
        return None
```

---

## 📞 Soporte

Para problemas o preguntas sobre el uso de `get_candle()`, revisa:
- Los logs del bot en `trading_bot.log`
- La implementación en `candle_reader.py`
- Los ejemplos en `example_candle_usage.py`

---

**Última actualización**: Diciembre 2025

