# Documentación: CRT (Candle Range Theory) - Teoría del Rango de Velas

## 📖 Introducción

La **CRT (Candle Range Theory)** o **Teoría del Rango de Velas** es una metodología de trading que se enfoca en analizar la acción del precio dentro del rango de una sola vela, identificando manipulaciones de liquidez (barridos de máximos/mínimos) por parte de grandes actores del mercado para anticipar movimientos de reversión o continuación en temporalidades mayores.

Esta estrategia opera principalmente en **sesiones clave** como Londres y Nueva York para buscar entradas precisas basadas en el comportamiento institucional del mercado.

---

## 🎯 Principios Fundamentales

### 1. Cada Vela Tiene un Rango

**Concepto clave:**
- Cada vela en un gráfico (diario, 4h, 1h, etc.) representa un **rango de precios** definido por su máximo (high) y mínimo (low).
- Este rango contiene información valiosa sobre la intención del mercado y la manipulación de liquidez.

**Aplicación:**
- El rango de una vela se convierte en una zona de referencia para futuros movimientos.
- Los extremos (high/low) de velas anteriores actúan como niveles de liquidez.

### 2. Manipulación de Liquidez

**Concepto clave:**
- Los grandes participantes del mercado (institucionales, bancos centrales, fondos) inducen **falsos rompimientos** (barridos) de los máximos o mínimos de velas anteriores.
- El objetivo es **recolectar órdenes de stop** de traders minoristas antes de mover el precio en la dirección opuesta.

**Cómo funciona:**
1. El precio "barre" (rompe temporalmente) el máximo o mínimo de una vela anterior.
2. Esto activa stops de traders que esperaban continuidad.
3. El precio cierra **dentro del rango** de la vela manipulada.
4. El mercado se mueve hacia el **extremo opuesto** (reversión).

### 3. Movimiento de Reversión Post-Barrido

**Concepto clave:**
- Después de un barrido (mecha que supera el extremo de una vela anterior pero cierra dentro de su rango), el precio tiende a moverse hacia el **extremo opuesto** de esa vela.

**Ejemplo:**
- Si el precio barre el **máximo** de una vela anterior pero cierra por debajo → Señal **bajista** (reversión hacia el mínimo).
- Si el precio barre el **mínimo** de una vela anterior pero cierra por encima → Señal **alcista** (reversión hacia el máximo).

### 4. Análisis Multi-Temporal

**Concepto clave:**
- Se utiliza una **jerarquía de temporalidades** para confirmar señales:
  - **Temporalidades altas** (semanal, diario): Identificar tendencia general y estructura del mercado.
  - **Temporalidades medias** (4h, 1h): Detectar manipulaciones y barridos de liquidez.
  - **Temporalidades bajas** (M15, M5): Buscar entradas precisas con patrones de confirmación.

**Flujo de análisis:**
```
Semanal/D1 → Tendencia general
    ↓
H4/H1 → Detectar barridos y manipulaciones
    ↓
M15/M5 → Entrada precisa con confirmación
```

### 5. Patrón "Vayas" (Cambio de Sesgo)

**Concepto clave:**
- El **"Vayas"** es un patrón que indica un posible **agotamiento de la tendencia** o cambio de sesgo del mercado.

**Características:**
- En una tendencia alcista: Aparece una vela que, en lugar de romper el máximo anterior, **cierra dentro del rango** de la vela anterior.
- En una tendencia bajista: Aparece una vela que, en lugar de romper el mínimo anterior, **cierra dentro del rango** de la vela anterior.

**Señal:**
- Indica que la fuerza de la tendencia se está debilitando.
- Puede preceder a una reversión o corrección significativa.

---

## 🔍 Componentes de la CRT

### Barrido de Liquidez (Liquidity Sweep)

**Definición:**
- Un barrido ocurre cuando el precio **rompe temporalmente** un extremo (high o low) de una vela anterior, pero luego **cierra dentro del rango** de esa vela.

**Tipos de barridos:**

1. **Barrido Alcista (Bullish Sweep):**
   - El precio rompe el **máximo** de una vela anterior.
   - Cierra por debajo del máximo (dentro del rango).
   - Señal: Posible reversión **bajista** hacia el mínimo.

