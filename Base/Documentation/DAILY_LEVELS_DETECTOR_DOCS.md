# Documentación: Detector de Niveles Diarios (Previous Daily High/Low)

## 📖 Introducción

El detector de niveles diarios identifica cuando el precio actual está tomando (alcanzando) los altos (HIGH) o bajos (LOW) diarios de días anteriores. Esta funcionalidad es esencial para identificar niveles de liquidez y zonas de interés en trading ICT/SMC (Smart Money Concepts).

**Característica clave**: Detecta la toma del nivel incluso si es por solo 1 pip, lo que permite identificar con precisión cuando el precio "barre" o "toma" un nivel diario previo.

---

## 🚀 Uso Básico

### Importar las funciones

```python
from Base.daily_levels_detector import (
    get_previous_daily_levels,
    detect_daily_level_touch,
    detect_daily_high_take,
    detect_daily_low_take,
    get_yesterday_levels
)
```

### Funciones principales

1. **`get_previous_daily_levels()`** - Obtiene los HIGHs y LOWs de días anteriores
2. **`detect_daily_level_touch()`** - Detecta si el precio está tocando algún nivel diario
3. **`detect_daily_high_take()`** - Detecta específicamente la toma de un Daily High
4. **`detect_daily_low_take()`** - Detecta específicamente la toma de un Daily Low
5. **`get_yesterday_levels()`** - Obtiene los niveles de ayer (día anterior)

---

## 📊 Funciones Detalladas

### 1. `get_previous_daily_levels()`

Obtiene los niveles HIGH y LOW de los días anteriores.

#### Sintaxis

```python
levels = get_previous_daily_levels(symbol, lookback_days=5)
```

#### Parámetros

- **`symbol`** (str): Símbolo a analizar (ej: `'EURUSD'`, `'GBPUSD'`)
- **`lookback_days`** (int): Número de días anteriores a revisar (default: `5`)

#### Retorno

Retorna un diccionario (`Dict`) con información de niveles diarios o `None` si hay error.

#### Estructura de Datos

```python
{
    'previous_highs': List[Dict],  # Lista de HIGHs de días anteriores
    'previous_lows': List[Dict],    # Lista de LOWs de días anteriores
    'highest_high': float,          # El HIGH más alto de los días revisados
    'lowest_low': float,            # El LOW más bajo de los días revisados
    'highest_high_date': date,      # Fecha del HIGH más alto
    'lowest_low_date': date,        # Fecha del LOW más bajo
    'lookback_days': int            # Número de días revisados
}
```

Cada elemento en `previous_highs` y `previous_lows` tiene:

```python
{
    'date': date,      # Fecha del día
    'high': float,     # Precio HIGH (solo en previous_highs)
    'low': float,      # Precio LOW (solo en previous_lows)
    'time': datetime   # Timestamp de la vela
}
```

---

### 2. `detect_daily_level_touch()`

Detecta si el precio actual está tocando o alcanzando un nivel diario previo.

**IMPORTANTE**: Detecta incluso si el precio toma el nivel por solo 1 pip.

#### Sintaxis

```python
touch_info = detect_daily_level_touch(symbol, lookback_days=5, tolerance_pips=1.0)
```

#### Parámetros

- **`symbol`** (str): Símbolo a analizar
- **`lookback_days`** (int): Número de días anteriores a revisar (default: `5`)
- **`tolerance_pips`** (float): Tolerancia en pips para considerar que el precio "tocó" el nivel (default: `1.0`)
  - Para HIGH: precio >= (high - tolerance) → El precio alcanzó o superó el HIGH
  - Para LOW: precio <= (low + tolerance) → El precio alcanzó o cayó por debajo del LOW

#### Retorno

Retorna un diccionario (`Dict`) con información del nivel tocado o `None` si no hay toque.

#### Estructura de Datos

