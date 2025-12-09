# Documentación: Detector de FVG (Fair Value Gap)

## 📖 Introducción

El detector de FVG identifica si el precio actual está formando un Fair Value Gap (brecha de valor justo) según la metodología ICT, y analiza si el precio entró, salió, y si está llenando el FVG (parcialmente o completamente).

---

## 🚀 Uso Básico

### Importar la función

```python
from Base.fvg_detector import detect_fvg
```

### Sintaxis

```python
fvg = detect_fvg(symbol, timeframe='H4')
```

### Parámetros

- **`symbol`** (str): Símbolo a analizar (ej: `'EURUSD'`, `'GBPUSD'`)
- **`timeframe`** (str): Temporalidad para análisis (default: `'H4'`)
  - Opciones: `'M1'`, `'M5'`, `'M15'`, `'M30'`, `'H1'`, `'H4'`, `'D1'`, `'W1'`

### Retorno

Retorna un diccionario (`Dict`) con información del FVG o `None` si no hay FVG en formación.

---

## 📊 Estructura de Datos Retornada

```python
{
    'fvg_detected': True,
    'fvg_type': str,                      # 'ALCISTA' o 'BAJISTA'
    'fvg_bottom': float,                   # Precio inferior del FVG
    'fvg_top': float,                      # Precio superior del FVG
    'fvg_size': float,                     # Tamaño del FVG (top - bottom)
    'current_price': float,                # Precio actual
    'is_inside_fvg': bool,                 # True si el precio está tocando el FVG (compatibilidad)
    'price_touching_fvg': bool,            # True si el precio está tocando el FVG
    'entered_fvg': bool,                   # True si el precio entró al FVG (vela3 tocó)
    'exited_fvg': bool,                    # True si el precio salió del FVG
    'exit_direction': str,                 # 'ALCISTA' o 'BAJISTA' o None
    'status': str,                         # 'TOCANDO', 'SALIO', 'FUERA', 'LLENANDO_PARCIAL', 'LLENO_COMPLETO'
    'fvg_filling_partially': bool,         # True si está llenando parcialmente
    'fvg_filled_completely': bool,         # True si está completamente lleno
    'bottom_touched': bool,                # True si el precio tocó el bottom del FVG
    'top_touched': bool,                   # True si el precio tocó el top del FVG
    'forming_candle': dict,                # Información de la vela3 (actual) que forma el FVG
    'prev_candle': dict,                   # Vela1 (más antigua) que forma el FVG
    'next_candle': dict,                   # Vela3 (actual, mismo que forming_candle)
    'symbol': str,
    'timeframe': str,
    'timestamp': datetime
}
```

---

## 💡 Ejemplos de Uso

### Ejemplo 1: Detección básica de FVG

```python
from Base.fvg_detector import detect_fvg

# Detectar FVG en H4
fvg = detect_fvg('EURUSD', 'H4')

if fvg:
    print(f"FVG {fvg['fvg_type']} detectado")
    print(f"Rango: {fvg['fvg_bottom']:.5f} - {fvg['fvg_top']:.5f}")
    print(f"Precio actual: {fvg['current_price']:.5f}")
    print(f"Estado: {fvg['status']}")
else:
    print("No hay FVG en formación")
```

### Ejemplo 2: Análisis completo de entrada/salida

```python
fvg = detect_fvg('EURUSD', 'H4')

if fvg:
    print(f"Tipo de FVG: {fvg['fvg_type']}")
    
    # Verificar entrada (solo vela3 determina entrada)
    if fvg['entered_fvg']:
        print("✅ El precio entró al FVG (vela3 tocó el FVG)")
    else:
        print("❌ El precio no ha entrado al FVG")
    
    # Verificar salida
    if fvg['exited_fvg']:
        print(f"✅ El precio salió del FVG")
        print(f"   Dirección de salida: {fvg['exit_direction']}")
        print(f"   Estado: Entró → Salió → Actualmente FUERA")
    else:
        if fvg['price_touching_fvg']:
            print("⏳ El precio está dentro/tocando el FVG")
        else:
            print("⏳ El precio está fuera del FVG")
```

### Ejemplo 3: Análisis de llenado del FVG