2. **Barrido Bajista (Bearish Sweep):**
   - El precio rompe el **mínimo** de una vela anterior.
   - Cierra por encima del mínimo (dentro del rango).
   - Señal: Posible reversión **alcista** hacia el máximo.

**Identificación:**
```
Vela Anterior: High = 1.1000, Low = 1.0950, Close = 1.0980
Vela Actual: High = 1.1005, Low = 1.0960, Close = 1.0970

✅ Barrido detectado: High actual (1.1005) > High anterior (1.1000)
✅ Cierre dentro del rango: Close actual (1.0970) < High anterior (1.1000)
→ Señal: Reversión bajista esperada hacia Low anterior (1.0950)
```

### Vela Envolvente (Engulfing Candle)

**Definición:**
- Una vela que **envuelve completamente** el rango de la vela anterior.
- Indica un cambio de momentum y puede confirmar una reversión.

**Tipos:**

1. **Vela Envolvente Bajista (Bearish Engulfing):**
   - Vela alcista seguida de una vela bajista más grande.
   - La vela bajista envuelve completamente la alcista.
   - Señal: Reversión bajista.

2. **Vela Envolvente Alcista (Bullish Engulfing):**
   - Vela bajista seguida de una vela alcista más grande.
   - La vela alcista envuelve completamente la bajista.
   - Señal: Reversión alcista.

### Patrón de Rechazo

**Definición:**
- Una vela que muestra un **rechazo claro** en un nivel de liquidez.
- Caracterizada por una mecha larga (wick) y un cuerpo pequeño.

**Ejemplos:**
- **Rechazo en máximo:** Mecha superior larga, cierre por debajo → Señal bajista.
- **Rechazo en mínimo:** Mecha inferior larga, cierre por encima → Señal alcista.

---

## 📊 Aplicación Práctica: Ejemplo Completo

### Escenario: Tendencia Alcista con Posible Reversión

#### Paso 1: Identificar Tendencia (Temporalidad Alta)

**Análisis en D1:**
- Tendencia alcista clara.
- Velas cierran consistentemente por encima de los máximos anteriores.
- Estructura de máximos y mínimos crecientes.

#### Paso 2: Detectar "Vayas" (Cambio de Sesgo)

**Análisis en D1:**
- Aparece una vela que **no rompe el máximo** de la vela anterior.
- Cierra **dentro del rango** de la vela anterior.
- Señal: Posible agotamiento de la tendencia alcista.

#### Paso 3: Buscar Manipulación (Temporalidad Media)

**Análisis en H4:**
- Durante la sesión de Londres o Nueva York.
- El precio **barre el máximo** de una vela H4 anterior.
- La vela cierra **por debajo del máximo** (dentro del rango).
- Señal: Manipulación de liquidez detectada.

#### Paso 4: Confirmar con Patrón (Temporalidad Baja)

**Análisis en M15/M5:**
- Aparece una **vela envolvente bajista** o **patrón de rechazo**.
- El precio muestra confirmación de reversión.
- Señal: Entrada en corto (SELL).

#### Paso 5: Operar

**Entrada:**
- Dirección: **SELL** (corto).
- Precio de entrada: Después de confirmación en M15/M5.
- Stop Loss: Por encima del máximo barrido.
- Take Profit: Hacia el **mínimo de la vela manipulada** (extremo opuesto).

---

## 🕐 Sesiones Clave para CRT

### Sesión de Londres (8:00 AM - 12:00 PM GMT / 3:00 AM - 7:00 AM NY)

**Características:**
- Alta volatilidad y volumen.
- Manipulaciones frecuentes de liquidez.
- Ideal para detectar barridos en H4.

### Sesión de Nueva York (1:00 PM - 5:00 PM GMT / 8:00 AM - 12:00 PM NY)

**Características:**
- Solapamiento con Londres (mayor liquidez).
- Movimientos institucionales significativos.
- Confirmación de tendencias y reversiones.

### Sesión Asiática (12:00 AM - 8:00 AM GMT / 7:00 PM - 3:00 AM NY)

**Características:**
- Menor volatilidad.
- Generalmente menos manipulaciones.
- Útil para preparación y análisis.

---

## 🎯 Tipos de CRT

La estrategia CRT se puede clasificar en **3 tipos principales**, cada uno con características específicas y condiciones únicas:

### Tipo 1: CRT de Continuación (Continuation CRT)