```python
{
    'level_touched': bool,          # True si se tocó algún nivel
    'level_type': str,              # 'HIGH' o 'LOW' o None
    'level_price': float,           # Precio del nivel tocado
    'level_date': date,             # Fecha del día del nivel
    'current_price': float,         # Precio actual (bid)
    'distance_pips': float,         # Distancia en pips desde el nivel
    'is_taking': bool,              # True si el precio está "tomando" el nivel
    'has_taken': bool,              # True si el precio ya tomó el nivel (lo alcanzó o superó)
    'previous_highs': List[Dict],   # Lista de HIGHs revisados
    'previous_lows': List[Dict],    # Lista de LOWs revisados
    'highest_high': float,          # El HIGH más alto de los días revisados
    'lowest_low': float,            # El LOW más bajo de los días revisados
    'highest_high_date': date,      # Fecha del HIGH más alto
    'lowest_low_date': date         # Fecha del LOW más bajo
}
```

---

### 3. `detect_daily_high_take()`

Detecta específicamente si el precio está tomando un HIGH diario previo.

**IMPORTANTE**: Detecta incluso si el precio toma el HIGH por solo 1 pip.

#### Sintaxis

```python
high_take = detect_daily_high_take(symbol, lookback_days=5, tolerance_pips=1.0)
```

#### Parámetros

- **`symbol`** (str): Símbolo a analizar
- **`lookback_days`** (int): Número de días anteriores a revisar (default: `5`)
- **`tolerance_pips`** (float): Tolerancia en pips (default: `1.0`)

#### Retorno

Retorna un diccionario (`Dict`) con información del HIGH tomado o `None` si no hay toma de HIGH.

#### Estructura de Datos

Misma estructura que `detect_daily_level_touch()`, pero solo retorna cuando `level_type == 'HIGH'` y `is_taking == True`.

---

### 4. `detect_daily_low_take()`

Detecta específicamente si el precio está tomando un LOW diario previo.

**IMPORTANTE**: Detecta incluso si el precio toma el LOW por solo 1 pip.

#### Sintaxis

```python
low_take = detect_daily_low_take(symbol, lookback_days=5, tolerance_pips=1.0)
```

#### Parámetros

- **`symbol`** (str): Símbolo a analizar
- **`lookback_days`** (int): Número de días anteriores a revisar (default: `5`)
- **`tolerance_pips`** (float): Tolerancia en pips (default: `1.0`)

#### Retorno

Retorna un diccionario (`Dict`) con información del LOW tomado o `None` si no hay toma de LOW.

#### Estructura de Datos

Misma estructura que `detect_daily_level_touch()`, pero solo retorna cuando `level_type == 'LOW'` y `is_taking == True`.

---

### 5. `get_yesterday_levels()`

Obtiene los niveles HIGH y LOW del día anterior (ayer).

#### Sintaxis

```python
yesterday = get_yesterday_levels(symbol)
```

#### Parámetros

- **`symbol`** (str): Símbolo a analizar

#### Retorno

Retorna un diccionario (`Dict`) con información de ayer o `None` si hay error.

#### Estructura de Datos

```python
{
    'date': date,        # Fecha de ayer
    'high': float,       # HIGH de ayer
    'low': float,        # LOW de ayer
    'open': float,       # OPEN de ayer
    'close': float,      # CLOSE de ayer
    'time': datetime     # Timestamp de la vela
}
```

---

## 💡 Ejemplos de Uso

### Ejemplo 1: Obtener niveles previos

```python
from Base.daily_levels_detector import get_previous_daily_levels

# Obtener niveles de los últimos 5 días
levels = get_previous_daily_levels('EURUSD', lookback_days=5)

if levels:
    print(f"Highest High: {levels['highest_high']:.5f} ({levels['highest_high_date']})")
    print(f"Lowest Low: {levels['lowest_low']:.5f} ({levels['lowest_low_date']})")
    
    print("\nPrevious Highs:")
    for high_item in levels['previous_highs']:
        print(f"  - {high_item['date']}: {high_item['high']:.5f}")
    
    print("\nPrevious Lows:")
    for low_item in levels['previous_lows']:
        print(f"  - {low_item['date']}: {low_item['low']:.5f}")
```

