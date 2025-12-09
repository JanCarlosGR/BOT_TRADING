# Bot de Trading para MetaTrader 5

Bot de trading automatizado con soporte multi-estrategia, gestión de horarios operativos y conexión a MetaTrader 5.

**📚 Para documentación completa de la estructura del proyecto, consulta:** [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)

## Características

- ✅ Conexión a MetaTrader 5 con credenciales configurables
- ✅ Sistema multi-estrategia (fácil agregar nuevas estrategias)
- ✅ Gestión de horarios operativos (timezone configurable)
- ✅ Soporte para múltiples activos (EURUSD, GBPUSD, etc.)
- ✅ Sistema de logging completo
- ✅ Configuración mediante archivo YAML
- ✅ **Módulos reutilizables en `Base/`**:
  - 📊 Lector de velas (`candle_reader.py`)
  - 📈 Detector de FVG - Fair Value Gap (`fvg_detector.py`)
  - 📰 Verificador de noticias económicas (`news_checker.py`)
  - 💹 Ejecutor de órdenes MT5 (`order_executor.py`) - **NUEVO**

## Instalación

1. **Instalar Python 3.8 o superior**

2. **Instalar dependencias:**
```bash
pip install -r requirements.txt
```

3. **Configurar el archivo `config.yaml`:**
   - Agregar tus credenciales de MT5 (login, password, server)
   - Configurar los activos a operar
   - Establecer horario operativo
   - Seleccionar estrategia

## Configuración

Edita el archivo `config.yaml` con tus parámetros:

```yaml
mt5:
  login: 12345678
  password: "tu_password"
  server: "Broker-Server"

symbols:
  - "EURUSD"
  - "GBPUSD"

trading_hours:
  enabled: true
  start_time: "09:00"
  end_time: "13:00"
  timezone: "America/New_York"

strategy:
  name: "default"
```

## Uso

Ejecutar el bot:

```bash
python bot_trading.py
```

El bot:
- Se conectará a MT5 automáticamente
- Estará activo 24/7 pero solo analizará el mercado en el horario configurado
- Generará logs en `trading_bot.log` y en consola

## Estructura del Proyecto

```
.
├── bot_trading.py              # Bot principal
├── strategies.py               # Sistema de estrategias (gestor)
├── trading_hours.py            # Gestión de horarios
├── config.yaml                 # Archivo de configuración
├── requirements.txt            # Dependencias
├── README.md                   # Este archivo
├── .gitignore                  # Archivos ignorados por Git
├── logs/                       # 📁 Archivos de log
│   ├── .gitkeep
│   └── trading_bot.log         # (generado automáticamente)
├── tests/                      # 📁 Tests unitarios
│   ├── __init__.py
│   ├── README.md
│   ├── test_candle_reader.py
│   ├── test_fvg_detector.py
│   └── test_news_checker.py
├── strategies/                 # 📁 Estrategias (para crecimiento futuro)
│   ├── __init__.py
│   ├── README.md
│   ├── default_strategy.py
│   └── fvg_strategy.py         # Ejemplo de estrategia
└── Base/                       # 📁 Módulos reutilizables para estrategias
    ├── __init__.py             # Exporta funciones principales
    ├── candle_reader.py       # Lector de velas reutilizable
    ├── fvg_detector.py         # Detector de Fair Value Gap (FVG)
    ├── news_checker.py         # Verificador de noticias económicas
    └── Documentation/          # Documentación completa
        ├── CANDLE_READER_DOCS.md
        ├── FVG_DETECTOR_DOCS.md
        └── NEWS_CHECKER_DOCS.md
```

## Módulos Reutilizables (Base/)

El proyecto incluye módulos reutilizables en la carpeta `Base/` que pueden usarse en cualquier estrategia.

### 📊 1. Lector de Velas (`candle_reader.py`)

Función reutilizable para obtener información de velas de forma sencilla.

**📚 Documentación completa:** [Base/Documentation/CANDLE_READER_DOCS.md](Base/Documentation/CANDLE_READER_DOCS.md)

**Uso básico:**
```python
from Base import get_candle

# Vela actual M5
candle = get_candle('M5', 'ahora', 'EURUSD')
if candle:
    print(f"OPEN: {candle['open']}, HIGH: {candle['high']}")
    print(f"Tipo: {candle['type']}")  # ALCISTA o BAJISTA
```