**Enfoque:** Detectar continuaciones de tendencia después de manipulación de liquidez.

**Condiciones:**
- La vela 5 AM debe barrer un extremo de la vela 1 AM (HIGH o LOW)
- El **CLOSE** de la vela 5 AM debe estar **FUERA** del rango completo (HIGH-LOW) de la vela 1 AM
- Indica continuación en la dirección del barrido

**Objetivo (TP):**
- Si barrió HIGH → TP = HIGH de vela 5 AM (continuación alcista)
- Si barrió LOW → TP = LOW de vela 5 AM (continuación bajista)

**Documentación completa:** Ver [CRT_CONTINUATION_DOCS.md](./CRT_CONTINUATION_DOCS.md)

### Tipo 2: CRT de Revisión (Revision CRT)

**Enfoque:** Detectar reversiones después de barridos de liquidez.

**Condiciones:**
- La vela 5 AM debe barrer UN extremo de la vela 1 AM (HIGH o LOW, pero NO ambos)
- El **CUERPO** de la vela 5 AM debe cerrar **DENTRO** del rango completo (HIGH-LOW) de la vela 1 AM
- Indica reversión hacia el extremo opuesto

**Objetivo (TP):**
- Si barrió HIGH → TP = LOW de vela 1 AM (reversión bajista)
- Si barrió LOW → TP = HIGH de vela 1 AM (reversión alcista)

**Documentación completa:** Ver [CRT_REVISION_DOCS.md](./CRT_REVISION_DOCS.md)

### Tipo 3: CRT de Extremo (Extreme CRT)

**Enfoque:** Detectar cuando se barren ambos extremos simultáneamente, indicando alta volatilidad y dirección según el cierre.

**Condiciones:**
- La vela 5 AM debe barrer **AMBOS extremos** de la vela 1 AM:
  - HIGH de vela 5 AM > HIGH de vela 1 AM
  - LOW de vela 5 AM < LOW de vela 1 AM
- El objetivo se define según el tipo de cierre de la vela 5 AM

**Objetivo (TP):**
- Si cerró alcista (Close > Open) → TP = HIGH de vela 5 AM
- Si cerró bajista (Close < Open) → TP = LOW de vela 5 AM

**Documentación completa:** Ver [CRT_EXTREME_DOCS.md](./CRT_EXTREME_DOCS.md)

---

### Comparación de los 3 Tipos

| Tipo | Barridos | Cierre | TP | Dirección |
|------|----------|--------|----|-----------| 
| **Continuación** | 1 extremo (HIGH o LOW) | CLOSE fuera del rango | Extremo de vela 5 AM | Misma del barrido |
| **Revisión** | 1 extremo (HIGH o LOW) | CUERPO dentro del rango | Extremo opuesto de vela 1 AM | Opuesta al barrido |
| **Extremo** | AMBOS extremos (HIGH y LOW) | Según cierre | HIGH o LOW de vela 5 AM según cierre | Según cierre |

**Nota:** Cada tipo tiene documentación detallada con ejemplos específicos y casos de uso.

---

## 🔧 Implementación Técnica

### Detección de Barridos

```python
def detect_liquidity_sweep(previous_candle, current_candle):
    """
    Detecta si hay un barrido de liquidez
    
    Args:
        previous_candle: Vela anterior (dict con high, low, close)
        current_candle: Vela actual (dict con high, low, close)
    
    Returns:
        Dict con información del barrido o None
    """
    # Barrido alcista (rompe máximo pero cierra dentro)
    if current_candle['high'] > previous_candle['high']:
        if current_candle['close'] < previous_candle['high']:
            return {
                'type': 'BULLISH_SWEEP',
                'direction': 'BEARISH',  # Reversión esperada
                'swept_level': previous_candle['high'],
                'target': previous_candle['low']
            }
    
    # Barrido bajista (rompe mínimo pero cierra dentro)
    if current_candle['low'] < previous_candle['low']:
        if current_candle['close'] > previous_candle['low']:
            return {
                'type': 'BEARISH_SWEEP',
                'direction': 'BULLISH',  # Reversión esperada
                'swept_level': previous_candle['low'],
                'target': previous_candle['high']
            }
    
    return None
```

### Detección de Patrón "Vayas"

