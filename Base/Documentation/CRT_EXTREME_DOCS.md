# Documentación: CRT de Extremo - Estrategia Completa

## 📖 Introducción

El **CRT de Extremo** es una estrategia de trading que detecta patrones de alta volatilidad en temporalidad H4, donde la vela de **5 AM** barre **AMBOS extremos** (HIGH y LOW) de la vela de **1 AM** (hora NY). A diferencia de los otros tipos de CRT, el objetivo (TP) se define según el **tipo de cierre** de la vela 5 AM, no por el extremo barrido.

Esta estrategia combina:
- **Detección de CRT de Extremo en H4**: Identifica cuando la vela 5 AM barre ambos extremos de la vela 1 AM
- **TP según cierre**: El objetivo se define por el tipo de cierre de la vela 5 AM (alcista o bajista)
- **Entrada por FVG**: Utiliza Fair Value Gaps (FVG) en temporalidades menores para entradas precisas
- **Gestión de riesgo**: Risk/Reward mínimo configurable (puede ser mayor si TP lógico lo requiere)

---

## 🎯 Conceptos Clave del CRT de Extremo

### Diferencia con Otros Tipos de CRT

**CRT de Continuación:**
- Barre **1 extremo** y el CLOSE está **FUERA** del rango → Continuación

**CRT de Revisión:**
- Barre **1 extremo** y el CUERPO está **DENTRO** del rango → Reversión

**CRT de Extremo:**
- Barre **AMBOS extremos** → TP según cierre de vela 5 AM

### Características Únicas

1. **Alta Volatilidad:**
   - Indica un movimiento de precio muy amplio en la vela 5 AM
   - Muestra indecisión del mercado que se resuelve con el cierre

2. **TP Dinámico:**
   - No se basa en el extremo barrido
   - Se basa en el **tipo de cierre** de la vela 5 AM:
     - Cerró alcista → TP = HIGH de vela 5 AM
     - Cerró bajista → TP = LOW de vela 5 AM

3. **Velas Clave:**
   - **Vela 1 AM**: Establece el rango que será barrido
   - **Vela 5 AM**: Barre ambos extremos y define el TP según su cierre
   - **Vela 9 AM**: Vela donde esperamos alcanzar el objetivo

---

## 📊 Condiciones de Detección

### Condiciones Obligatorias

1. **Barrido de AMBOS extremos:**
   - HIGH de vela 5 AM > HIGH de vela 1 AM
   - LOW de vela 5 AM < LOW de vela 1 AM
   - **Ambas condiciones deben cumplirse simultáneamente**

2. **Definición del TP según cierre:**
   - Si la vela 5 AM cerró **alcista** (Close > Open):
     - TP = **HIGH de vela 5 AM**
     - Dirección: **BULLISH** (alcista)
   - Si la vela 5 AM cerró **bajista** (Close < Open):
     - TP = **LOW de vela 5 AM**
     - Dirección: **BEARISH** (bajista)

3. **Caso especial - Doji:**
   - Si la vela 5 AM cerró sin cuerpo (Close = Open):
     - Por defecto, usa HIGH como TP
     - Se registra como 'DOJI' en el tipo de cierre

**Ejemplo visual - Extremo Alcista:**

```
Vela 1 AM:     HIGH = 1.11000
               [Cuerpo: 1.10800 - 1.10900]
               LOW = 1.10700
               Rango: 1.10700 - 1.11000

Vela 5 AM:     HIGH = 1.11150 ← Barrió HIGH de 1 AM
               [Cuerpo: 1.11020 - 1.11120] ← Cerró alcista
               LOW = 1.10650 ← Barrió LOW de 1 AM
               Close = 1.11120 > Open = 1.11020 ✓ (alcista)

✅ Detectado: CRT de Extremo ALCISTA
   - Barrió HIGH: 1.11150 > 1.11000 ✓
   - Barrió LOW: 1.10650 < 1.10700 ✓
   - Cerró alcista: Close (1.11120) > Open (1.11020) ✓
   - TP = HIGH de vela 5 AM = 1.11150
   - Dirección: BULLISH
```

**Ejemplo visual - Extremo Bajista:**

```
Vela 1 AM:     HIGH = 1.11000
               [Cuerpo: 1.10800 - 1.10900]
               LOW = 1.10700
               Rango: 1.10700 - 1.11000

Vela 5 AM:     HIGH = 1.11100 ← Barrió HIGH de 1 AM
               [Cuerpo: 1.11050 - 1.10950] ← Cerró bajista
               LOW = 1.10650 ← Barrió LOW de 1 AM
               Close = 1.10950 < Open = 1.11050 ✓ (bajista)

✅ Detectado: CRT de Extremo BAJISTA
   - Barrió HIGH: 1.11100 > 1.11000 ✓
   - Barrió LOW: 1.10650 < 1.10700 ✓
   - Cerró bajista: Close (1.10950) < Open (1.11050) ✓
   - TP = LOW de vela 5 AM = 1.10650
   - Dirección: BEARISH
```

