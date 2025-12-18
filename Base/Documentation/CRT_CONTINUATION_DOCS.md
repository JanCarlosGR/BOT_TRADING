# Documentación: CRT de Continuación - Estrategia Completa

## 📖 Introducción

El **CRT de Continuación** es una estrategia de trading que detecta patrones de continuación de tendencia en temporalidad H4, utilizando las velas de **1 AM** y **5 AM** (hora NY) para identificar barridos de liquidez con el **cuerpo de la vela** que indican continuación en lugar de reversión.

Esta estrategia combina:
- **Detección de CRT de Continuación en H4**: Identifica cuando el cuerpo de la vela de 5 AM barre extremos de la vela de 1 AM y cierra fuera del rango
- **Entrada por FVG**: Utiliza Fair Value Gaps (FVG) en temporalidades menores (M1, M5, M15, etc.) para entradas precisas
- **Gestión de riesgo**: Risk/Reward mínimo configurable, límites de trades diarios, y cálculo de volumen por porcentaje de cuenta

---

## 🎯 Conceptos Clave del CRT de Continuación

### Diferencia con CRT de Reversión

**CRT de Reversión:**
- El precio barre un extremo pero **cierra dentro del rango** de la vela anterior
- Indica **reversión** hacia el extremo opuesto

**CRT de Continuación:**
- El **cuerpo de la vela** barre un extremo y **cierra fuera del rango** de la vela anterior
- Indica **continuación** en la dirección del barrido

### Velas Clave

La estrategia utiliza velas H4 en horario NY:
- **Vela 1 AM**: Vela de referencia que establece el rango y los extremos a barrer
- **Vela 5 AM**: Vela que debe barrer un extremo de la vela 1 AM **con su cuerpo** y cerrar fuera del rango
- **Vela 9 AM**: Vela donde esperamos que el precio alcance el objetivo (TP)

---

## 📊 Condiciones de Detección

### Continuación Alcista

**Condiciones obligatorias:**

1. **Barrido con cuerpo:**
   - El **cuerpo** de la vela 5 AM debe estar **completamente por encima** del HIGH de la vela 1 AM
   - Condición: `candle_5am_body_bottom > candle_1am_high`
   - Esto significa que el cuerpo (parte inferior del cuerpo) está por encima del máximo de la vela 1 AM

2. **Cierre fuera del rango:**
   - El cuerpo de la vela 5 AM debe cerrar **arriba del rango del cuerpo** de la vela 1 AM
   - Condición: `candle_5am_body_bottom > candle_1am_body_top`
   - Esto asegura que el cuerpo cerró completamente fuera del rango

3. **Objetivo (TP):**
   - TP = **HIGH de vela 5 AM**
   - Este es el objetivo que esperamos alcanzar durante la vela de 9 AM

**Ejemplo visual:**
```
Vela 1 AM:     HIGH = 1.11000
               [Cuerpo: 1.10800 - 1.10900]
               LOW = 1.10700

Vela 5 AM:     HIGH = 1.11150
               [Cuerpo: 1.11050 - 1.11120] ← Cuerpo barre HIGH de 1 AM
               LOW = 1.11000

✅ Detectado: Continuación Alcista
   - Cuerpo 5 AM (1.11050) > HIGH 1 AM (1.11000) ✓
   - Cuerpo 5 AM (1.11050) > Cuerpo Top 1 AM (1.10900) ✓
   - TP = HIGH 5 AM = 1.11150
```

### Continuación Bajista

**Condiciones obligatorias:**

1. **Barrido con cuerpo:**
   - El **cuerpo** de la vela 5 AM debe estar **completamente por debajo** del LOW de la vela 1 AM
   - Condición: `candle_5am_body_top < candle_1am_low`
   - Esto significa que el cuerpo (parte superior del cuerpo) está por debajo del mínimo de la vela 1 AM

2. **Cierre fuera del rango:**
   - El cuerpo de la vela 5 AM debe cerrar **abajo del rango del cuerpo** de la vela 1 AM
   - Condición: `candle_5am_body_top < candle_1am_body_bottom`
   - Esto asegura que el cuerpo cerró completamente fuera del rango

3. **Objetivo (TP):**
   - TP = **LOW de vela 5 AM**
   - Este es el objetivo que esperamos alcanzar durante la vela de 9 AM