```python
fvg = detect_fvg('EURUSD', 'H4')

if fvg:
    print(f"FVG {fvg['fvg_type']} detectado")
    
    # Verificar llenado
    if fvg['fvg_filled_completely']:
        print("✅ FVG COMPLETAMENTE LLENADO")
        print(f"   El precio tocó tanto el bottom como el top del FVG")
    elif fvg['fvg_filling_partially']:
        print("⏳ FVG LLENÁNDOSE PARCIALMENTE")
        if fvg['bottom_touched']:
            print(f"   ✅ Tocó el bottom: {fvg['fvg_bottom']:.5f}")
        if fvg['top_touched']:
            print(f"   ✅ Tocó el top: {fvg['fvg_top']:.5f}")
    else:
        print("❌ FVG aún no está siendo llenado")
```

### Ejemplo 4: Usar en una estrategia

```python
from Base.fvg_detector import detect_fvg
from strategies import BaseStrategy
import numpy as np
from typing import Optional, Dict

class FVGStrategy(BaseStrategy):
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        # Detectar FVG
        fvg = detect_fvg(symbol, 'H4')
        
        if not fvg:
            return None
        
        # Estrategia: Si hay FVG alcista completamente lleno y precio salió por arriba
        if fvg['fvg_type'] == 'ALCISTA' and fvg['fvg_filled_completely']:
            if fvg['exited_fvg'] and fvg['exit_direction'] == 'ALCISTA':
                # Señal de compra: FVG alcista lleno, precio salió por arriba
                current_price = rates[-1]['close']
                return self._create_signal(
                    'BUY',
                    symbol,
                    current_price,
                    stop_loss=fvg['fvg_bottom'],
                    take_profit=current_price + fvg['fvg_size'] * 2
                )
        
        # Estrategia: Si hay FVG bajista completamente lleno y precio salió por abajo
        elif fvg['fvg_type'] == 'BAJISTA' and fvg['fvg_filled_completely']:
            if fvg['exited_fvg'] and fvg['exit_direction'] == 'BAJISTA':
                # Señal de venta: FVG bajista lleno, precio salió por abajo
                current_price = rates[-1]['close']
                return self._create_signal(
                    'SELL',
                    symbol,
                    current_price,
                    stop_loss=fvg['fvg_top'],
                    take_profit=current_price - fvg['fvg_size'] * 2
                )
        
        return None
```

### Ejemplo 5: Monitoreo continuo

```python
import time
from Base.fvg_detector import detect_fvg
from datetime import datetime

def monitor_fvg(symbol, timeframe='H4', interval=60):
    """Monitorea FVG cada X segundos"""
    while True:
        fvg = detect_fvg(symbol, timeframe)
        
        if fvg:
            print(f"\n[{datetime.now()}] FVG detectado:")
            print(f"  Tipo: {fvg['fvg_type']}")
            print(f"  Estado: {fvg['status']}")
            print(f"  Precio: {fvg['current_price']:.5f}")
            
            if fvg['fvg_filled_completely']:
                print(f"  ✅ FVG completamente lleno")
            elif fvg['fvg_filling_partially']:
                print(f"  ⏳ FVG llenándose parcialmente")
            
            if fvg['exited_fvg']:
                print(f"  ⚠️ Precio salió del FVG en dirección {fvg['exit_direction']}")
        
        time.sleep(interval)

# Usar
# monitor_fvg('EURUSD', 'H4', 60)  # Monitorear cada 60 segundos
```

---

## 🔍 Cómo Funciona

### Detección de FVG

Un FVG se detecta cuando hay una brecha sin solapamiento entre la vela1 (más antigua) y la vela3 (actual):

1. **FVG Alcista**:
   - Condición: `Low vela1 < High vela3 AND Low vela3 > High vela1` (sin solapamiento)
   - Se forma entre: `HIGH de vela1` y `LOW de vela3`
   - Zona del FVG: entre `vela1.high` (bottom) y `vela3.low` (top)
   - **Se completa cuando**: `Low vela3 <= High vela1`
   - Expresión lógica: `BullishFVG_Fill = (Low_V3 <= High_V1)`

2. **FVG Bajista**:
   - Condición: `High vela1 > Low vela3 AND High vela3 < Low vela1` (sin solapamiento)
   - Se forma entre: `HIGH de vela3` y `LOW de vela1`
   - Zona del FVG: entre `vela3.high` (bottom) y `vela1.low` (top)
   - **Se completa cuando**: `High vela3 >= Low vela1`
   - Expresión lógica: `BearishFVG_Fill = (High_V3 >= Low_V1)`