### Ejemplo 2: Detectar toque de nivel diario

```python
from Base.daily_levels_detector import detect_daily_level_touch

# Detectar si el precio está tocando algún nivel diario
touch_info = detect_daily_level_touch('EURUSD', lookback_days=5, tolerance_pips=1.0)

if touch_info and touch_info['level_touched']:
    print(f"Nivel {touch_info['level_type']} tocado:")
    print(f"  - Precio del nivel: {touch_info['level_price']:.5f}")
    print(f"  - Fecha: {touch_info['level_date']}")
    print(f"  - Precio actual: {touch_info['current_price']:.5f}")
    print(f"  - Distancia: {touch_info['distance_pips']:.1f} pips")
    print(f"  - Está tomando: {touch_info['is_taking']}")
    print(f"  - Ya tomó: {touch_info['has_taken']}")
else:
    print("No se detectó toque de nivel diario")
```

### Ejemplo 3: Detectar toma específica de Daily High

```python
from Base.daily_levels_detector import detect_daily_high_take

# Detectar si el precio está tomando un Daily High
high_take = detect_daily_high_take('EURUSD', lookback_days=5, tolerance_pips=1.0)

if high_take:
    print(f"Daily High TOMADO:")
    print(f"  - High tomado: {high_take['level_price']:.5f} ({high_take['level_date']})")
    print(f"  - Precio actual: {high_take['current_price']:.5f}")
    print(f"  - Distancia: {high_take['distance_pips']:.1f} pips")
    
    if high_take['has_taken']:
        print("  - El precio YA SUPERÓ el HIGH")
    else:
        print("  - El precio está cerca del HIGH (dentro de tolerancia)")
else:
    print("No se detectó toma de Daily High")
```

### Ejemplo 4: Detectar toma específica de Daily Low

```python
from Base.daily_levels_detector import detect_daily_low_take

# Detectar si el precio está tomando un Daily Low
low_take = detect_daily_low_take('EURUSD', lookback_days=5, tolerance_pips=1.0)

if low_take:
    print(f"Daily Low TOMADO:")
    print(f"  - Low tomado: {low_take['level_price']:.5f} ({low_take['level_date']})")
    print(f"  - Precio actual: {low_take['current_price']:.5f}")
    print(f"  - Distancia: {low_take['distance_pips']:.1f} pips")
    
    if low_take['has_taken']:
        print("  - El precio YA CAYÓ por debajo del LOW")
    else:
        print("  - El precio está cerca del LOW (dentro de tolerancia)")
else:
    print("No se detectó toma de Daily Low")
```

### Ejemplo 5: Obtener niveles de ayer

```python
from Base.daily_levels_detector import get_yesterday_levels

# Obtener niveles de ayer
yesterday = get_yesterday_levels('EURUSD')

if yesterday:
    print(f"Niveles de ayer ({yesterday['date']}):")
    print(f"  - High: {yesterday['high']:.5f}")
    print(f"  - Low: {yesterday['low']:.5f}")
    print(f"  - Open: {yesterday['open']:.5f}")
    print(f"  - Close: {yesterday['close']:.5f}")
```

### Ejemplo 6: Usar en una estrategia

```python
from Base.daily_levels_detector import detect_daily_high_take, detect_daily_low_take
from strategies import BaseStrategy
import numpy as np
from typing import Optional, Dict

class DailyLevelsStrategy(BaseStrategy):
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        # Detectar toma de Daily High
        high_take = detect_daily_high_take(symbol, lookback_days=5, tolerance_pips=1.0)
        
        if high_take and high_take['has_taken']:
            # Señal de venta: El precio tomó un Daily High (liquidity sweep)
            current_price = rates[-1]['close']
            return self._create_signal(
                'SELL',
                symbol,
                current_price,
                stop_loss=high_take['level_price'] + 0.0010,  # SL por encima del HIGH
                take_profit=current_price - (current_price - high_take['level_price']) * 2
            )
        
        # Detectar toma de Daily Low
        low_take = detect_daily_low_take(symbol, lookback_days=5, tolerance_pips=1.0)
        
        if low_take and low_take['has_taken']:
            # Señal de compra: El precio tomó un Daily Low (liquidity sweep)
            current_price = rates[-1]['close']
            return self._create_signal(
                'BUY',
                symbol,
                current_price,
                stop_loss=low_take['level_price'] - 0.0010,  # SL por debajo del LOW
                take_profit=current_price + (low_take['level_price'] - current_price) * 2
            )
        
        return None
```