---

## 🔍 Detector: `Base/crt_extreme_detector.py`

### Clase: `CRTextremeDetector`

**Función principal:** `detect_extreme_crt(symbol: str)`

**Proceso de detección:**

1. **Obtener velas H4:**
   ```python
   candle_1am = get_candle('H4', '1am', symbol)
   candle_5am = get_candle('H4', '5am', symbol)
   candle_9am = get_candle('H4', '9am', symbol)  # Opcional
   ```

2. **Verificar barrido de ambos extremos:**
   ```python
   swept_high = candle_5am_high > candle_1am_high
   swept_low = candle_5am_low < candle_1am_low
   
   if not (swept_high and swept_low):
       return None  # No es CRT de Extremo
   ```

3. **Determinar tipo de cierre:**
   ```python
   candle_5am_is_bullish = candle_5am_close > candle_5am_open
   candle_5am_is_bearish = candle_5am_close < candle_5am_open
   ```

4. **Definir TP según cierre:**
   ```python
   if candle_5am_is_bullish:
       target_price = candle_5am_high  # TP = HIGH
       direction = 'BULLISH'
       close_type = 'BULLISH'
   elif candle_5am_is_bearish:
       target_price = candle_5am_low  # TP = LOW
       direction = 'BEARISH'
       close_type = 'BEARISH'
   else:
       # Doji - usar HIGH por defecto
       target_price = candle_5am_high
       direction = 'BULLISH'
       close_type = 'DOJI'
   ```

**Retorno del detector:**
```python
{
    'detected': True,
    'sweep_type': 'EXTREME_SWEEP',
    'direction': 'BULLISH' | 'BEARISH',  # Dirección hacia el TP
    'target_price': float,  # TP (HIGH o LOW de vela 5 AM según cierre)
    'swept_high': float,  # HIGH de vela 1 AM (barrido)
    'swept_low': float,  # LOW de vela 1 AM (barrido)
    'candle_1am': Dict,
    'candle_5am': Dict,
    'candle_9am': Dict,
    'close_type': 'BULLISH' | 'BEARISH' | 'DOJI'
}
```

---

## 💹 Estrategia: `strategies/crt_extreme_strategy.py`

### Clase: `CRTextremeStrategy`

La estrategia implementa un flujo de 4 etapas:

### Etapa 1/4: Verificación de Noticias
- Verifica que no haya noticias de alto impacto 5 minutos antes/después

### Etapa 2/4: Detección CRT de Extremo
- Llama a `detect_crt_extreme(symbol)` para detectar el patrón en H4
- Muestra logs detallados:
  ```
  ✅ CRT DE EXTREMO DETECTADO
  📊 TIPO DE CRT: EXTREMO
  📍 Detalles del Patrón:
     • Barrido: Vela 5 AM barrió AMBOS extremos de vela 1 AM
     • Barrió HIGH: 1.11000
     • Barrió LOW: 1.10700
     • Tipo de cierre de vela 5 AM: BULLISH
  🎯 OBJETIVO (TP) SEGÚN CRT DE EXTREMO:
     • Objetivo definido desde: HIGH de vela 5 AM (cerró alcista)
     • Precio objetivo (TP): 1.11150
  ```

### Etapa 3/4: Búsqueda de Entrada FVG
- Busca FVG en la temporalidad de entrada configurada
- **FVG Esperado según CRT:**
  - Si cerró alcista → TP = HIGH de vela 5 AM → Busca FVG ALCISTA
  - Si cerró bajista → TP = LOW de vela 5 AM → Busca FVG BAJISTA
- Validaciones estrictas del FVG (igual que otros CRT)

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
  name: "crt_extreme"  # Nombre de la estrategia

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

### Escenario: Extremo Alcista

**Paso 1: Detección del Patrón (H4)**

```
Vela 1 AM H4 (NY):
   Open: 1.10800
   High: 1.11000
   Low: 1.10700
   Close: 1.10900
   Rango: 1.10700 - 1.11000

Vela 5 AM H4 (NY):
   Open: 1.11020
   High: 1.11150  ← Barrió HIGH de 1 AM
   Low: 1.10650   ← Barrió LOW de 1 AM
   Close: 1.11120
   Cuerpo: 1.11020 - 1.11120

✅ Validación:
   - Barrió HIGH: 1.11150 > 1.11000 ✓
   - Barrió LOW: 1.10650 < 1.10700 ✓
   - Cerró alcista: Close (1.11120) > Open (1.11020) ✓
   - TP = HIGH de vela 5 AM = 1.11150
   - Dirección: BULLISH
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

**Paso 3: Ejecución**

```
Entry Price: 1.11060 (ASK actual)
Stop Loss: 1.10950 (debajo del FVG)
Take Profit: 1.11150 (HIGH de vela 5 AM)
Risk: 0.00110
Reward: 0.00090
RR: 0.82:1

