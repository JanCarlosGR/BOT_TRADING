# Documentación: CRT de Revisión - Estrategia Completa

## 📖 Introducción

El **CRT de Revisión** es una estrategia de trading que detecta patrones de **reversión** en temporalidad H4, utilizando las velas de **1 AM** y **5 AM** (hora NY) para identificar barridos de liquidez donde el precio barre un extremo pero el **cuerpo de la vela cierra dentro del rango completo**, indicando una reversión hacia el extremo opuesto.

Esta estrategia combina:
- **Detección de CRT de Revisión en H4**: Identifica cuando la vela 5 AM barre un extremo de la vela 1 AM pero su cuerpo cierra dentro del rango completo
- **Entrada por FVG**: Utiliza Fair Value Gaps (FVG) en temporalidades menores (M1, M5, M15, etc.) para entradas precisas
- **Gestión de riesgo**: Risk/Reward mínimo configurable (puede ser mayor si TP lógico lo requiere), límites de trades diarios

---

## 🎯 Conceptos Clave del CRT de Revisión

### Diferencia con Otros Tipos de CRT

**CRT de Continuación:**
- Barre un extremo y el **CLOSE** está **FUERA** del rango → Continuación

**CRT de Revisión:**
- Barre un extremo pero el **CUERPO** está **DENTRO** del rango completo → Reversión

**CRT de Extremo:**
- Barre **AMBOS extremos** → Se define TP según cierre de vela 5 AM

### Velas Clave

La estrategia utiliza velas H4 en horario NY:
- **Vela 1 AM**: Vela de referencia que establece el rango y los extremos a barrer
- **Vela 5 AM**: Vela que debe barrer UN extremo de la vela 1 AM y cuyo cuerpo debe cerrar dentro del rango completo
- **Vela 9 AM**: Vela donde esperamos que el precio alcance el objetivo (TP = extremo opuesto)

---

## 📊 Condiciones de Detección

### Revisión Bajista (BULLISH_SWEEP)

**Condiciones obligatorias:**

1. **Barrido del HIGH:**
   - La vela 5 AM debe barrer el HIGH de la vela 1 AM
   - Condición: `candle_5am_high > candle_1am_high`

2. **Cuerpo dentro del rango completo:**
   - El **CUERPO** de la vela 5 AM debe cerrar **DENTRO** del rango completo (HIGH-LOW) de la vela 1 AM
   - Condiciones:
     - `candle_5am_body_bottom >= candle_1am_low`
     - `candle_5am_body_top <= candle_1am_high`
   - Esto significa que todo el cuerpo está dentro del rango completo de la vela 1 AM

3. **NO debe barrer ambos extremos:**
   - Si barre AMBOS extremos, es CRT de Extremo, no de Revisión
   - Condición: Solo debe barrer el HIGH, NO el LOW

4. **Objetivo (TP):**
   - TP = **LOW de vela 1 AM** (extremo opuesto al barrido)
   - Este es el objetivo que esperamos alcanzar durante la vela de 9 AM

**Ejemplo visual:**
```
Vela 1 AM:     HIGH = 1.11000
               [Cuerpo: 1.10800 - 1.10900]
               LOW = 1.10700
               Rango completo: 1.10700 - 1.11000

Vela 5 AM:     HIGH = 1.11050 ← Barrió HIGH de 1 AM
               [Cuerpo: 1.10850 - 1.10950] ← Cuerpo dentro del rango
               LOW = 1.10800
               
✅ Detectado: Revisión Bajista (BULLISH_SWEEP)
   - Barrió HIGH: 1.11050 > 1.11000 ✓
   - NO barrió LOW: 1.10800 > 1.10700 ✓ (solo barrió HIGH)
   - Body Bottom (1.10850) >= LOW 1 AM (1.10700) ✓
   - Body Top (1.10950) <= HIGH 1 AM (1.11000) ✓
   - TP = LOW de vela 1 AM = 1.10700
```

### Revisión Alcista (BEARISH_SWEEP)

**Condiciones obligatorias:**

1. **Barrido del LOW:**
   - La vela 5 AM debe barrer el LOW de la vela 1 AM
   - Condición: `candle_5am_low < candle_1am_low`

2. **Cuerpo dentro del rango completo:**
   - El **CUERPO** de la vela 5 AM debe cerrar **DENTRO** del rango completo (HIGH-LOW) de la vela 1 AM
   - Condiciones:
     - `candle_5am_body_bottom >= candle_1am_low`
     - `candle_5am_body_top <= candle_1am_high`

3. **NO debe barrer ambos extremos:**
   - Si barre AMBOS extremos, es CRT de Extremo, no de Revisión
   - Condición: Solo debe barrer el LOW, NO el HIGH

4. **Objetivo (TP):**
   - TP = **HIGH de vela 1 AM** (extremo opuesto al barrido)
   - Este es el objetivo que esperamos alcanzar durante la vela de 9 AM

