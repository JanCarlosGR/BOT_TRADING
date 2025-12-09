# Documentación: Detector de Turtle Soup H4

## 📖 Introducción

El módulo `turtle_soup_detector` detecta **Turtle Soup** (Sopa de Tortuga) en temporalidad H4 según la metodología ICT. Esta estrategia identifica barridos de liquidez en velas clave (1 AM, 5 AM, 9 AM hora NY) y define objetivos basados en extremos opuestos.

**Características principales:**
- ✅ Detecta barridos de swing highs/lows en H4
- ✅ Evalúa velas clave: 1 AM, 5 AM, 9 AM (hora NY)
- ✅ Define objetivos (TP) basados en extremos opuestos
- ✅ Identifica dirección de la reversión esperada

---

## 🚀 Uso Básico

### Importar el módulo

```python
from Base import detect_turtle_soup_h4, TurtleSoupDetector
```

---

## 📊 Concepto de Turtle Soup

### ¿Qué es Turtle Soup?

**Turtle Soup** es una estrategia ICT donde:

1. El precio **barre** (rompe) un swing high o swing low
2. Los traders entran pensando que el movimiento continuará
3. El precio **invierte rápidamente**, atrapando a esos traders
4. Se crea una oportunidad para operar en la **dirección opuesta**

### En H4 con velas clave

La estrategia evalúa:
- **Vela 1 AM NY**: Primera vela clave del día
- **Vela 5 AM NY**: Segunda vela clave
- **Vela 9 AM NY**: Vela que puede barrer extremos anteriores

**Regla principal:**
- Si la vela de **9 AM** barre el high o low de la vela de **1 AM** o **5 AM**
- El **extremo opuesto** de la vela barrida se convierte en el **objetivo (TP)**

---

## 💡 Ejemplos de Uso

### Ejemplo 1: Detección básica

```python
from Base import detect_turtle_soup_h4

# Detectar Turtle Soup en EURUSD
result = detect_turtle_soup_h4('EURUSD')

if result and result.get('detected'):
    print(f"✅ Turtle Soup detectado!")
    print(f"   Tipo: {result['sweep_type']}")
    print(f"   Vela barrida: {result['swept_candle']}")
    print(f"   Extremo barrido: {result['swept_extreme']}")
    print(f"   Precio objetivo (TP): {result['target_price']}")
    print(f"   Dirección: {result['direction']}")
else:
    print("❌ No se detectó Turtle Soup")
```

### Ejemplo 2: Usar la clase directamente

```python
from Base import TurtleSoupDetector

detector = TurtleSoupDetector()

# Obtener velas clave
candles = detector.get_h4_key_candles('EURUSD')
print(f"Vela 1 AM: {candles['1am']}")
print(f"Vela 5 AM: {candles['5am']}")
print(f"Vela 9 AM: {candles['9am']}")

# Detectar Turtle Soup
result = detector.detect_turtle_soup(symbol='EURUSD')
```

---

## 🔧 Estructura de Respuesta

### Cuando se detecta Turtle Soup

```python
{
    'detected': True,
    'swept_candle': '1am',  # o '5am'
    'swept_extreme': 'high',  # o 'low'
    'target_extreme': 'low',  # o 'high' (opuesto)
    'target_price': 1.0950,  # Precio objetivo (TP)
    'sweep_price': 1.1100,   # Precio del barrido
    'candles': {
        '1am': {...},  # Vela de 1 AM
        '5am': {...},  # Vela de 5 AM
        '9am': {...}   # Vela de 9 AM
    },
    'direction': 'BEARISH',  # o 'BULLISH'
    'sweep_type': 'BULLISH_SWEEP'  # o 'BEARISH_SWEEP'
}
```

### Cuando NO se detecta

```python
{
    'detected': False,
    'candles': {
        '1am': {...},
        '5am': {...},
        '9am': {...}
    }
}
```

---

## 📋 Campos Explicados

