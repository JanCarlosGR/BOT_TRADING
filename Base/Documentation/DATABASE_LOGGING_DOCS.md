# Documentación: Sistema de Logging en Base de Datos

## 📖 Introducción

El sistema de logging en base de datos guarda automáticamente todos los logs del bot y las estrategias en una tabla SQL Server. Esto proporciona un historial completo y persistente de todas las operaciones, eventos y errores del sistema.

**Características principales:**
- ✅ Guardado automático de logs en SQL Server
- ✅ Extracción automática de símbolo y estrategia
- ✅ Configuración flexible (habilitar/deshabilitar)
- ✅ Soporte para datos adicionales (JSON)
- ✅ Filtrado por nivel de log

---

## 🗄️ Estructura de la Tabla `Logs`

La tabla `Logs` se crea automáticamente cuando el bot inicia por primera vez:

```sql
CREATE TABLE Logs (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    Level NVARCHAR(50) NOT NULL,           -- Nivel del log (INFO, WARNING, ERROR, DEBUG, etc.)
    LoggerName NVARCHAR(255),               -- Nombre del logger (módulo/clase)
    Message NVARCHAR(MAX) NOT NULL,         -- Mensaje completo del log
    Symbol NVARCHAR(50),                    -- Símbolo extraído automáticamente (ej: EURUSD)
    Strategy NVARCHAR(255),                 -- Estrategia detectada automáticamente
    ExtraData NVARCHAR(MAX),                -- Datos adicionales en formato JSON
    CreatedAt DATETIME NOT NULL DEFAULT GETDATE()  -- Fecha y hora del log
)
```

### Índices Creados

Para mejorar el rendimiento de las consultas:

```sql
CREATE INDEX IX_Logs_CreatedAt ON Logs(CreatedAt)
CREATE INDEX IX_Logs_Level ON Logs(Level)
CREATE INDEX IX_Logs_Symbol ON Logs(Symbol)
CREATE INDEX IX_Logs_Strategy ON Logs(Strategy)
```

---

## 📋 Campos de la Tabla

### `Id`
- **Tipo**: `INT IDENTITY(1,1)`
- **Descripción**: Identificador único auto-incremental
- **Ejemplo**: `1, 2, 3...`

### `Level`
- **Tipo**: `NVARCHAR(50) NOT NULL`
- **Descripción**: Nivel de severidad del log
- **Valores posibles**: 
  - `INFO` - Información general
  - `WARNING` - Advertencias
  - `ERROR` - Errores
  - `DEBUG` - Información de depuración
  - `CRITICAL` - Errores críticos
- **Ejemplo**: `"INFO"`, `"ERROR"`

### `LoggerName`
- **Tipo**: `NVARCHAR(255)`
- **Descripción**: Nombre del logger (módulo o clase que generó el log)
- **Ejemplos**: 
  - `"bot_trading"` - Logs del bot principal
  - `"TurtleSoupFVGStrategy"` - Logs de la estrategia Turtle Soup
  - `"Base.order_executor"` - Logs del ejecutor de órdenes
  - `"Base.position_monitor"` - Logs del monitor de posiciones

### `Message`
- **Tipo**: `NVARCHAR(MAX) NOT NULL`
- **Descripción**: Mensaje completo del log (formateado con timestamp y nivel)
- **Formato**: `"%(asctime)s - %(name)s - %(levelname)s - %(message)s"`
- **Ejemplo**: 
  ```
  "2025-01-15 14:30:25,123 - TurtleSoupFVGStrategy - INFO - [EURUSD] ✅ ORDEN EJECUTADA EXITOSAMENTE"
  ```

### `Symbol`
- **Tipo**: `NVARCHAR(50)`
- **Descripción**: Símbolo de trading extraído automáticamente del mensaje
- **Extracción**: Busca patrones como `[EURUSD]`, `[GBPUSD]`, etc.
- **Ejemplo**: `"EURUSD"`, `"GBPUSD"`, `"XAUUSD"`

### `Strategy`
- **Tipo**: `NVARCHAR(255)`
- **Descripción**: Nombre de la estrategia detectada automáticamente
- **Detección**: Basada en el nombre del logger
- **Valores posibles**:
  - `"turtle_soup_fvg"` - Si el logger contiene "TurtleSoup"
  - `"fvg_strategy"` - Si el logger contiene "FVG" y "Strategy"
  - `"default"` - Si el logger contiene "DefaultStrategy"
  - `NULL` - Si no se puede detectar

### `ExtraData`
- **Tipo**: `NVARCHAR(MAX)`
- **Descripción**: Datos adicionales en formato JSON (opcional)
- **Uso**: Para información estructurada adicional
- **Ejemplo**:
  ```json
  {
    "ticket": 12345678,
    "entry_price": 1.09500,
    "volume": 0.1,
    "custom_field": "valor"
  }
  ```

