# Documentación: Estrategia CRT (Candle Range Theory)

## 📖 Introducción

La **Estrategia CRT** implementa la metodología de **Candle Range Theory (Teoría del Rango de Velas)** para detectar manipulaciones de liquidez y operar reversiones basadas en el comportamiento institucional del mercado.

## 🎯 Tipo de Estrategia

**Tipo 1: CRT de Reversión (Reversal CRT)**
- Detecta barridos de liquidez en temporalidad alta
- Opera reversiones hacia el extremo opuesto de la vela manipulada
- Utiliza confirmación multi-temporal para validar señales

## 🔄 Flujo de la Estrategia

### Etapa 1: Verificación de Noticias
- Verifica noticias económicas de alto impacto
- Bloquea operaciones 5 minutos antes y después de noticias importantes
- Solo continúa si no hay noticias cercanas

### Etapa 2: Detección de Barrido de Liquidez
- Analiza temporalidad alta (H4 o D1 por defecto)
- Detecta barridos donde:
  - El precio rompe un extremo (high o low) de una vela anterior
  - Pero cierra dentro del rango de esa vela
- Identifica dirección esperada (reversión)

### Etapa 3: Patrón Vayas (Opcional)
- Si está habilitado, detecta agotamiento de tendencia
- Indica posible cambio de sesgo del mercado
- No es obligatorio para ejecutar la orden

### Etapa 4: Confirmación con Vela Envolvente (Opcional)
- Si está habilitado, busca confirmación en temporalidad baja (M15 o M5)
- Verifica que la vela envolvente confirme la dirección del barrido
- Aumenta la precisión de las entradas

### Etapa 5: Ejecución de Orden
- Calcula niveles de entrada, SL y TP
- Valida Risk/Reward mínimo (default: 1:2)
- Calcula volumen basado en riesgo porcentual
- Ejecuta orden hacia el extremo opuesto del barrido

## 📊 Parámetros de Configuración

### En `config.yaml`:

```yaml
strategy:
  name: "crt_strategy"

strategy_config:
  # Temporalidades
  crt_high_timeframe: "H4"      # H4 o D1 (temporalidad alta para barridos)
  crt_entry_timeframe: "M15"   # M15 o M5 (temporalidad de confirmación)
  
  # Opciones de detección
  crt_use_vayas: false         # Habilitar patrón Vayas (opcional)
  crt_use_engulfing: true      # Confirmar con velas envolventes
  crt_lookback: 5              # Número de velas a revisar para barridos
  
  # Risk/Reward
  min_rr: 2.0                   # Risk/Reward mínimo (1:2)

risk_management:
  risk_per_trade_percent: 1.0  # Porcentaje de riesgo por trade
  max_trades_per_day: 2         # Máximo de trades por día
```

## 🔍 Tipos de Barridos Detectados

### 1. Barrido Alcista (Bullish Sweep)
- **Condición**: El precio rompe el **máximo** de una vela anterior pero cierra por debajo
- **Señal**: Reversión **bajista** esperada
- **TP**: Hacia el **mínimo** de la vela manipulada
- **Operación**: SELL (venta)

### 2. Barrido Bajista (Bearish Sweep)
- **Condición**: El precio rompe el **mínimo** de una vela anterior pero cierra por encima
- **Señal**: Reversión **alcista** esperada
- **TP**: Hacia el **máximo** de la vela manipulada
- **Operación**: BUY (compra)

## 📈 Cálculo de Niveles

### Precio de Entrada
- **BUY**: Precio ASK actual del mercado
- **SELL**: Precio BID actual del mercado

### Stop Loss
- **BUY**: Por debajo del precio barrido (con margen de 0.1%)
- **SELL**: Por encima del precio barrido (con margen de 0.1%)

### Take Profit
- **BUY**: Hacia el máximo de la vela manipulada
- **SELL**: Hacia el mínimo de la vela manipulada

### Risk/Reward
- Se valida que el RR sea al menos el mínimo configurado (default: 1:2)
- Si el RR es insuficiente, la orden no se ejecuta