**IMPORTANTE**: 
- El FVG solo se forma entre vela1 (más antigua) y vela3 (actual)
- NO se forma entre vela2 y vela3
- Debe haber una brecha real sin solapamiento (las velas no deben tocarse)

### Análisis de Entrada/Salida

1. **Entrada al FVG**:
   - **Solo la vela3 (actual) determina si entró al FVG**
   - El precio entra si:
     - El HIGH de la vela3 tocó el rango del FVG, O
     - El LOW de la vela3 tocó el rango del FVG, O
     - La vela3 cruzó o tocó el FVG
   - `entered_fvg = True` cuando la vela3 tocó el FVG

2. **Salida del FVG**:
   - El precio sale si:
     - Anteriormente entró (`entered_fvg = True`), Y
     - Ahora está fuera del rango del FVG (`price_touching_fvg = False`)
   - Dirección de salida:
     - **ALCISTA**: Precio salió por arriba (`current_price > fvg_top`)
     - **BAJISTA**: Precio salió por abajo (`current_price < fvg_bottom`)
   - `exited_fvg = True` cuando entró y luego salió

### Análisis de Llenado

1. **FVG Completamente Lleno**:
   - **FVG Alcista**: `Low vela3 <= High vela1`
     - El precio baja para llenar la brecha alcista
     - Expresión: `BullishFVG_Fill = (Low_V3 <= High_V1)`
   - **FVG Bajista**: `High vela3 >= Low vela1`
     - El precio sube para llenar la brecha bajista
     - Expresión: `BearishFVG_Fill = (High_V3 >= Low_V1)`
   - `fvg_filled_completely = True`

2. **FVG Llenándose Parcialmente**:
   - El precio entró al FVG (`entered_fvg = True`)
   - Tocó el bottom o el top (pero no ambos)
   - Pero no ha llenado completamente
   - `fvg_filling_partially = True`

3. **Tocó Bottom/Top**:
   - `bottom_touched = True`: El precio tocó el bottom del FVG
   - `top_touched = True`: El precio tocó el top del FVG

---

## 📝 Estados del FVG

- **`TOCANDO`**: El precio actual está tocando el rango del FVG
- **`SALIO`**: El precio entró y luego salió del FVG
- **`FUERA`**: El precio está fuera del FVG (no ha entrado o ya salió)
- **`LLENANDO_PARCIAL`**: El precio está llenando el FVG parcialmente
- **`LLENO_COMPLETO`**: El FVG está completamente lleno

---

## ⚠️ Consideraciones Importantes

1. **FVG en formación**: La función detecta FVGs que se están formando con la vela3 (actual)
2. **Solo vela1 y vela3**: El FVG solo se forma entre la vela más antigua (vela1) y la actual (vela3)
3. **Sin solapamiento**: Para que sea un FVG real, las velas NO deben tocarse o superponerse
4. **Entrada solo por vela3**: Solo la vela3 (actual) determina si el precio entró al FVG
5. **Completado diferente por tipo**:
   - **FVG Alcista**: Se completa cuando `Low vela3 <= High vela1` (el precio baja para llenar)
   - **FVG Bajista**: Se completa cuando `High vela3 >= Low vela1` (el precio sube para llenar)
6. **Precio actual**: Usa el precio bid actual para determinar entrada/salida
7. **Temporalidad**: Funciona con todos los timeframes: M1, M5, M15, M30, H1, H4, D1, W1

---

## 🎯 Casos de Uso Comunes

### 1. Detectar FVG y verificar si está siendo llenado

```python
from Base.fvg_detector import detect_fvg

fvg = detect_fvg('EURUSD', 'H4')

if fvg:
    print(f"FVG {fvg['fvg_type']} detectado")
    
    if fvg['fvg_filled_completely']:
        print("✅ FVG completamente lleno")
    elif fvg['fvg_filling_partially']:
        print("⏳ FVG llenándose parcialmente")
    else:
        print("❌ FVG aún no está siendo llenado")
```

### 2. Señal cuando el precio sale del FVG después de llenarlo