**Ejemplo visual:**
```
Vela 1 AM:     HIGH = 1.11000
               [Cuerpo: 1.10800 - 1.10900]
               LOW = 1.10700
               Rango completo: 1.10700 - 1.11000

Vela 5 AM:     HIGH = 1.10900
               [Cuerpo: 1.10650 - 1.10750] ← Cuerpo dentro del rango
               LOW = 1.10650 ← Barrió LOW de 1 AM
               
✅ Detectado: Revisión Alcista (BEARISH_SWEEP)
   - Barrió LOW: 1.10650 < 1.10700 ✓
   - NO barrió HIGH: 1.10900 < 1.11000 ✓ (solo barrió LOW)
   - Body Bottom (1.10650) >= LOW 1 AM (1.10700) ✓
   - Body Top (1.10750) <= HIGH 1 AM (1.11000) ✓
   - TP = HIGH de vela 1 AM = 1.11000
```

---

## 🔍 Detector: `Base/crt_revision_detector.py`

### Clase: `CRTRevisionDetector`

**Función principal:** `detect_revision_crt(symbol: str)`

**Proceso de detección:**

1. **Obtener velas H4:**
   ```python
   candle_1am = get_candle('H4', '1am', symbol)
   candle_5am = get_candle('H4', '5am', symbol)
   candle_9am = get_candle('H4', '9am', symbol)  # Opcional
   ```

2. **Calcular rangos de cuerpos:**
   ```python
   candle_5am_body_bottom = min(candle_5am_open, candle_5am_close)
   candle_5am_body_top = max(candle_5am_open, candle_5am_close)
   ```

3. **Verificar que el cuerpo esté dentro del rango completo:**
   ```python
   body_inside_range = (
       candle_5am_body_bottom >= candle_1am_low and
       candle_5am_body_top <= candle_1am_high
   )
   
   if not body_inside_range:
       return None  # No es CRT de Revisión
   ```

4. **Verificar que NO barrió ambos extremos:**
   ```python
   swept_high = candle_5am_high > candle_1am_high
   swept_low = candle_5am_low < candle_1am_low
   
   if swept_high and swept_low:
       return None  # Es CRT de Extremo, no de Revisión
   ```

5. **Determinar tipo de revisión:**
   ```python
   if swept_high:
       # Revisión Bajista (BULLISH_SWEEP)
       target_price = candle_1am_low  # TP = extremo opuesto
       direction = 'BEARISH'
   elif swept_low:
       # Revisión Alcista (BEARISH_SWEEP)
       target_price = candle_1am_high  # TP = extremo opuesto
       direction = 'BULLISH'
   ```

**Retorno del detector:**
```python
{
    'detected': True,
    'sweep_type': 'BULLISH_SWEEP' | 'BEARISH_SWEEP',
    'direction': 'BULLISH' | 'BEARISH',  # Dirección hacia el TP
    'target_price': float,  # TP (extremo opuesto de vela 1 AM)
    'swept_extreme': 'high' | 'low',  # Extremo barrido
    'sweep_price': float,  # Precio barrido (HIGH o LOW de vela 1 AM)
    'candle_1am': Dict,
    'candle_5am': Dict,
    'candle_9am': Dict,
    'body_inside_range': True,
    'close_type': 'BULLISH' | 'BEARISH'
}
```

---

## 💹 Estrategia: `strategies/crt_revision_strategy.py`

### Clase: `CRTRevisionStrategy`

La estrategia implementa un flujo de 4 etapas similar a CRT de Continuación:

### Etapa 1/4: Verificación de Noticias
- Verifica que no haya noticias de alto impacto 5 minutos antes/después

### Etapa 2/4: Detección CRT de Revisión
- Llama a `detect_crt_revision(symbol)` para detectar el patrón en H4
- Muestra logs detallados del patrón detectado

### Etapa 3/4: Búsqueda de Entrada FVG
- Busca FVG en la temporalidad de entrada configurada
- **FVG Esperado según CRT:**
  - Si barrió HIGH → TP = LOW de vela 1 AM → Busca FVG BAJISTA
  - Si barrió LOW → TP = HIGH de vela 1 AM → Busca FVG ALCISTA
- Validaciones estrictas del FVG (igual que CRT de Continuación)

### Etapa 4/4: Ejecución de Orden
- Validaciones finales
- Cálculo de niveles (Entry, SL, TP)
- Ejecución de orden
- Guardado en base de datos

---

## ⚙️ Configuración

### Archivo: `config.yaml`

```yaml
strategy:
  name: "crt_revision"  # Nombre de la estrategia

strategy_config:
  crt_entry_timeframe: "M5"  # Temporalidad de entrada: M1, M5, M15, M30, H1
  min_rr: 2.0                 # Risk/Reward mínimo (default: 1:2, puede ser mayor)

risk_management:
  risk_per_trade_percent: 1.0  # Riesgo por trade (% de cuenta)
  max_trades_per_day: 2        # Máximo de trades por día
  max_position_size: 0.1       # Tamaño máximo de posición (lotes)
```