**Ejemplo visual:**
```
Vela 1 AM:     HIGH = 1.11000
               [Cuerpo: 1.10800 - 1.10900]
               LOW = 1.10700

Vela 5 AM:     HIGH = 1.10800
               [Cuerpo: 1.10650 - 1.10720] ← Cuerpo barre LOW de 1 AM
               LOW = 1.10600

✅ Detectado: Continuación Bajista
   - Cuerpo 5 AM (1.10720) < LOW 1 AM (1.10700) ✓
   - Cuerpo 5 AM (1.10720) < Cuerpo Bottom 1 AM (1.10800) ✓
   - TP = LOW 5 AM = 1.10600
```

---

## 🔍 Detector: `Base/crt_continuation_detector.py`

### Clase: `CRTContinuationDetector`

**Función principal:** `detect_continuation_crt(symbol: str)`

**Proceso de detección:**

1. **Obtener velas H4:**
   ```python
   candle_1am = get_candle('H4', '1am', symbol)
   candle_5am = get_candle('H4', '5am', symbol)
   candle_9am = get_candle('H4', '9am', symbol)  # Opcional, puede estar en formación
   ```

2. **Calcular rangos de cuerpos:**
   ```python
   # Vela 1 AM
   candle_1am_body_top = max(candle_1am_open, candle_1am_close)
   candle_1am_body_bottom = min(candle_1am_open, candle_1am_close)
   
   # Vela 5 AM
   candle_5am_body_top = max(candle_5am_open, candle_5am_close)
   candle_5am_body_bottom = min(candle_5am_open, candle_5am_close)
   ```

3. **Validar Continuación Alcista:**
   ```python
   if candle_5am_body_bottom > candle_1am_high:  # Cuerpo barre HIGH
       if candle_5am_body_bottom > candle_1am_body_top:  # Cuerpo cierra fuera
           # ✅ Continuación Alcista detectada
           target_price = candle_5am_high  # TP
   ```

4. **Validar Continuación Bajista:**
   ```python
   if candle_5am_body_top < candle_1am_low:  # Cuerpo barre LOW
       if candle_5am_body_top < candle_1am_body_bottom:  # Cuerpo cierra fuera
           # ✅ Continuación Bajista detectada
           target_price = candle_5am_low  # TP
   ```

**Retorno del detector:**

```python
{
    'detected': True,
    'sweep_type': 'BULLISH_SWEEP' | 'BEARISH_SWEEP',
    'direction': 'BULLISH' | 'BEARISH',
    'target_price': float,  # TP (HIGH o LOW de vela 5 AM)
    'sweep_price': float,   # Precio barrido (HIGH o LOW de vela 1 AM)
    'candle_1am': Dict,     # Datos completos de vela 1 AM
    'candle_5am': Dict,     # Datos completos de vela 5 AM
    'candle_9am': Dict,     # Datos completos de vela 9 AM (puede ser None)
    'close_type': 'BULLISH' | 'BEARISH',
    'swept_extreme': 'high' | 'low',
    'body_outside': 'above' | 'below'
}
```

---

## 💹 Estrategia: `strategies/crt_continuation_strategy.py`

### Clase: `CRTContinuationStrategy`

La estrategia implementa un flujo de 4 etapas:

### Etapa 1/4: Verificación de Noticias

**Acción:**
- Verifica que no haya noticias de alto impacto 5 minutos antes/después del momento actual

**Bloqueo:**
- Si hay noticias cercanas, la estrategia no opera y espera

**Log:**
```
📰 Etapa 1/4: Verificando noticias económicas...
✅ Etapa 1/4: Noticias OK - Puede operar
```

### Etapa 2/4: Detección CRT de Continuación

**Acción:**
- Llama a `detect_crt_continuation(symbol)` para detectar el patrón en H4

**Validaciones:**
- Verifica que el CRT esté detectado (`detected == True`)
- Si no está detectado, espera y cancela monitoreo intensivo si estaba activo