```python
def detect_vayas_pattern(candles):
    """
    Detecta el patrón "Vayas" (cambio de sesgo)
    
    Args:
        candles: Lista de velas (al menos 2)
    
    Returns:
        True si se detecta patrón Vayas
    """
    if len(candles) < 2:
        return False
    
    prev_candle = candles[-2]
    current_candle = candles[-1]
    
    # En tendencia alcista: vela no rompe máximo anterior
    if prev_candle['close'] > prev_candle['open']:  # Vela anterior alcista
        if current_candle['high'] <= prev_candle['high']:
            if current_candle['close'] < prev_candle['high']:
                return True  # Vayas detectado - posible agotamiento
    
    # En tendencia bajista: vela no rompe mínimo anterior
    if prev_candle['close'] < prev_candle['open']:  # Vela anterior bajista
        if current_candle['low'] >= prev_candle['low']:
            if current_candle['close'] > prev_candle['low']:
                return True  # Vayas detectado - posible agotamiento
    
    return False
```

---

## ⚠️ Consideraciones Importantes

### 1. Confirmación Multi-Temporal

- **Nunca operar** solo con una temporalidad.
- Siempre confirmar con temporalidades superiores e inferiores.
- La señal debe ser consistente en múltiples timeframes.

### 2. Gestión de Riesgo

- **Stop Loss:** Siempre colocar por encima/debajo del nivel barrido.
- **Take Profit:** Apuntar al extremo opuesto de la vela manipulada.
- **Risk/Reward:** Mínimo 1:2 recomendado.

### 3. Sesiones del Mercado

- Priorizar operaciones en sesiones de Londres y Nueva York.
- Evitar operar en sesión asiática (menor liquidez).
- Considerar solapamiento Londres-Nueva York (mayor volatilidad).

### 4. Filtros Adicionales

- Verificar noticias económicas de alto impacto.
- Considerar estructura de mercado (tendencia, rango, etc.).
- Validar con indicadores de volumen si está disponible.

---

## 📚 Referencias y Conceptos Relacionados

### Conceptos Relacionados

- **ICT (Inner Circle Trader):** Metodología similar que también analiza manipulación de liquidez.
- **Fair Value Gap (FVG):** Brechas de valor que pueden complementar análisis CRT.
- **Order Blocks:** Bloques de órdenes institucionales.
- **Liquidity Pools:** Acumulaciones de órdenes stop.

### Integración con Otras Estrategias

La CRT puede combinarse con:
- **Turtle Soup:** Detección de barridos en H4.
- **FVG Strategy:** Entradas en Fair Value Gaps.
- **News Trading:** Evitar operaciones durante noticias de alto impacto.

---

## 🎓 Resumen

La **CRT (Candle Range Theory)** es una metodología poderosa que:

1. ✅ Analiza la manipulación de liquidez dentro de rangos de velas.
2. ✅ Identifica barridos de extremos para anticipar reversiones.
3. ✅ Utiliza análisis multi-temporal para confirmar señales.
4. ✅ Opera principalmente en sesiones de alta liquidez (Londres/NY).
5. ✅ Busca entradas precisas basadas en comportamiento institucional.

**Ventajas:**
- Alta precisión en entradas.
- Basada en comportamiento real del mercado.
- Aplicable a múltiples temporalidades.
- Complementa otras metodologías (ICT, FVG, etc.).

**Desafíos:**
- Requiere experiencia para identificar patrones correctamente.
- Necesita confirmación multi-temporal.
- Puede generar señales falsas en mercados laterales.

---

---

## 📚 Documentación Específica por Tipo

Cada tipo de CRT tiene documentación detallada:

1. **CRT de Continuación:** [CRT_CONTINUATION_DOCS.md](./CRT_CONTINUATION_DOCS.md)
   - Condiciones de detección
   - Ejemplos prácticos
   - Configuración y uso

2. **CRT de Revisión:** [CRT_REVISION_DOCS.md](./CRT_REVISION_DOCS.md)
   - Condiciones de detección
   - Ejemplos prácticos
   - Configuración y uso

3. **CRT de Extremo:** [CRT_EXTREME_DOCS.md](./CRT_EXTREME_DOCS.md)
   - Condiciones de detección
   - Ejemplos prácticos
   - Configuración y uso

---

**Última actualización**: Diciembre 2025

