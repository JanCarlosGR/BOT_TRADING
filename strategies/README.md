# Estrategias de Trading

Esta carpeta contiene las estrategias de trading del bot. Cada estrategia debe heredar de `BaseStrategy`.

## Estructura

```
strategies/
├── __init__.py
├── README.md
├── default_strategy.py              # Estrategia por defecto
├── turtle_soup_fvg_strategy.py     # Estrategia activa: Turtle Soup H4 + FVG M1
├── crt_strategy.py                  # Estrategia CRT (Candle Range Theory) - Reversión
├── crt_continuation_strategy.py     # Estrategia CRT de Continuación H4 + FVG
├── TURTLE_SOUP_FVG_STRATEGY_CHANGELOG.md  # Historial de cambios de la estrategia
├── rsi_strategy.py                  # Ejemplo: Estrategia RSI
└── fvg_strategy.py                  # Ejemplo: Estrategia basada en FVG
```

## Crear una Nueva Estrategia

1. **Crear archivo de estrategia** (ej: `mi_estrategia.py`):

```python
from strategies import BaseStrategy
import numpy as np
from typing import Optional, Dict
from Base import can_trade_now, detect_fvg, get_candle

class MiEstrategia(BaseStrategy):
    """Descripción de tu estrategia"""
    
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        # 1. Verificar noticias
        can_trade, reason, next_news = can_trade_now(symbol)
        if not can_trade:
            return None
        
        # 2. Tu lógica aquí
        # ...
        
        # 3. Retornar señal si hay
        if condicion_compra:
            return self._create_signal('BUY', symbol, rates[-1]['close'])
        
        return None
```

2. **Registrar en `strategies.py`**:

```python
from strategies.mi_estrategia import MiEstrategia

# En StrategyManager.__init__():
self.strategies = {
    'default': DefaultStrategy(config),
    'mi_estrategia': MiEstrategia(config),  # Nueva estrategia
}
```

3. **Usar en `config.yaml`**:

```yaml
strategy:
  name: "mi_estrategia"
```

## Estrategias Disponibles

### CRT de Continuación Strategy - NUEVA ⭐

Estrategia basada en la **Teoría del Rango de Velas (CRT)** que detecta patrones de **continuación** en temporalidad H4.

**Características principales:**
- **Detección en H4**: Analiza velas de 1 AM y 5 AM (hora NY) para detectar barridos con cuerpo
- **Barrido con cuerpo**: El cuerpo de la vela 5 AM debe barrer extremos de la vela 1 AM (no solo mechas)
- **Cierre fuera del rango**: El cuerpo debe cerrar completamente fuera del rango de la vela 1 AM
- **Entrada por FVG**: Utiliza Fair Value Gaps en temporalidades menores (M1, M5, M15, etc.) para entradas precisas
- **Objetivo desde vela 5 AM**: TP se define desde HIGH/LOW de vela 5 AM, esperamos alcanzarlo en vela 9 AM
- **Monitoreo intensivo**: Monitorea cada segundo cuando detecta FVG esperado pero aún no válido
- **Validaciones estrictas**: Múltiples validaciones aseguran setups de alta calidad

**Tipos de CRT de Continuación:**
- **Continuación Alcista**: Cuerpo de vela 5 AM barre HIGH de vela 1 AM y cierra arriba → TP = HIGH de vela 5 AM
- **Continuación Bajista**: Cuerpo de vela 5 AM barre LOW de vela 1 AM y cierra abajo → TP = LOW de vela 5 AM

**Configuración en `config.yaml`**:
```yaml
strategy:
  name: "crt_continuation"

strategy_config:
  crt_entry_timeframe: "M5"    # Temporalidad de entrada: M1, M5, M15, M30, H1
  min_rr: 2.0                   # Risk/Reward mínimo (default: 1:2)

risk_management:
  risk_per_trade_percent: 1.0   # Riesgo por trade (% de cuenta)
  max_trades_per_day: 2         # Máximo de trades por día
  max_position_size: 0.1        # Tamaño máximo de posición (lotes)
```

**Documentación completa**: Ver [Base/Documentation/CRT_CONTINUATION_DOCS.md](../Base/Documentation/CRT_CONTINUATION_DOCS.md)

---

### CRT Strategy (Candle Range Theory) - Reversión

Estrategia basada en la **Teoría del Rango de Velas (CRT)** que detecta:
- **Barridos de liquidez**: Manipulaciones institucionales donde el precio rompe extremos pero cierra dentro del rango
- **Patrón Vayas** (opcional): Agotamiento de tendencia
- **Velas envolventes** (opcional): Confirmación de reversión en temporalidad baja