**Logs detallados:**
```
======================================================================
✅ CRT DE CONTINUACIÓN DETECTADO - Etapa 2/4 COMPLETA
======================================================================
📊 TIPO DE CRT: CONTINUACIÓN ALCISTA
📍 Detalles del Patrón:
   • Barrido: Vela 5 AM barrió HIGH de vela 1 AM
   • Precio barrido: 1.11000
   • Cierre: Cuerpo de vela 5 AM cerró ARRIBA del rango de vela 1 AM
   • Tipo de cierre: BULLISH
----------------------------------------------------------------------
🎯 OBJETIVO (TP) SEGÚN CRT:
   • Tipo: CONTINUACIÓN ALCISTA
   • Objetivo definido desde: HIGH de vela 5 AM
   • Precio objetivo (TP): 1.11150
   • Vela donde esperamos alcanzar: Vela 9 AM NY
   • Dirección esperada: BULLISH
======================================================================
```

### Etapa 3/4: Búsqueda de Entrada FVG

**Acción:**
- Busca un FVG válido en la temporalidad de entrada configurada (M1, M5, M15, etc.)

**FVG Esperado según CRT:**

| CRT Detectado | FVG Esperado |
|---------------|--------------|
| Continuación Alcista (barrió HIGH, dirección BULLISH) | FVG ALCISTA |
| Continuación Bajista (barrió LOW, dirección BEARISH) | FVG BAJISTA |

**Validaciones estrictas del FVG:**

1. **Las 3 velas forman el FVG esperado:**
   - Vela en formación (posición 0) + 2 anteriores (posición 1 y 2)
   - Deben formar el FVG del tipo esperado

2. **Vela en formación entró al FVG:**
   - **FVG BAJISTA**: HIGH de la vela debe estar dentro del FVG
   - **FVG ALCISTA**: LOW de la vela debe estar dentro del FVG

3. **Precio salió del FVG en dirección correcta:**
   - **FVG BAJISTA + dirección BEARISH**: Precio debe estar debajo del FVG
   - **FVG ALCISTA + dirección BULLISH**: Precio debe estar arriba del FVG

4. **Risk/Reward mínimo:**
   - Debe cumplir el RR configurado (default 1:2)
   - Si no cumple, intenta optimizar el SL

**Monitoreo Intensivo:**
- Si se detecta FVG esperado pero aún no cumple todas las condiciones:
  - Activa monitoreo intensivo (cada segundo)
  - Monitorea hasta que se cumplan las condiciones o expire

**Logs:**
```
🔄 FVG ESPERADO DETECTADO - ACTIVANDO MONITOREO INTENSIVO
📊 CRT DETECTADO: CONTINUACIÓN ALCISTA
🎯 OBJETIVO SEGÚN CRT: HIGH de vela 5 AM = 1.11150
📊 FVG ALCISTA detectado: 1.11000 - 1.11050
🔄 El bot ahora analizará cada SEGUNDO evaluando:
   • Si las 3 velas forman el FVG esperado
   • Si la vela EN FORMACIÓN entró al FVG
   • Si el precio actual salió del FVG en la dirección correcta
```

### Etapa 4/4: Ejecución de Orden

**Validaciones finales:**
1. Re-validar que las 3 velas forman el FVG esperado
2. Re-validar que la vela en formación entró al FVG
3. Re-validar que el precio salió del FVG en dirección correcta
4. Verificar límite de trades diarios
5. Verificar que no hay posiciones abiertas

**Cálculos:**

1. **Entry Price:**
   - Precio actual del mercado
   - BUY: ASK actual
   - SELL: BID actual

2. **Stop Loss:**
   - Basado en el FVG + margen de seguridad
   - BUY: `fvg_bottom - fvg_size - safety_margin`
   - SELL: `fvg_top + fvg_size + safety_margin`

3. **Take Profit:**
   - Objetivo del CRT (HIGH/LOW de vela 5 AM)
   - Ajustado por RR si es necesario (forzado a RR mínimo si excede máximo)

4. **Volumen:**
   - Calculado según riesgo porcentual configurado
   - Fórmula: `volume = risk_amount / risk_value_per_lot`

**Ejecución:**
- Si todas las validaciones pasan: ejecuta orden (BUY o SELL)
- Guarda en base de datos con información completa del CRT
- Muestra logs detallados