**Ejemplos:**
```python
# Vela actual
candle = get_candle('M5', 'ahora', 'EURUSD')

# Vela H4 de las 1am NY
candle = get_candle('H4', '1am', 'EURUSD')

# Vela H4 de las 5am NY
candle = get_candle('H4', '5am', 'EURUSD')
```

---

### 📈 2. Detector de FVG (`fvg_detector.py`)

Detecta Fair Value Gaps (FVG) según la metodología ICT. Identifica si el precio está formando un FVG, si entró/salió, y si está llenando el gap.

**📚 Documentación completa:** [Base/Documentation/FVG_DETECTOR_DOCS.md](Base/Documentation/FVG_DETECTOR_DOCS.md)

**Uso básico:**
```python
from Base import detect_fvg

# Detectar FVG en H4
fvg = detect_fvg('EURUSD', 'H4')
if fvg:
    print(f"FVG {fvg['fvg_type']} detectado")
    print(f"Estado: {fvg['status']}")
    print(f"Entró: {fvg['entered_fvg']}, Salió: {fvg['exited_fvg']}")
```

**Características:**
- ✅ Detecta FVG alcista y bajista
- ✅ Verifica si el precio entró/salió del FVG
- ✅ Determina si el FVG está siendo llenado (parcial o completo)
- ✅ Soporta múltiples timeframes (M5, M15, H1, H4, D1, W1)

---

### 📰 3. Verificador de Noticias (`news_checker.py`)

Verifica noticias económicas de alto impacto que pueden afectar el trading. Solo muestra noticias **pendientes** (futuras, no pasadas).

**📚 Documentación completa:** [Base/Documentation/NEWS_CHECKER_DOCS.md](Base/Documentation/NEWS_CHECKER_DOCS.md)

**Uso básico:**
```python
from Base import can_trade_now, get_daily_news_summary

# Verificar si se puede operar (MÁS IMPORTANTE)
can_trade, reason, next_news = can_trade_now('EURUSD')
if can_trade:
    print(f"✅ {reason}")
    # Proceder con la estrategia
else:
    print(f"❌ {reason}")  # Bloqueado por noticias

# Obtener resumen del día
summary = get_daily_news_summary('EURUSD')
print(summary)
```

**Características:**
- ✅ Solo muestra noticias **pendientes** (futuras)
- ✅ Filtra noticias de alto impacto (3 estrellas)
- ✅ Determina si se puede operar en un momento dado
- ✅ Valida días operativos (excluye fines de semana y festivos)
- ✅ Resúmenes diarios, semanales y mensuales

---

### 💹 4. Ejecutor de Órdenes (`order_executor.py`)

Ejecuta órdenes de compra y venta en MT5 de forma segura y reutilizable.

**📚 Documentación completa:** [Base/Documentation/ORDER_EXECUTOR_DOCS.md](Base/Documentation/ORDER_EXECUTOR_DOCS.md)

**Uso básico:**
```python
from Base import OrderExecutor

executor = OrderExecutor()

# Compra simple
result = executor.buy('EURUSD', volume=0.1)
if result['success']:
    print(f"✅ Orden ejecutada: {result['order_ticket']}")

# Venta con stop loss y take profit
result = executor.sell(
    symbol='EURUSD',
    volume=0.1,
    stop_loss=1.0950,
    take_profit=1.1100
)
```

**Características:**
- ✅ Ejecuta órdenes de compra (BUY) y venta (SELL)
- ✅ Normalización automática de precios y volúmenes
- ✅ Soporte para stop loss y take profit
- ✅ Validación de parámetros
- ✅ Cerrar posiciones existentes
- ✅ Obtener posiciones abiertas

---

### 🔗 Importar desde Base

Todas las funciones principales están disponibles desde `Base`:

```python
# Forma recomendada
from Base import (
    get_candle,              # Lector de velas
    detect_fvg,              # Detector de FVG
    can_trade_now,           # Verificar noticias
    get_daily_news_summary,  # Resumen de noticias
    OrderExecutor,            # Ejecutor de órdenes
    buy_order,                # Función rápida de compra
    sell_order                # Función rápida de venta
)
```