**Características**:
- Detecta barridos en temporalidad alta (H4 o D1)
- Confirma con velas envolventes en temporalidad baja (M15 o M5)
- Verifica noticias de alto impacto antes de operar
- Ejecuta órdenes hacia el extremo opuesto del barrido (reversión)
- Risk/Reward mínimo configurable (default: 1:2)
- Gestión de riesgo basada en porcentaje de cuenta

**Configuración en `config.yaml`**:
```yaml
strategy:
  name: "crt_strategy"

strategy_config:
  crt_high_timeframe: "H4"      # Temporalidad alta: H4 o D1
  crt_entry_timeframe: "M15"    # Temporalidad de entrada: M15 o M5
  crt_use_vayas: false          # Usar patrón Vayas (opcional)
  crt_use_engulfing: true       # Confirmar con velas envolventes
  crt_lookback: 5               # Velas a revisar para barridos
  min_rr: 2.0                    # Risk/Reward mínimo (1:2)
```

**Documentación completa**: Ver [Base/Documentation/CRT_THEORY_DOCS.md](../Base/Documentation/CRT_THEORY_DOCS.md)

---

### Turtle Soup FVG Strategy (Activa)

Estrategia principal que combina:
- **Turtle Soup en H4**: Detecta barridos de liquidez en velas H4 (1 AM, 5 AM, 9 AM NY)
- **Entrada en FVG en M1**: Busca entradas en Fair Value Gaps en temporalidad M1
- **Gestión de riesgo**: Valida Risk/Reward mínimo antes de ejecutar

**Características**:
- Detecta barridos de HIGH (BULLISH_SWEEP) y LOW (BEARISH_SWEEP)
- Busca FVG ALCISTA para compras y FVG BAJISTA para ventas
- Valida que el precio entre y salga del FVG en la dirección correcta
- Verifica noticias de alto impacto antes de operar
- Logs estructurados y detallados para cada orden

**Documentación de cambios**: Ver [TURTLE_SOUP_FVG_STRATEGY_CHANGELOG.md](TURTLE_SOUP_FVG_STRATEGY_CHANGELOG.md)

#### Cambios Recientes (Diciembre 2025)

**Fix: Error de formato f-string en logging**
- ✅ Corregido `ValueError: Invalid format specifier` al formatear precios barridos
- ✅ Ahora formatea correctamente valores opcionales (muestra 'N/A' si no existe)
- ✅ Mejora en la robustez del logging de órdenes

**Antes (con error):**
```python
self.logger.info(f"Precio barrido: {turtle_soup.get('sweep_price'):.5f if turtle_soup.get('sweep_price') else 'N/A'}")
# ❌ ValueError: Invalid format specifier
```

**Después (corregido):**
```python
sweep_price = turtle_soup.get('sweep_price')
sweep_price_str = f"{sweep_price:.5f}" if sweep_price is not None else 'N/A'
self.logger.info(f"Precio barrido: {sweep_price_str}")
# ✅ Funciona correctamente
```

---

## Ejemplos de Estrategias

### Estrategia con FVG y Noticias

```python
from Base import can_trade_now, detect_fvg
from strategies import BaseStrategy

class FVGNewsStrategy(BaseStrategy):
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        # Verificar noticias
        can_trade, _, _ = can_trade_now(symbol)
        if not can_trade:
            return None
        
        # Detectar FVG
        fvg = detect_fvg(symbol, 'H4')
        if fvg and fvg['fvg_filled_completely'] and fvg['exited_fvg']:
            if fvg['exit_direction'] == 'ALCISTA':
                return self._create_signal('BUY', symbol, rates[-1]['close'])
        
        return None
```

## BaseStrategy

Todas las estrategias heredan de `BaseStrategy` que proporciona:

- `self.config`: Configuración del bot
- `self.logger`: Logger para la estrategia
- `self.risk_config`: Configuración de gestión de riesgo
- `self._create_signal()`: Método para crear señales estandarizadas

## Método analyze()

Debe retornar:
- `Dict` con señal de trading (usando `_create_signal()`)
- `None` si no hay señal

La señal debe contener:
- `action`: 'BUY' o 'SELL'
- `symbol`: Símbolo
- `price`: Precio de entrada
- `stop_loss`: (opcional)
- `take_profit`: (opcional)

