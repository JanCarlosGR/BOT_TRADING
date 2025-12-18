# Estructura del Proyecto - Documentación Completa

## 📁 Estructura de Directorios

```
BOT OF TRADING/
│
├── 📄 bot_trading.py              # Bot principal - Punto de entrada
├── 📄 strategies.py               # Gestor de estrategias
├── 📄 trading_hours.py            # Gestión de horarios operativos
├── 📄 config.yaml                 # Configuración del bot
├── 📄 requirements.txt            # Dependencias Python
├── 📄 .gitignore                  # Archivos ignorados por Git
├── 📄 README.md                   # Documentación principal
├── 📄 PROJECT_STRUCTURE.md        # Este archivo
│
├── 📁 logs/                        # Archivos de log
│   ├── README.md                  # Documentación de logs
│   └── trading_bot.log            # (generado automáticamente)
│
├── 📁 tests/                       # Tests unitarios
│   ├── __init__.py
│   ├── README.md                  # Guía de tests
│   ├── test_candle_reader.py      # Tests para candle_reader
│   ├── test_fvg_detector.py        # Tests para fvg_detector
│   └── test_news_checker.py        # Tests para news_checker
│
├── 📁 strategies/                  # Estrategias de trading
│   ├── __init__.py
│   ├── README.md                  # Guía de estrategias
│   ├── default_strategy.py        # Estrategia por defecto
│   └── fvg_strategy.py            # Ejemplo: Estrategia FVG
│
└── 📁 Base/                        # Módulos reutilizables
    ├── __init__.py                # Exporta funciones principales
    ├── candle_reader.py           # Lector de velas
    ├── fvg_detector.py            # Detector de FVG
    ├── news_checker.py            # Verificador de noticias
    ├── order_executor.py          # Ejecutor de órdenes MT5
    └── Documentation/            # Documentación de módulos
        ├── CANDLE_READER_DOCS.md
        ├── FVG_DETECTOR_DOCS.md
        ├── NEWS_CHECKER_DOCS.md
        ├── ORDER_EXECUTOR_DOCS.md
        ├── TURTLE_SOUP_DETECTOR_DOCS.md
        ├── DATABASE_LOGGING_DOCS.md
        └── CRT_THEORY_DOCS.md
```

---

## 📂 Descripción de Carpetas y Archivos

### 🎯 Raíz del Proyecto

#### `bot_trading.py`
- **Propósito**: Bot principal, punto de entrada del sistema
- **Responsabilidades**:
  - Conexión a MT5
  - Gestión del ciclo de vida del bot
  - Coordinación de estrategias y horarios
  - Logging principal
- **Logs**: Se guardan en `logs/trading_bot.log`

#### `strategies.py`
- **Propósito**: Gestor de estrategias (StrategyManager) y clase base (BaseStrategy)
- **Responsabilidades**:
  - Registrar y gestionar estrategias disponibles
  - Proporcionar clase base para nuevas estrategias
  - Crear señales estandarizadas

#### `trading_hours.py`
- **Propósito**: Gestión de horarios operativos
- **Responsabilidades**:
  - Validar si está en horario de trading
  - Conversión de timezones
  - Control de horarios configurados

#### `config.yaml`
- **Propósito**: Configuración centralizada del bot
- **Contenido**:
  - Credenciales MT5
  - Símbolos a operar
  - Horarios operativos
  - Estrategia seleccionada
  - Nivel de log

---

### 📁 logs/

**Propósito**: Almacenar archivos de log del bot

**Contenido**:
- `trading_bot.log` - Log principal (generado automáticamente)
- `README.md` - Documentación sobre logs

**Características**:
- ✅ Se crea automáticamente si no existe
- ✅ Los archivos `.log` están en `.gitignore`
- ✅ Configuración de niveles de log en `config.yaml`

**Documentación**: [logs/README.md](logs/README.md)

---

### 📁 tests/

**Propósito**: Tests unitarios para validar funcionalidad