## Agregar Nuevas Estrategias

1. Crear una nueva clase en `strategies.py` heredando de `BaseStrategy`
2. Implementar el método `analyze(symbol, rates)`
3. Registrar la estrategia en `StrategyManager.__init__()`
4. Actualizar `config.yaml` para usar la nueva estrategia

**Ejemplo básico:**
```python
from strategies import BaseStrategy
import numpy as np
from typing import Optional, Dict

class MiEstrategia(BaseStrategy):
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        # Tu lógica aquí
        if condicion_compra:
            return self._create_signal('BUY', symbol, current_price)
        return None
```

**Ejemplo usando módulos de Base (con ejecución de órdenes):**
```python
from Base import can_trade_now, detect_fvg, OrderExecutor
from strategies import BaseStrategy
import numpy as np
from typing import Optional, Dict

class EstrategiaCompleta(BaseStrategy):
    def __init__(self, config: Dict):
        super().__init__(config)
        self.executor = OrderExecutor()
        self.volume = config.get('risk_management', {}).get('volume', 0.1)
    
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        # 1. Verificar noticias primero
        can_trade, reason, next_news = can_trade_now(symbol)
        if not can_trade:
            self.logger.info(f"Bloqueado: {reason}")
            return None
        
        # 2. Detectar FVG
        fvg = detect_fvg(symbol, 'H4')
        if fvg and fvg['fvg_filled_completely'] and fvg['exited_fvg']:
            current_price = rates[-1]['close']
            
            # 3. Ejecutar orden según señal
            if fvg['exit_direction'] == 'ALCISTA':
                result = self.executor.buy(
                    symbol=symbol,
                    volume=self.volume,
                    stop_loss=fvg['fvg_bottom'],
                    take_profit=current_price + fvg['fvg_size'] * 2,
                    comment="FVG Strategy"
                )
                if result['success']:
                    return {'action': 'BUY_EXECUTED', 'ticket': result['order_ticket']}
            elif fvg['exit_direction'] == 'BAJISTA':
                result = self.executor.sell(
                    symbol=symbol,
                    volume=self.volume,
                    stop_loss=fvg['fvg_top'],
                    take_profit=current_price - fvg['fvg_size'] * 2,
                    comment="FVG Strategy"
                )
                if result['success']:
                    return {'action': 'SELL_EXECUTED', 'ticket': result['order_ticket']}
        
        return None
```

## Logs

Los logs se guardan en:
- **Archivo**: `logs/trading_bot.log` (carpeta `logs/`)
- **Consola**: Salida estándar

Niveles de log configurables en `config.yaml`:
- DEBUG: Información detallada
- INFO: Información general (recomendado)
- WARNING: Solo advertencias y errores
- ERROR: Solo errores

**Nota**: La carpeta `logs/` se crea automáticamente. Los archivos `.log` están en `.gitignore`.

**Ver documentación:** [logs/README.md](logs/README.md)

## Notas Importantes

- ⚠️ Asegúrate de tener MetaTrader 5 instalado y funcionando
- ⚠️ Las credenciales deben ser válidas y la cuenta debe estar activa
- ⚠️ El bot está en modo análisis por ahora (no ejecuta órdenes automáticamente)
- ⚠️ Prueba primero en cuenta demo antes de usar en cuenta real

## Tests

El proyecto incluye una estructura de tests en la carpeta `tests/`.

**Ejecutar tests:**
```bash
# Instalar pytest
pip install pytest pytest-cov

# Ejecutar todos los tests
pytest tests/

# Con cobertura
pytest tests/ --cov=Base --cov-report=html
```

**Ver documentación:** [tests/README.md](tests/README.md)

## Estrategias

Las estrategias están organizadas en `strategies.py` (gestor) y la carpeta `strategies/` (para crecimiento futuro).

**Crear nueva estrategia:** Ver [strategies/README.md](strategies/README.md)

## Próximos Pasos

- [ ] Implementar ejecución automática de órdenes
- [ ] Agregar gestión de riesgo avanzada
- [ ] Implementar backtesting
- [ ] Dashboard web para monitoreo

## Soporte

Para problemas o preguntas, revisa los logs en `trading_bot.log`.