| Campo | Descripción |
|-------|-------------|
| `detected` | `True` si se detectó Turtle Soup |
| `swept_candle` | Vela que fue barrida: `'1am'` o `'5am'` |
| `swept_extreme` | Extremo barrido: `'high'` o `'low'` |
| `target_extreme` | Extremo opuesto (objetivo): `'high'` o `'low'` |
| `target_price` | Precio objetivo (TP) para la operación |
| `sweep_price` | Precio donde ocurrió el barrido |
| `direction` | Dirección de la reversión: `'BULLISH'` o `'BEARISH'` |
| `sweep_type` | Tipo de barrido: `'BULLISH_SWEEP'` o `'BEARISH_SWEEP'` |
| `candles` | Diccionario con las 3 velas H4 clave |

---

## 🎯 Lógica de Detección

### Barrido Alcista (BULLISH_SWEEP)

```
Vela 1 AM: High = 1.1100, Low = 1.1050
Vela 9 AM: High = 1.1110, Low = 1.1060

✅ Barrido detectado: Vela 9 AM barre el HIGH de 1 AM (1.1110 > 1.1100)
→ Dirección: BEARISH (esperamos reversión bajista)
→ TP: Low de vela 1 AM = 1.1050
```

### Barrido Bajista (BEARISH_SWEEP)

```
Vela 5 AM: High = 1.1100, Low = 1.1050
Vela 9 AM: High = 1.1090, Low = 1.1040

✅ Barrido detectado: Vela 9 AM barre el LOW de 5 AM (1.1040 < 1.1050)
→ Dirección: BULLISH (esperamos reversión alcista)
→ TP: High de vela 5 AM = 1.1100
```

---

## 🔗 Integración con Estrategias

### Ejemplo: Turtle Soup + FVG

```python
from Base import detect_turtle_soup_h4, detect_fvg

# 1. Detectar Turtle Soup en H4
turtle_soup = detect_turtle_soup_h4('EURUSD')

if turtle_soup and turtle_soup.get('detected'):
    direction = turtle_soup['direction']
    target_price = turtle_soup['target_price']
    
    # 2. Buscar FVG en temporalidad menor
    fvg = detect_fvg('EURUSD', 'M5')
    
    if fvg:
        # 3. Verificar que el FVG sea contrario al barrido
        if direction == 'BEARISH' and fvg['fvg_type'] == 'ALCISTA':
            # Barrido alcista → buscar FVG alcista para vender
            if fvg['exited_fvg'] and fvg['exit_direction'] == 'BAJISTA':
                # Señal de entrada
                print("✅ Señal de venta detectada")
                print(f"   TP: {target_price}")
```

---

## ⚙️ Métodos Principales

### `TurtleSoupDetector.get_h4_key_candles()`

Obtiene las velas H4 clave (1 AM, 5 AM, 9 AM hora NY).

```python
detector = TurtleSoupDetector()
candles = detector.get_h4_key_candles('EURUSD')

# candles = {
#     '1am': {...} o None,
#     '5am': {...} o None,
#     '9am': {...} o None
# }
```

### `TurtleSoupDetector.detect_turtle_soup()`

Detecta Turtle Soup en H4.

```python
detector = TurtleSoupDetector()
result = detector.detect_turtle_soup('EURUSD')
```

### `detect_turtle_soup_h4()`

Función de conveniencia para detectar Turtle Soup.

```python
from Base import detect_turtle_soup_h4

result = detect_turtle_soup_h4('EURUSD')
```

---

## ⚠️ Consideraciones Importantes

1. **Velas requeridas**: Necesita las velas de 1 AM, 5 AM y 9 AM (hora NY)
2. **Temporalidad H4**: Solo funciona en H4
3. **Zona horaria**: Usa automáticamente hora de Nueva York
4. **Velas faltantes**: Si falta alguna vela, retorna `None` o `detected: False`
5. **Barrido mínimo**: El barrido debe ser claro (high > target_high o low < target_low)

---

## 📞 Soporte

Para problemas o preguntas:
- Revisa los logs del bot
- Consulta la implementación en `Base/turtle_soup_detector.py`
- Verifica que las velas H4 estén disponibles en MT5
- Asegúrate de que la zona horaria sea correcta

---

**Última actualización**: Diciembre 2025