### Ejemplo 7: Monitoreo continuo de niveles

```python
import time
from Base.daily_levels_detector import detect_daily_level_touch
from datetime import datetime

def monitor_daily_levels(symbol, lookback_days=5, interval=60):
    """Monitorea niveles diarios cada X segundos"""
    previous_take = None
    
    while True:
        touch_info = detect_daily_level_touch(symbol, lookback_days, tolerance_pips=1.0)
        
        if touch_info and touch_info['level_touched']:
            # Solo mostrar si cambió el nivel tomado
            current_take = f"{touch_info['level_type']}_{touch_info['level_date']}"
            
            if current_take != previous_take:
                print(f"\n[{datetime.now()}] Nivel diario detectado:")
                print(f"  Tipo: {touch_info['level_type']}")
                print(f"  Precio del nivel: {touch_info['level_price']:.5f}")
                print(f"  Fecha: {touch_info['level_date']}")
                print(f"  Precio actual: {touch_info['current_price']:.5f}")
                print(f"  Distancia: {touch_info['distance_pips']:.1f} pips")
                
                if touch_info['has_taken']:
                    print(f"  ✅ El precio YA TOMÓ el nivel")
                else:
                    print(f"  ⏳ El precio está cerca del nivel (dentro de tolerancia)")
                
                previous_take = current_take
        
        time.sleep(interval)

# Usar
# monitor_daily_levels('EURUSD', lookback_days=5, interval=60)  # Monitorear cada 60 segundos
```

### Ejemplo 8: Validar si hoy barrió niveles previos

```python
from Base.daily_levels_detector import get_previous_daily_levels, get_yesterday_levels
import MetaTrader5 as mt5
from datetime import date

def check_today_swept_levels(symbol='EURUSD', lookback_days=5):
    """Valida si el día de hoy barrió algún Previous Daily High o Low"""
    
    # Inicializar MT5
    if not mt5.initialize():
        print(f"Error al inicializar MT5")
        return
    
    try:
        # Obtener niveles previos
        levels = get_previous_daily_levels(symbol, lookback_days)
        if not levels:
            print("No se pudieron obtener niveles")
            return
        
        # Obtener vela diaria de HOY
        today_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 1)
        if today_rates is None or len(today_rates) == 0:
            print("No se pudo obtener vela de hoy")
            return
        
        today_candle = today_rates[0]
        today_high = float(today_candle['high'])
        today_low = float(today_candle['low'])
        
        # Verificar si HOY barrió algún HIGH previo
        swept_highs = []
        for high_item in levels['previous_highs']:
            if today_high >= high_item['high']:  # Incluso si es igual (dentro de 1 pip)
                swept_highs.append(high_item)
        
        # Verificar si HOY barrió algún LOW previo
        swept_lows = []
        for low_item in levels['previous_lows']:
            if today_low <= low_item['low']:  # Incluso si es igual (dentro de 1 pip)
                swept_lows.append(low_item)
        
        # Mostrar resultados
        print(f"\nValidación para {date.today()}:")
        if swept_highs:
            print(f"✅ HIGHs barridos: {len(swept_highs)}")
            for sh in swept_highs:
                print(f"   - {sh['date']}: {sh['high']:.5f} (barrido por {today_high:.5f})")
        else:
            print(f"⏸️  No se barrieron HIGHs previos")
        
        if swept_lows:
            print(f"✅ LOWs barridos: {len(swept_lows)}")
            for sl in swept_lows:
                print(f"   - {sl['date']}: {sl['low']:.5f} (barrido por {today_low:.5f})")
        else:
            print(f"⏸️  No se barrieron LOWs previos")
        
    finally:
        mt5.shutdown()

# Usar
# check_today_swept_levels('EURUSD', lookback_days=5)
```