⚠️ RR menor que mínimo (2.0), ajustando TP...
TP ajustado: 1.11280 (para RR 2:1)
Nuevo Reward: 0.00220
Nuevo RR: 2.00:1 ✓

✅ Orden ejecutada: BUY
```

---

## 📝 Notas Importantes

### Sobre el Barrido de Ambos Extremos

**⚠️ CRÍTICO:** Para ser CRT de Extremo, la vela 5 AM **DEBE** barrer **AMBOS extremos** simultáneamente.

- ✅ **Correcto:** `HIGH_5AM > HIGH_1AM` Y `LOW_5AM < LOW_1AM`
- ❌ **Incorrecto:** Solo barre uno de los extremos (eso es Continuación o Revisión)

### Sobre el TP según Cierre

**⚠️ IMPORTANTE:** El TP NO se basa en qué extremo fue barrido, sino en **cómo cerró la vela 5 AM**.

- Si cerró alcista → TP = HIGH de vela 5 AM (independientemente de qué extremo se barrió primero)
- Si cerró bajista → TP = LOW de vela 5 AM (independientemente de qué extremo se barrió primero)

### Sobre la Alta Volatilidad

- Este patrón indica **alta volatilidad** y **indecisión del mercado**
- El cierre de la vela 5 AM "resuelve" la indecisión y define la dirección
- Es un patrón menos común que Continuación o Revisión

### Sobre el Objetivo (TP)

- El TP se define desde la **vela de 5 AM** (HIGH o LOW según cierre)
- Esperamos que el precio **alcance ese objetivo durante la vela de 9 AM**
- El TP puede ser ajustado por RR si no cumple el mínimo configurado

---

## 📊 Resumen de Condiciones

### Extremo Alcista

| Condición | Validación |
|-----------|------------|
| Barrió HIGH | `candle_5am_high > candle_1am_high` |
| Barrió LOW | `candle_5am_low < candle_1am_low` |
| Cerró alcista | `candle_5am_close > candle_5am_open` |
| TP | `HIGH de vela 5 AM` |
| FVG esperado | `FVG ALCISTA` |
| Dirección orden | `BUY` |

### Extremo Bajista

| Condición | Validación |
|-----------|------------|
| Barrió HIGH | `candle_5am_high > candle_1am_high` |
| Barrió LOW | `candle_5am_low < candle_1am_low` |
| Cerró bajista | `candle_5am_close < candle_5am_open` |
| TP | `LOW de vela 5 AM` |
| FVG esperado | `FVG BAJISTA` |
| Dirección orden | `SELL` |

---

## 🔄 Comparación con Otros Tipos de CRT

| Aspecto | Continuación | Revisión | Extremo |
|---------|--------------|----------|---------|
| **Barridos** | 1 extremo | 1 extremo | **AMBOS extremos** |
| **Cierre** | CLOSE fuera del rango | CUERPO dentro del rango | Según cierre |
| **TP** | Extremo de vela 5 AM | Extremo opuesto de vela 1 AM | **HIGH o LOW de vela 5 AM según cierre** |
| **Frecuencia** | Común | Común | Menos común |
| **Volatilidad** | Media | Media | **Alta** |

---

## 🔗 Referencias

- **Teoría CRT General:** Ver [CRT_THEORY_DOCS.md](./CRT_THEORY_DOCS.md)
- **CRT de Continuación:** Ver [CRT_CONTINUATION_DOCS.md](./CRT_CONTINUATION_DOCS.md)
- **CRT de Revisión:** Ver [CRT_REVISION_DOCS.md](./CRT_REVISION_DOCS.md)

---

## 🎓 Casos de Uso

### Cuándo Usar CRT de Extremo

1. **Mercados de Alta Volatilidad:**
   - Sesiones de Londres/Nueva York
   - Durante eventos económicos importantes
   - Después de noticias de alto impacto

2. **Confirmación de Dirección:**
   - El cierre de la vela 5 AM confirma la dirección final
   - Útil cuando hay indecisión en el mercado

3. **Operaciones de Mayor Alcance:**
   - El TP puede ser más lejano que en otros tipos de CRT
   - Permite operaciones con mayor potencial de ganancia

---

**Última actualización:** Diciembre 2025
**Versión:** 1.0
