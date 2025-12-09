# Estrategias de Trading

Esta carpeta contiene las estrategias de trading del bot. Cada estrategia debe heredar de `BaseStrategy`.

## Estructura

```
strategies/
├── __init__.py
├── README.md
├── default_strategy.py      # Estrategia por defecto
├── rsi_strategy.py          # Ejemplo: Estrategia RSI
└── fvg_strategy.py          # Ejemplo: Estrategia basada en FVG
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