### `CreatedAt`
- **Tipo**: `DATETIME NOT NULL DEFAULT GETDATE()`
- **Descripción**: Fecha y hora exacta cuando se generó el log
- **Formato**: `YYYY-MM-DD HH:MM:SS.mmm`
- **Ejemplo**: `"2025-01-15 14:30:25.123"`

---

## 🔧 Configuración

El sistema de logging en BD se configura en `config.yaml`:

```yaml
# Configuración de base de datos
database:
  enabled: true  # Habilitar guardado en base de datos
  server: "18.224.8.184"
  database: "DbBotTrading"
  username: "csenterprise"
  password: "Med@s0ft7622"
  driver: "ODBC Driver 17 for SQL Server"

# Configuración general
general:
  log_level: "INFO"  # Nivel mínimo de log (DEBUG, INFO, WARNING, ERROR)
```

### Niveles de Log Guardados

Por defecto, solo se guardan logs de nivel **INFO** y superior:
- ✅ `INFO` - Guardado
- ✅ `WARNING` - Guardado
- ✅ `ERROR` - Guardado
- ✅ `CRITICAL` - Guardado
- ❌ `DEBUG` - No guardado (solo en archivo/consola)

Esto se puede ajustar modificando el parámetro `min_level` en `DatabaseLogHandler`.

---

## 🚀 Funcionamiento Automático

El sistema funciona automáticamente sin necesidad de código adicional:

### 1. Inicialización

Cuando el bot inicia:

```python
# En bot_trading.py
self.db_manager = DatabaseManager(self.config)
self._setup_database_logging()
```

### 2. Handler de Logging

Se crea un `DatabaseLogHandler` que:

1. Se agrega al root logger de Python
2. Intercepta todos los logs del sistema
3. Extrae información automáticamente (símbolo, estrategia)
4. Guarda en base de datos

### 3. Proceso de Guardado

```
Logger genera log
    ↓
DatabaseLogHandler.emit() intercepta
    ↓
Extrae símbolo del mensaje (ej: [EURUSD])
    ↓
Detecta estrategia del logger name
    ↓
DatabaseManager.save_log() guarda en BD
    ↓
Commit a la base de datos
```

---

## 📊 Ejemplos de Logs Guardados

### Ejemplo 1: Log de Orden Ejecutada

```python
self.logger.info(f"[{symbol}] ✅ ORDEN EJECUTADA EXITOSAMENTE")
```

**Registro en BD:**
- **Level**: `"INFO"`
- **LoggerName**: `"TurtleSoupFVGStrategy"`
- **Message**: `"2025-01-15 14:30:25 - TurtleSoupFVGStrategy - INFO - [EURUSD] ✅ ORDEN EJECUTADA EXITOSAMENTE"`
- **Symbol**: `"EURUSD"`
- **Strategy**: `"turtle_soup_fvg"`
- **ExtraData**: `NULL`

### Ejemplo 2: Log con Datos Adicionales

```python
self.logger.info(
    f"[{symbol}] 🎫 Ticket: {ticket}",
    extra={'extra_data': {'ticket': ticket, 'price': entry_price}}
)
```

**Registro en BD:**
- **Level**: `"INFO"`
- **Symbol**: `"EURUSD"`
- **ExtraData**: `{"ticket": 12345678, "price": 1.09500}`

### Ejemplo 3: Log de Error

```python
self.logger.error(f"[{symbol}] ❌ Error al ejecutar orden: {error}")
```

**Registro en BD:**
- **Level**: `"ERROR"`
- **LoggerName**: `"Base.order_executor"`
- **Symbol**: `"EURUSD"`
- **Strategy**: `NULL` (no se detecta estrategia en este logger)

---

## 🔍 Consultas Útiles

### Obtener todos los logs de hoy

```sql
SELECT * 
FROM Logs 
WHERE CAST(CreatedAt AS DATE) = CAST(GETDATE() AS DATE)
ORDER BY CreatedAt DESC
```

### Obtener logs de un símbolo específico

```sql
SELECT * 
FROM Logs 
WHERE Symbol = 'EURUSD'
ORDER BY CreatedAt DESC
```

### Obtener solo errores

```sql
SELECT * 
FROM Logs 
WHERE Level = 'ERROR'
ORDER BY CreatedAt DESC
```

### Obtener logs de una estrategia

```sql
SELECT * 
FROM Logs 
WHERE Strategy = 'turtle_soup_fvg'
ORDER BY CreatedAt DESC
```

### Contar logs por nivel

```sql
SELECT Level, COUNT(*) as Total
FROM Logs
GROUP BY Level
ORDER BY Total DESC
```

