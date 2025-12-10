# Estrategias de Trading

Esta carpeta contiene las estrategias de trading del bot. Cada estrategia debe heredar de `BaseStrategy`.

## Estructura

```
strategies/
├── __init__.py
├── README.md
├── default_strategy.py              # Estrategia por defecto
├── turtle_soup_fvg_strategy.py     # Estrategia activa: Turtle Soup H4 + FVG M1
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