---

## 📈 Ejemplo de Flujo Completo

### Escenario: Revisión Bajista (BULLISH_SWEEP)

**Paso 1: Detección del Patrón (H4)**

```
Vela 1 AM H4 (NY):
   Open: 1.10800
   High: 1.11000
   Low: 1.10700
   Close: 1.10900
   Rango completo: 1.10700 - 1.11000

Vela 5 AM H4 (NY):
   Open: 1.10850
   High: 1.11050  ← Barrió HIGH de 1 AM
   Low: 1.10800
   Close: 1.10950
   Cuerpo: 1.10850 - 1.10950

✅ Validación:
   - Barrió HIGH: 1.11050 > 1.11000 ✓
   - NO barrió LOW: 1.10800 > 1.10700 ✓
   - Body Bottom (1.10850) >= LOW 1 AM (1.10700) ✓
   - Body Top (1.10950) <= HIGH 1 AM (1.11000) ✓
   - TP = LOW de vela 1 AM = 1.10700
```

**Paso 2: Búsqueda de FVG (M5)**

```
FVG BAJISTA detectado en M5:
   Bottom: 1.10900
   Top: 1.10950
   Estado: VALIDADO
   Entró: True
   Salió: True
   Exit Direction: BAJISTA

✅ Validación:
   - 3 velas forman FVG BAJISTA ✓
   - Vela en formación entró al FVG (HIGH dentro) ✓
   - Precio salió debajo del FVG (1.10880 < 1.10900) ✓
```

**Paso 3: Ejecución**

```
Entry Price: 1.10880 (BID actual)
Stop Loss: 1.11000 (arriba del HIGH barrido)
Take Profit: 1.10700 (LOW de vela 1 AM)
Risk: 0.00120
Reward: 0.00180
RR: 1.50:1

⚠️ RR menor que mínimo (2.0), ajustando TP...
TP ajustado: 1.10640 (para RR 2:1)
Nuevo Reward: 0.00240
Nuevo RR: 2.00:1 ✓

✅ Orden ejecutada: SELL
```

---

## 📝 Notas Importantes

### Sobre el Cuerpo Dentro del Rango

**⚠️ CRÍTICO:** El **CUERPO** de la vela 5 AM debe estar completamente dentro del **rango completo (HIGH-LOW)** de la vela 1 AM, NO solo dentro del rango del cuerpo.

- ✅ **Correcto:** `body_bottom >= LOW_1AM` y `body_top <= HIGH_1AM`
- ❌ **Incorrecto:** Comparar solo con el rango del cuerpo de la vela 1 AM

### Sobre el Barrido de un Solo Extremo

**⚠️ IMPORTANTE:** Si la vela 5 AM barre **AMBOS extremos**, NO es CRT de Revisión, es **CRT de Extremo**.

- ✅ **Correcto:** Barre solo HIGH o solo LOW
- ❌ **Incorrecto:** Barre ambos extremos (eso es CRT de Extremo)

### Sobre el Objetivo (TP)

- El TP es el **extremo opuesto** de la vela 1 AM (el que NO fue barrido)
- Si barrió HIGH → TP = LOW de vela 1 AM
- Si barrió LOW → TP = HIGH de vela 1 AM
- El TP puede ser ajustado por RR si no cumple el mínimo configurado

---

## 📊 Resumen de Condiciones

### Revisión Bajista (BULLISH_SWEEP)

| Condición | Validación |
|-----------|------------|
| Barrió HIGH | `candle_5am_high > candle_1am_high` |
| NO barrió LOW | `candle_5am_low >= candle_1am_low` |
| Cuerpo dentro del rango | `body_bottom >= LOW_1AM` y `body_top <= HIGH_1AM` |
| TP | `LOW de vela 1 AM` |
| FVG esperado | `FVG BAJISTA` |
| Dirección orden | `SELL` |

### Revisión Alcista (BEARISH_SWEEP)

| Condición | Validación |
|-----------|------------|
| Barrió LOW | `candle_5am_low < candle_1am_low` |
| NO barrió HIGH | `candle_5am_high <= candle_1am_high` |
| Cuerpo dentro del rango | `body_bottom >= LOW_1AM` y `body_top <= HIGH_1AM` |
| TP | `HIGH de vela 1 AM` |
| FVG esperado | `FVG ALCISTA` |
| Dirección orden | `BUY` |

---

## 🔗 Referencias

- **Teoría CRT General:** Ver [CRT_THEORY_DOCS.md](./CRT_THEORY_DOCS.md)
- **CRT de Continuación:** Ver [CRT_CONTINUATION_DOCS.md](./CRT_CONTINUATION_DOCS.md)
- **CRT de Extremo:** Ver [CRT_EXTREME_DOCS.md](./CRT_EXTREME_DOCS.md)

---

**Última actualización:** Diciembre 2025
**Versión:** 1.0