---

## 🔍 Cómo Funciona

### Detección de Toma de Nivel

El detector identifica cuando el precio "toma" un nivel diario previo usando las siguientes reglas:

1. **Para Daily High (PDH)**:
   - Un HIGH se considera "tomado" si: `current_price >= (high_price - tolerance)`
   - Esto significa que el precio alcanzó o superó el HIGH (incluso por 1 pip)
   - `has_taken = True` cuando `current_price >= high_price` (superó el HIGH)

2. **Para Daily Low (PDL)**:
   - Un LOW se considera "tomado" si: `current_price <= (low_price + tolerance)`
   - Esto significa que el precio alcanzó o cayó por debajo del LOW (incluso por 1 pip)
   - `has_taken = True` cuando `current_price <= low_price` (cayó por debajo del LOW)

### Tolerancia de 1 Pip

La tolerancia por defecto es de **1 pip** (`tolerance_pips=1.0`), lo que significa:

- **HIGH**: Si el precio está a 1 pip o menos por debajo del HIGH, se considera que está "tomando" el nivel
- **LOW**: Si el precio está a 1 pip o menos por encima del LOW, se considera que está "tomando" el nivel

Esto permite detectar la toma del nivel incluso si es por una diferencia mínima.

### Prioridad de Niveles

Si múltiples niveles están siendo tomados simultáneamente, el detector prioriza el nivel que está más cerca del precio exacto del nivel (menor distancia en pips).

---

## 📝 Estados y Flags

### `is_taking` vs `has_taken`

- **`is_taking`** (bool): `True` si el precio está dentro de la tolerancia del nivel (puede estar cerca o ya haberlo tomado)
- **`has_taken`** (bool): `True` si el precio realmente alcanzó o superó el nivel exacto
  - Para HIGH: `current_price >= level_price`
  - Para LOW: `current_price <= level_price`

### Ejemplos de Estados

1. **Precio cerca del HIGH (dentro de 1 pip)**:
   - `is_taking = True`
   - `has_taken = False`
   - `distance_pips = -0.5` (0.5 pips por debajo del HIGH)

2. **Precio superó el HIGH**:
   - `is_taking = True`
   - `has_taken = True`
   - `distance_pips = +2.0` (2 pips por encima del HIGH)

3. **Precio cerca del LOW (dentro de 1 pip)**:
   - `is_taking = True`
   - `has_taken = False`
   - `distance_pips = +0.5` (0.5 pips por encima del LOW)

4. **Precio cayó por debajo del LOW**:
   - `is_taking = True`
   - `has_taken = True`
   - `distance_pips = -2.0` (2 pips por debajo del LOW)

---

## ⚠️ Consideraciones Importantes

1. **Detección precisa**: El detector detecta la toma incluso si es por solo 1 pip, lo que es crucial para identificar liquidity sweeps
2. **Tolerancia configurable**: Puedes ajustar `tolerance_pips` según tus necesidades (default: 1.0)
3. **Precio actual**: Usa el precio `bid` actual para determinar si el nivel fue tomado
4. **Lookback configurable**: Puedes ajustar `lookback_days` para revisar más o menos días anteriores (default: 5)
5. **Timezone**: El detector usa la zona horaria "America/New_York" por defecto para determinar días
6. **Velas D1**: El detector trabaja con velas diarias (D1) de MetaTrader 5
7. **Múltiples niveles**: Si hay múltiples niveles siendo tomados, se prioriza el más cercano al precio exacto del nivel

---

## 🎯 Casos de Uso Comunes

### 1. Detectar Liquidity Sweep

```python
from Base.daily_levels_detector import detect_daily_high_take, detect_daily_low_take

# Detectar si el precio barrió un Daily High (liquidity sweep alcista)
high_take = detect_daily_high_take('EURUSD', lookback_days=5, tolerance_pips=1.0)

if high_take and high_take['has_taken']:
    print(f"Liquidity sweep detectado: HIGH de {high_take['level_date']} fue barrido")
    print(f"Señal potencial de reversión bajista")
```