```python
from Base.fvg_detector import detect_fvg

fvg = detect_fvg('EURUSD', 'H4')

if fvg and fvg['fvg_filled_completely']:
    if fvg['exited_fvg']:
        if fvg['fvg_type'] == 'ALCISTA' and fvg['exit_direction'] == 'ALCISTA':
            print("Señal de compra: FVG alcista lleno, precio salió por arriba")
        elif fvg['fvg_type'] == 'BAJISTA' and fvg['exit_direction'] == 'BAJISTA':
            print("Señal de venta: FVG bajista lleno, precio salió por abajo")
```

### 3. Verificar si el precio está dentro o fuera del FVG

```python
from Base.fvg_detector import detect_fvg

fvg = detect_fvg('EURUSD', 'H1')

if fvg:
    if fvg['price_touching_fvg']:
        print(f"✅ El precio ESTÁ DENTRO del FVG")
        print(f"   Rango: [{fvg['fvg_bottom']:.5f}, {fvg['fvg_top']:.5f}]")
        print(f"   Precio: {fvg['current_price']:.5f}")
    else:
        print(f"❌ El precio ESTÁ FUERA del FVG")
        if fvg['current_price'] > fvg['fvg_top']:
            print(f"   Posición: POR ENCIMA ({fvg['current_price']:.5f} > {fvg['fvg_top']:.5f})")
        else:
            print(f"   Posición: POR DEBAJO ({fvg['current_price']:.5f} < {fvg['fvg_bottom']:.5f})")
```

### 4. Verificar si el precio entró y salió del FVG

```python
from Base.fvg_detector import detect_fvg

fvg = detect_fvg('EURUSD', 'M5')

if fvg:
    if fvg['entered_fvg'] and fvg['exited_fvg']:
        print(f"✅ El precio entró y salió del FVG")
        print(f"   Entró: vela3 tocó el FVG")
        print(f"   Salió: precio actual fuera del FVG")
        print(f"   Dirección salida: {fvg['exit_direction']}")
        print(f"   Estado actual: FUERA del FVG")
```

### 5. Análisis multi-timeframe

```python
from Base.fvg_detector import detect_fvg

# Detectar FVG en diferentes timeframes
fvg_h4 = detect_fvg('EURUSD', 'H4')
fvg_h1 = detect_fvg('EURUSD', 'H1')
fvg_m15 = detect_fvg('EURUSD', 'M15')

if fvg_h4 and fvg_h1:
    if fvg_h4['fvg_type'] == fvg_h1['fvg_type']:
        print("FVG confirmado en múltiples timeframes")
        print(f"H4: {fvg_h4['status']}")
        print(f"H1: {fvg_h1['status']}")
```

---

## 🔗 Integración con Estrategias

Para usar en tus estrategias:

```python
from Base.fvg_detector import detect_fvg
from strategies import BaseStrategy

class TuEstrategiaFVG(BaseStrategy):
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        fvg = detect_fvg(symbol, 'H4')
        
        if fvg:
            # Estrategia: FVG completamente lleno y precio salió
            if fvg['fvg_filled_completely'] and fvg['exited_fvg']:
                if fvg['exit_direction'] == 'ALCISTA':
                    return self._create_signal('BUY', symbol, rates[-1]['close'])
                elif fvg['exit_direction'] == 'BAJISTA':
                    return self._create_signal('SELL', symbol, rates[-1]['close'])
        
        return None
```

---

## 📋 Resumen de Lógica

### Formación del FVG
- **FVG Alcista**: `Low vela1 < High vela3 AND Low vela3 > High vela1` (sin solapamiento)
  - Rango: `[High vela1, Low vela3]`
- **FVG Bajista**: `High vela1 > Low vela3 AND High vela3 < Low vela1` (sin solapamiento)
  - Rango: `[High vela3, Low vela1]`

### Completado del FVG
- **FVG Alcista**: `Low vela3 <= High vela1` (BullishFVG_Fill = (Low_V3 <= High_V1))
- **FVG Bajista**: `High vela3 >= Low vela1` (BearishFVG_Fill = (High_V3 >= Low_V1))

### Entrada al FVG
- **Solo vela3**: Si el HIGH o LOW de la vela3 tocó el FVG → `entered_fvg = True`

### Salida del FVG
- Si `entered_fvg = True` y `price_touching_fvg = False` → `exited_fvg = True`

---

## 📞 Soporte

Para problemas o preguntas:
- Revisa los logs del bot
- Consulta la implementación en `Base/fvg_detector.py`
- Verifica que MT5 esté conectado y funcionando

---

**Última actualización**: Diciembre 2025