**Estructura**:
```
tests/
├── __init__.py
├── README.md                  # Guía de tests
├── test_candle_reader.py      # Tests para candle_reader
├── test_fvg_detector.py        # Tests para fvg_detector
└── test_news_checker.py        # Tests para news_checker
```

**Ejecutar tests**:
```bash
pip install pytest pytest-cov
pytest tests/
pytest tests/ --cov=Base --cov-report=html
```

**Documentación**: [tests/README.md](tests/README.md)

---

### 📁 strategies/

**Propósito**: Contener estrategias de trading individuales

**Estructura**:
```
strategies/
├── __init__.py
├── README.md                  # Guía de estrategias
├── default_strategy.py        # Estrategia por defecto
└── fvg_strategy.py            # Ejemplo: Estrategia FVG
```

**Uso**:
- Para proyectos pequeños: estrategias en `strategies.py`
- Para proyectos grandes: mover estrategias a esta carpeta
- Cada estrategia debe heredar de `BaseStrategy`

**Documentación**: [strategies/README.md](strategies/README.md)

---

### 📁 Base/

**Propósito**: Módulos reutilizables para cualquier estrategia

**Módulos**:

1. **`candle_reader.py`**
   - Función: `get_candle()`
   - Obtiene información de velas (OHLC, tipo, etc.)
   - Maneja conversión de timezones automáticamente

2. **`fvg_detector.py`**
   - Función: `detect_fvg()`
   - Detecta Fair Value Gaps (FVG) según metodología ICT
   - Verifica entrada/salida y llenado del FVG

3. **`news_checker.py`**
   - Funciones: `can_trade_now()`, `get_daily_news_summary()`, etc.
   - Verifica noticias económicas de alto impacto
   - Solo muestra noticias pendientes (futuras)

4. **`order_executor.py`**
   - Clase: `OrderExecutor`
   - Funciones: `buy_order()`, `sell_order()`
   - Ejecuta órdenes de compra y venta en MT5
   - Normaliza precios y volúmenes automáticamente
   - Soporta stop loss y take profit

**Importar**:
```python
from Base import get_candle, detect_fvg, can_trade_now, OrderExecutor
```

**Documentación**: Ver `Base/Documentation/`

---

## 🔄 Flujo de Datos

```
bot_trading.py
    ↓
StrategyManager (strategies.py)
    ↓
BaseStrategy.analyze()
    ↓
Módulos Base/ (candle_reader, fvg_detector, news_checker)
    ↓
MetaTrader5 / Investing.com
```

---

## 📝 Convenciones

### Nombres de Archivos
- **Snake_case** para archivos Python: `candle_reader.py`
- **UPPERCASE** para constantes: `HIGH_IMPACT = 3`
- **PascalCase** para clases: `BaseStrategy`, `FVGDetector`

### Imports
- **Relativos** dentro de `Base/`: `from .candle_reader import get_candle`
- **Absolutos** desde raíz: `from Base import get_candle`
- **Desde strategies**: `from strategies import BaseStrategy`

### Documentación
- Cada módulo tiene docstrings completos
- Documentación detallada en `Base/Documentation/`
- README.md en cada carpeta importante

---

## 🚀 Escalabilidad

### Para Proyectos Pequeños
- Estrategias en `strategies.py`
- Tests básicos en `tests/`
- Logs en `logs/`

### Para Proyectos Grandes
- Mover estrategias a `strategies/` (una por archivo)
- Agregar más tests en `tests/`
- Considerar subcarpetas en `Base/` si crece mucho
- Agregar `utils/` para funciones auxiliares

---

## 📚 Documentación Adicional

- **README.md** - Documentación principal del proyecto
- **Base/Documentation/** - Documentación de módulos reutilizables
- **logs/README.md** - Información sobre logs
- **tests/README.md** - Guía de tests
- **strategies/README.md** - Guía de estrategias

---

**Última actualización**: Diciembre 2025