### 2. Identificar Zonas de Interés

```python
from Base.daily_levels_detector import get_previous_daily_levels

levels = get_previous_daily_levels('EURUSD', lookback_days=5)

if levels:
    print(f"Zona de resistencia: {levels['highest_high']:.5f}")
    print(f"Zona de soporte: {levels['lowest_low']:.5f}")
```

### 3. Validar Setup de Trading

```python
from Base.daily_levels_detector import detect_daily_level_touch

# Verificar si el precio está cerca de un nivel diario antes de entrar
touch_info = detect_daily_level_touch('EURUSD', lookback_days=5, tolerance_pips=5.0)

if touch_info and touch_info['level_touched']:
    if touch_info['level_type'] == 'HIGH' and not touch_info['has_taken']:
        print("Precio cerca de Daily High - Posible resistencia")
    elif touch_info['level_type'] == 'LOW' and not touch_info['has_taken']:
        print("Precio cerca de Daily Low - Posible soporte")
```

### 4. Análisis de Ayer

```python
from Base.daily_levels_detector import get_yesterday_levels

yesterday = get_yesterday_levels('EURUSD')

if yesterday:
    print(f"Ayer ({yesterday['date']}):")
    print(f"  Range: {yesterday['low']:.5f} - {yesterday['high']:.5f}")
    print(f"  Body: {yesterday['open']:.5f} - {yesterday['close']:.5f}")
```

---

## 🔗 Integración con Estrategias

Para usar en tus estrategias:

```python
from Base.daily_levels_detector import detect_daily_high_take, detect_daily_low_take
from strategies import BaseStrategy

class DailyLevelsStrategy(BaseStrategy):
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        # Detectar toma de Daily High (liquidity sweep)
        high_take = detect_daily_high_take(symbol, lookback_days=5, tolerance_pips=1.0)
        
        if high_take and high_take['has_taken']:
            # Señal de venta: El precio barrió un Daily High
            return self._create_signal('SELL', symbol, rates[-1]['close'])
        
        # Detectar toma de Daily Low (liquidity sweep)
        low_take = detect_daily_low_take(symbol, lookback_days=5, tolerance_pips=1.0)
        
        if low_take and low_take['has_taken']:
            # Señal de compra: El precio barrió un Daily Low
            return self._create_signal('BUY', symbol, rates[-1]['close'])
        
        return None
```

---

## 📋 Resumen de Lógica

### Detección de Toma

- **Daily High tomado**: `current_price >= (high_price - tolerance)`
  - `has_taken = True` cuando `current_price >= high_price`
- **Daily Low tomado**: `current_price <= (low_price + tolerance)`
  - `has_taken = True` cuando `current_price <= low_price`

### Tolerancia

- **Default**: 1 pip (`tolerance_pips=1.0`)
- **HIGH**: Precio dentro de 1 pip por debajo del HIGH → `is_taking = True`
- **LOW**: Precio dentro de 1 pip por encima del LOW → `is_taking = True`

### Prioridad

- Si múltiples niveles están siendo tomados, se prioriza el más cercano al precio exacto del nivel

---

## 📞 Soporte

Para problemas o preguntas:
- Revisa los logs del bot
- Consulta la implementación en `Base/daily_levels_detector.py`
- Verifica que MT5 esté conectado y funcionando
- Asegúrate de tener datos históricos suficientes (al menos `lookback_days + 1` velas D1)

---

## 🔄 Changelog

### Versión 1.0 (Enero 2026)
- ✅ Detección de Previous Daily High/Low
- ✅ Detección de toma incluso por 1 pip
- ✅ Funciones para obtener niveles previos
- ✅ Funciones para detectar toque específico de HIGH o LOW
- ✅ Función para obtener niveles de ayer
- ✅ Tolerancia configurable en pips

---

**Última actualización**: Enero 2026