**Logs de ejecución:**
```
======================================================================
💹 EJECUTANDO ORDEN CRT DE CONTINUACIÓN
======================================================================
📊 TIPO DE CRT: CONTINUACIÓN ALCISTA
📊 Dirección: BULLISH (COMPRA)
💰 Precio de Entrada: 1.11050
🛑 Stop Loss: 1.10950 (Risk: 0.00100)
🎯 Take Profit: 1.11150 (Reward: 0.00100)
📈 Risk/Reward: 1.00:1 (mínimo requerido: 2.00:1)
📦 Volumen: 0.10 lotes (calculado por 1.0% de riesgo)
----------------------------------------------------------------------
📋 Contexto de la Señal CRT:
   • Tipo de CRT: CONTINUACIÓN ALCISTA
   • Barrido: Vela 5 AM barrió HIGH de vela 1 AM
   • Precio barrido: 1.11000
   • Cierre: Cuerpo de vela 5 AM cerró ARRIBA del rango
----------------------------------------------------------------------
🎯 OBJETIVO SEGÚN CRT DETECTADO:
   • Objetivo (TP) definido desde: HIGH de vela 5 AM
   • Precio objetivo: 1.11150
   • Vela donde esperamos alcanzar: Vela 9 AM NY
   • TP original del CRT: 1.11150
======================================================================
```

---

## ⚙️ Configuración

### Archivo: `config.yaml`

```yaml
strategy:
  name: "crt_continuation"  # Nombre de la estrategia

strategy_config:
  crt_entry_timeframe: "M5"  # Temporalidad de entrada: M1, M5, M15, M30, H1
  min_rr: 2.0                 # Risk/Reward mínimo (default: 1:2)

risk_management:
  risk_per_trade_percent: 1.0  # Riesgo por trade (% de cuenta)
  max_trades_per_day: 2        # Máximo de trades por día
  max_position_size: 0.1       # Tamaño máximo de posición (lotes)
```

### Parámetros Configurables

| Parámetro | Descripción | Valores | Default |
|-----------|-------------|---------|---------|
| `crt_entry_timeframe` | Temporalidad para buscar FVG de entrada | M1, M5, M15, M30, H1 | M5 |
| `min_rr` | Risk/Reward mínimo requerido | 1.0 - 10.0 | 2.0 |
| `risk_per_trade_percent` | Porcentaje de cuenta a arriesgar por trade | 0.1 - 5.0 | 1.0 |
| `max_trades_per_day` | Límite de trades diarios | 1 - 10 | 2 |
| `max_position_size` | Tamaño máximo de posición | 0.01 - 10.0 | 0.1 |

---

## 📈 Ejemplo de Flujo Completo

### Escenario: Continuación Alcista

**Paso 1: Detección del Patrón (H4)**

```
Vela 1 AM H4 (NY):
   Open: 1.10800
   High: 1.11000
   Low: 1.10700
   Close: 1.10900
   Cuerpo: 1.10800 - 1.10900

Vela 5 AM H4 (NY):
   Open: 1.11020
   High: 1.11150
   Low: 1.11000
   Close: 1.11120
   Cuerpo: 1.11020 - 1.11120

✅ Validación:
   - Cuerpo 5 AM bottom (1.11020) > HIGH 1 AM (1.11000) ✓
   - Cuerpo 5 AM bottom (1.11020) > Cuerpo Top 1 AM (1.10900) ✓
   - TP = HIGH 5 AM = 1.11150
```

**Paso 2: Búsqueda de FVG (M5)**

```
FVG ALCISTA detectado en M5:
   Bottom: 1.11000
   Top: 1.11050
   Estado: VALIDADO
   Entró: True
   Salió: True
   Exit Direction: ALCISTA

✅ Validación:
   - 3 velas forman FVG ALCISTA ✓
   - Vela en formación entró al FVG (LOW dentro) ✓
   - Precio salió arriba del FVG (1.11060 > 1.11050) ✓
```

**Paso 3: Cálculo de Niveles**

```
Entry Price: 1.11060 (ASK actual)
Stop Loss: 1.10950 (FVG bottom - margen)
Take Profit: 1.11150 (TP del CRT)
Risk: 0.00110
Reward: 0.00090
RR: 0.82:1

⚠️ RR insuficiente, optimizando SL...
SL optimizado: 1.10920
Nuevo Risk: 0.00140
Nuevo RR: 0.64:1

❌ RR aún insuficiente, esperando mejor entrada...
```