### Logs de errores de hoy con símbolo

```sql
SELECT Symbol, COUNT(*) as ErrorCount
FROM Logs
WHERE Level = 'ERROR' 
  AND CAST(CreatedAt AS DATE) = CAST(GETDATE() AS DATE)
  AND Symbol IS NOT NULL
GROUP BY Symbol
ORDER BY ErrorCount DESC
```

---

## 🎯 Extracción Automática

### Extracción de Símbolo

El handler busca patrones en el mensaje del log:

**Patrón**: `\[([A-Z]{6,12})\]`

**Ejemplos que se detectan**:
- `[EURUSD]` → `"EURUSD"`
- `[GBPUSD]` → `"GBPUSD"`
- `[XAUUSD]` → `"XAUUSD"`
- `[BTCUSD]` → `"BTCUSD"`

**Ejemplos que NO se detectan**:
- `EURUSD` (sin corchetes)
- `[EUR]` (muy corto)
- `[EURUSDX]` (muy largo)

### Detección de Estrategia

El handler analiza el nombre del logger:

| Contenido en LoggerName | Estrategia Detectada |
|-------------------------|---------------------|
| `"TurtleSoup"` | `"turtle_soup_fvg"` |
| `"FVG"` + `"Strategy"` | `"fvg_strategy"` |
| `"DefaultStrategy"` | `"default"` |
| Otros | `NULL` |

---

## ⚙️ Configuración Avanzada

### Cambiar Nivel Mínimo

Para guardar también logs de DEBUG, modificar en `bot_trading.py`:

```python
db_handler = DatabaseLogHandler(
    db_manager=self.db_manager,
    min_level=logging.DEBUG  # Ahora guarda también DEBUG
)
```

### Deshabilitar Extracción Automática

```python
db_handler = DatabaseLogHandler(
    db_manager=self.db_manager,
    extract_symbol=False,     # No extraer símbolos
    extract_strategy=False    # No detectar estrategias
)
```

---

## 🛠️ Troubleshooting

### Los logs no se guardan

1. **Verificar configuración**:
   ```yaml
   database:
     enabled: true  # Debe estar en true
   ```

2. **Verificar conexión a BD**:
   - Revisar logs del bot para mensajes de conexión
   - Verificar credenciales en `config.yaml`

3. **Verificar nivel de log**:
   - Los logs DEBUG no se guardan por defecto
   - Solo INFO y superior se guardan

### Los símbolos no se extraen

- Asegurarse de usar formato `[SYMBOL]` en los mensajes
- Ejemplo correcto: `self.logger.info(f"[{symbol}] Mensaje")`
- Ejemplo incorrecto: `self.logger.info(f"{symbol} Mensaje")`

### Los logs se duplican

- Esto es normal: los logs se guardan en archivo, consola Y base de datos
- Si no quieres duplicación, ajusta los handlers en `_setup_logging()`

---

## 📈 Mejores Prácticas

### 1. Usar Formato Consistente

```python
# ✅ Bueno - Símbolo se detecta automáticamente
self.logger.info(f"[{symbol}] ✅ Orden ejecutada")

# ❌ Evitar - Símbolo no se detecta
self.logger.info(f"{symbol} - Orden ejecutada")
```

### 2. Incluir Contexto

```python
# ✅ Bueno - Incluye información relevante
self.logger.info(
    f"[{symbol}] 🎯 Take Profit: {tp:.5f}",
    extra={'extra_data': {'take_profit': tp, 'entry': entry}}
)

# ❌ Menos útil - Falta contexto
self.logger.info("Take Profit alcanzado")
```

### 3. Niveles Apropiados

```python
# ✅ INFO - Operaciones normales
self.logger.info(f"[{symbol}] Orden ejecutada")

# ✅ WARNING - Situaciones inesperadas pero manejables
self.logger.warning(f"[{symbol}] Precio fuera de rango esperado")

# ✅ ERROR - Errores que requieren atención
self.logger.error(f"[{symbol}] Error al ejecutar orden: {error}")

# ✅ DEBUG - Información de depuración (no se guarda por defecto)
self.logger.debug(f"[{symbol}] Estado interno: {state}")
```

---

## 📝 Resumen

El sistema de logging en base de datos proporciona:

- ✅ **Persistencia**: Historial completo de logs
- ✅ **Búsqueda**: Consultas SQL para análisis
- ✅ **Extracción Automática**: Símbolos y estrategias detectados automáticamente
- ✅ **Configuración Flexible**: Fácil habilitar/deshabilitar
- ✅ **Rendimiento**: Índices para consultas rápidas
- ✅ **Escalabilidad**: Maneja grandes volúmenes de logs

**Todo funciona automáticamente** - No se requiere código adicional para usar el sistema de logging en base de datos.