## 💰 Gestión de Riesgo

### Cálculo de Volumen
- Basado en porcentaje de riesgo de la cuenta (`risk_per_trade_percent`)
- Calcula automáticamente el volumen necesario para arriesgar el % configurado
- Normaliza según límites del símbolo (mínimo, máximo, step)

### Límites Diarios
- Respeta el límite de trades por día (`max_trades_per_day`)
- Verifica desde base de datos para consistencia
- No permite nuevas entradas si hay posiciones abiertas

## 📝 Logs y Monitoreo

La estrategia genera logs estructurados en cada etapa:

```
[EURUSD] 📰 Etapa 1/5: Verificando noticias económicas...
[EURUSD] ✅ Etapa 1/5: Noticias OK - Puede operar
[EURUSD] 🔍 Etapa 2/5: Buscando barrido de liquidez en H4...
[EURUSD] ✅ Etapa 2/5 COMPLETA: Barrido detectado - BULLISH_SWEEP | Dirección esperada: BEARISH
[EURUSD] 🔍 Etapa 4/5: Buscando confirmación con vela envolvente en M15...
[EURUSD] ✅ Etapa 4/5 COMPLETA: Vela envolvente BEARISH_ENGULFING confirma dirección BEARISH
[EURUSD] 💹 Etapa 5/5: Calculando entrada y ejecutando orden...
[EURUSD] ✅ ORDEN EJECUTADA EXITOSAMENTE
```

## ⚙️ Configuración Recomendada

### Para Trading Conservador
```yaml
strategy_config:
  crt_high_timeframe: "D1"      # Temporalidad más alta = menos señales pero más confiables
  crt_entry_timeframe: "M15"   # Confirmación en M15
  crt_use_vayas: true           # Activar Vayas para mayor filtrado
  crt_use_engulfing: true       # Confirmar con velas envolventes
  min_rr: 2.5                   # RR más alto = menos trades pero mejor calidad
```

### Para Trading Agresivo
```yaml
strategy_config:
  crt_high_timeframe: "H4"      # Temporalidad más baja = más señales
  crt_entry_timeframe: "M5"    # Confirmación en M5 (más rápida)
  crt_use_vayas: false          # Desactivar Vayas para más oportunidades
  crt_use_engulfing: false      # Sin confirmación adicional
  min_rr: 1.5                   # RR más bajo = más trades
```

## 🔗 Integración con Otros Módulos

La estrategia CRT utiliza:
- **`Base.crt_detector`**: Detección de barridos, Vayas y velas envolventes
- **`Base.news_checker`**: Verificación de noticias económicas
- **`Base.order_executor`**: Ejecución de órdenes en MT5
- **`Base.database`**: Guardado de órdenes en base de datos

## 📚 Referencias

- **Documentación CRT**: [Base/Documentation/CRT_THEORY_DOCS.md](../Base/Documentation/CRT_THEORY_DOCS.md)
- **Detector CRT**: `Base/crt_detector.py`
- **Estrategia**: `strategies/crt_strategy.py`

## ⚠️ Consideraciones Importantes

1. **Confirmación Multi-Temporal**: La estrategia requiere confirmación en múltiples temporalidades para mayor precisión
2. **Noticias**: Siempre verifica noticias antes de operar (configurado automáticamente)
3. **Risk/Reward**: Respeta el RR mínimo configurado, no ejecuta si es insuficiente
4. **Posiciones Abiertas**: No permite nuevas entradas mientras hay posiciones activas
5. **Límites Diarios**: Respeta el límite de trades por día configurado

## 🎓 Ejemplo de Uso

1. **Configurar en `config.yaml`**:
```yaml
strategy:
  name: "crt_strategy"
```

2. **Ejecutar el bot**:
```bash
python bot_trading.py
```

3. **Monitorear logs**:
- El bot analizará el mercado en busca de barridos CRT
- Cuando detecte una señal válida, ejecutará la orden automáticamente
- Los logs mostrarán cada etapa del proceso

---

**Última actualización**: Diciembre 2025