**Paso 4: Ejecución (cuando RR es válido)**

```
Entry Price: 1.11050 (ASK actual)
Stop Loss: 1.10900 (FVG bottom - margen)
Take Profit: 1.11150 (TP del CRT)
Risk: 0.00150
Reward: 0.00100
RR: 0.67:1

⚠️ RR aún bajo, forzando RR mínimo...
TP ajustado: 1.11350 (para RR 2:1)
Nuevo Reward: 0.00300
Nuevo RR: 2.00:1 ✓

✅ Orden ejecutada:
   Ticket: 123456
   Tipo: BUY
   Volumen: 0.10 lotes
   Entry: 1.11050
   SL: 1.10900
   TP: 1.11350 (ajustado por RR)
```

---

## 🔧 Funciones Clave

### `detect_crt_continuation(symbol: str)`

Función de conveniencia que crea una instancia del detector y ejecuta la detección.

**Uso:**
```python
from Base.crt_continuation_detector import detect_crt_continuation

result = detect_crt_continuation('EURUSD')
if result and result.get('detected'):
    print(f"CRT detectado: {result['direction']}")
    print(f"TP: {result['target_price']}")
```

### `CRTContinuationStrategy.analyze(symbol, rates)`

Método principal de análisis de la estrategia. Se llama automáticamente por el bot.

**Flujo interno:**
1. Verifica límite de trades
2. Verifica noticias
3. Detecta CRT de Continuación
4. Busca entrada FVG
5. Ejecuta orden si todas las condiciones se cumplen

---

## 📝 Notas Importantes

### Sobre el Barrido con Cuerpo

**⚠️ CRÍTICO:** El barrido debe hacerse con el **cuerpo de la vela**, no solo con el extremo (mecha).

- ✅ **Correcto:** El cuerpo (parte inferior para alcista, parte superior para bajista) está completamente por encima/debajo del extremo
- ❌ **Incorrecto:** Solo el HIGH/LOW de la vela toca el extremo pero el cuerpo no lo barre

### Sobre el Objetivo (TP)

- El TP se **define desde la vela de 5 AM** (HIGH para alcista, LOW para bajista)
- Esperamos que el precio **alcance ese objetivo durante la vela de 9 AM**
- El TP puede ser **ajustado por RR** si no cumple el Risk/Reward mínimo configurado

### Sobre el Monitoreo Intensivo

- Se activa cuando se detecta CRT pero el FVG aún no cumple todas las condiciones
- Monitorea **cada segundo** hasta que se cumplan las condiciones o expire
- Se cancela automáticamente si el CRT desaparece o el FVG cambia

### Sobre las Validaciones

- La estrategia tiene **validaciones estrictas** en múltiples puntos
- Si alguna validación falla, la orden **NO se ejecuta**
- Esto asegura que solo se operen setups de alta calidad

---

## 🔗 Referencias

- **Teoría CRT General:** Ver [CRT_THEORY_DOCS.md](./CRT_THEORY_DOCS.md)
- **Detector FVG:** Ver [FVG_DETECTOR_DOCS.md](./FVG_DETECTOR_DOCS.md)
- **Estrategia Turtle Soup FVG:** Similar estructura, diferente detección de patrón

---

## 📊 Resumen de Condiciones

### Continuación Alcista

| Condición | Validación |
|-----------|------------|
| Cuerpo barre HIGH | `candle_5am_body_bottom > candle_1am_high` |
| Cuerpo cierra fuera | `candle_5am_body_bottom > candle_1am_body_top` |
| TP | `HIGH de vela 5 AM` |
| FVG esperado | `FVG ALCISTA` |
| Dirección orden | `BUY` |

### Continuación Bajista

| Condición | Validación |
|-----------|------------|
| Cuerpo barre LOW | `candle_5am_body_top < candle_1am_low` |
| Cuerpo cierra fuera | `candle_5am_body_top < candle_1am_body_bottom` |
| TP | `LOW de vela 5 AM` |
| FVG esperado | `FVG BAJISTA` |
| Dirección orden | `SELL` |

---

**Última actualización:** 2024
**Versión:** 1.0
