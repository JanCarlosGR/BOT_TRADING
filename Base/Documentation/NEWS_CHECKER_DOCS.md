# Documentación: Verificador de Noticias Económicas

## 📖 Introducción

El módulo `news_checker` proporciona funciones reutilizables para verificar noticias económicas de alto impacto que pueden afectar el trading. Utiliza web scraping del calendario económico de Investing.com para obtener información en tiempo real sobre eventos económicos importantes.

**Características principales:**
- ✅ Obtiene noticias de alto impacto (3 estrellas) del calendario económico
- ✅ **Solo muestra noticias PENDIENTES (futuras, no pasadas)**
- ✅ Filtra noticias por moneda (USD, EUR, etc.)
- ✅ Determina si se puede operar en un momento dado
- ✅ Valida días operativos (excluye fines de semana y festivos)
- ✅ Proporciona resúmenes diarios, semanales y mensuales
- ✅ Maneja timezones correctamente (NY time)

---

## 🚀 Uso Básico

### Importar las funciones

```python
from Base.news_checker import (
    can_trade_now,
    get_daily_news_summary,
    validate_trading_day,
    check_high_impact_news_calendar
)
```

---

## 📊 Estructura de Datos de Noticias

Cada noticia retornada es un diccionario con la siguiente estructura:

```python
{
    'time': datetime,              # Fecha y hora de la noticia (timezone NY)
    'time_str': str,                # Fecha y hora como string
    'currency': str,                # Moneda afectada (ej: 'USD', 'EUR')
    'title': str,                   # Título del evento (ej: 'Non-Farm Payrolls')
    'impact': int,                  # Nivel de impacto (0-3 estrellas)
    'impact_level': int,             # Nivel de impacto (alias de 'impact')
    'is_holiday': bool,              # True si es un día festivo
    'actual': str,                  # Valor actual (si está disponible)
    'forecast': str,                 # Valor pronosticado (si está disponible)
    'previous': str                  # Valor anterior (si está disponible)
}
```

---

## 💡 Funciones Principales

### 1. `can_trade_now()` - Verificar si se puede operar

**Función más importante para estrategias.** Determina si se puede operar en este momento basado en las noticias próximas.

**Nota importante:** Esta función solo considera noticias PENDIENTES (futuras), no las que ya pasaron.

```python
from Base.news_checker import can_trade_now

# Verificar si se puede operar ahora
can_trade, reason, next_news = can_trade_now('EURUSD')

if can_trade:
    print(f"✅ {reason}")
    # Proceder con la estrategia
else:
    print(f"❌ {reason}")
    # Evitar operar
```

**Parámetros:**
- `symbol` (str): Símbolo a verificar (ej: 'EURUSD')
- `minutes_before` (int, opcional): Minutos antes de la noticia para evitar operar (default: 5)
- `minutes_after` (int, opcional): Minutos después de la noticia para verificar consecutivas (default: 5)
- `check_consecutive` (bool, opcional): Si True, verifica noticias consecutivas (default: True)

**Retorno:**
- `tuple`: `(can_trade: bool, reason: str, next_news: Dict or None)`

**Reglas de bloqueo:**
- ❌ No operar `minutes_before` minutos antes de una noticia
- ❌ Esperar `minutes_after` minutos después de una noticia
- ❌ Si hay noticias consecutivas (dentro de 30 minutos), seguir esperando

**Ejemplo completo:**

```python
from Base.news_checker import can_trade_now

symbol = 'EURUSD'
can_trade, reason, next_news = can_trade_now(symbol, minutes_before=5, minutes_after=5)

if can_trade:
    print(f"✅ Puedo operar: {reason}")
    if next_news:
        print(f"   Próxima noticia: {next_news['title']} a las {next_news['time']}")
    # Proceder con la estrategia
else:
    print(f"❌ No puedo operar: {reason}")
    if next_news:
        print(f"   Noticia bloqueante: {next_news['title']}")
    # Evitar operar
```

---

### 2. `get_daily_news_summary()` - Resumen de noticias del día

Obtiene un resumen formateado de las noticias de alto impacto del día.

**Nota importante:** Solo muestra noticias PENDIENTES (futuras), excluyendo las que ya pasaron.

```python
from Base.news_checker import get_daily_news_summary

# Obtener resumen de noticias de hoy
summary = get_daily_news_summary('EURUSD')
print(summary)
```

**Salida ejemplo:**
```
📅 Monday, December 08, 2025: 2 noticia(s) de alto impacto (3⭐):
  ⏰ 08:30 | USD | ⭐⭐⭐ Non-Farm Payrolls
  ⏰ 10:00 | EUR | ⭐⭐⭐ ECB Interest Rate Decision
```

**Parámetros:**
- `symbol` (str): Símbolo a verificar (ej: 'EURUSD')
- `date` (datetime, opcional): Fecha. Si es None, usa hoy

**Retorno:**
- `str`: Resumen formateado de noticias

**Nota:** Solo incluye noticias dentro del horario de trading (9 AM - 3 PM NY) y de alto impacto (3 estrellas).

---

### 3. `validate_trading_day()` - Validar día operativo

Verifica si un día es operativo (no es fin de semana ni día festivo).

```python
from Base.news_checker import validate_trading_day
from datetime import datetime
import pytz

ny_tz = pytz.timezone('America/New_York')
date = datetime(2025, 12, 25, tzinfo=ny_tz)  # Navidad

is_trading, reason, holidays = validate_trading_day(date)

if is_trading:
    print(f"✅ {reason}")
else:
    print(f"❌ {reason}")
    if holidays:
        print(f"   Festivos: {[h['title'] for h in holidays]}")
```

**Parámetros:**
- `date` (datetime, opcional): Fecha a validar. Si es None, usa la fecha actual

**Retorno:**
- `tuple`: `(is_trading_day: bool, reason: str, holidays: List[Dict])`

---

### 4. `check_high_impact_news_calendar()` - Obtener noticias próximas

Obtiene lista de noticias de alto impacto próximas.

**Nota importante:** Solo retorna noticias PENDIENTES (futuras), filtrando automáticamente las que ya pasaron.

```python
from Base.news_checker import check_high_impact_news_calendar

# Obtener noticias de las próximas 2 horas
news_list = check_high_impact_news_calendar('EURUSD', hours_ahead=2)

if news_list:
    print(f"⚠️  {len(news_list)} noticia(s) de alto impacto próximas:")
    for news in news_list:
        print(f"  📰 {news['title']} ({news['currency']}) - {news['time']}")
else:
    print("✅ No hay noticias de alto impacto próximas")
```

**Parámetros:**
- `symbol` (str): Símbolo a verificar (ej: 'EURUSD')
- `hours_ahead` (int, opcional): Horas adelante para buscar (default: 2)

**Retorno:**
- `List[Dict]`: Lista de noticias de alto impacto

---

### 5. `get_weekly_news()` - Noticias de la semana

Obtiene todas las noticias de alto impacto de una semana específica.

**Nota importante:** Solo retorna noticias PENDIENTES (futuras) dentro del rango de la semana.

```python
from Base.news_checker import get_weekly_news

# Noticias de esta semana
this_week = get_weekly_news('EURUSD', week='current')

# Noticias de la próxima semana
next_week = get_weekly_news('EURUSD', week='next')

# Noticias de la semana pasada
prev_week = get_weekly_news('EURUSD', week='previous')
```

**Parámetros:**
- `symbol` (str): Símbolo a verificar (ej: 'EURUSD')
- `min_impact` (int, opcional): Nivel mínimo de impacto (0-3). Default: 3
- `currencies` (List[str], opcional): Monedas a filtrar. Default: ['USD', 'EUR']
- `week` (str, opcional): 'current', 'next', o 'previous'. Default: 'current'

**Retorno:**
- `List[Dict]`: Lista de noticias de la semana ordenadas por fecha

---

### 6. `get_monthly_news()` - Noticias del mes

Obtiene todas las noticias de alto impacto de un mes específico.

**Nota importante:** Solo retorna noticias PENDIENTES (futuras), excluyendo las que ya pasaron.

```python
from Base.news_checker import get_monthly_news

# Noticias de diciembre 2025
december_news = get_monthly_news('EURUSD', month=12, year=2025)

# Noticias del mes actual
current_month = get_monthly_news('EURUSD')
```

**Parámetros:**
- `symbol` (str): Símbolo a verificar (ej: 'EURUSD')
- `month` (int, opcional): Mes (1-12). Si es None, usa el mes actual
- `year` (int, opcional): Año. Si es None, usa el año actual

**Retorno:**
- `List[Dict]`: Lista de noticias del mes ordenadas por fecha

---

### 7. `get_daily_news_list()` - Lista de noticias del día

Obtiene la lista de noticias del día (útil para notificaciones o procesamiento).

**Nota importante:** Solo retorna noticias PENDIENTES (futuras), excluyendo las que ya pasaron.

```python
from Base.news_checker import get_daily_news_list

# Obtener lista de noticias de hoy
news_list = get_daily_news_list('EURUSD')

for news in news_list:
    print(f"{news['time']} - {news['title']} ({news['currency']}) - {news['impact_level']}⭐")
```

**Parámetros:**
- `symbol` (str): Símbolo a verificar (ej: 'EURUSD')
- `date` (datetime, opcional): Fecha. Si es None, usa hoy

**Retorno:**
- `List[Dict]`: Lista de diccionarios con información de noticias de alto impacto

---

## 🎯 Casos de Uso Comunes

### Caso 1: Verificar antes de operar (Recomendado)

```python
from Base.news_checker import can_trade_now

def should_enter_trade(symbol: str) -> bool:
    """Verifica si se puede entrar a una operación"""
    can_trade, reason, next_news = can_trade_now(symbol, minutes_before=5, minutes_after=5)
    
    if not can_trade:
        print(f"❌ Bloqueado por noticias: {reason}")
        return False
    
    print(f"✅ Libre para operar: {reason}")
    return True

# Usar en estrategia
if should_enter_trade('EURUSD'):
    # Lógica de entrada
    pass
```

---

### Caso 2: Integración en estrategia

```python
from Base.news_checker import can_trade_now
from strategies import BaseStrategy
import numpy as np
from typing import Optional, Dict

class NewsAwareStrategy(BaseStrategy):
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        # Verificar noticias antes de analizar
        can_trade, reason, next_news = can_trade_now(symbol)
        
        if not can_trade:
            self.logger.info(f"Operación bloqueada: {reason}")
            return None
        
        # Continuar con análisis de la estrategia
        # ... tu lógica aquí ...
        
        return signal
```

---

### Caso 3: Mostrar resumen diario al inicio

```python
from Base.news_checker import get_daily_news_summary

def print_daily_summary(symbol: str):
    """Imprime resumen de noticias del día"""
    summary = get_daily_news_summary(symbol)
    print("\n" + "="*60)
    print(summary)
    print("="*60 + "\n")

# Al inicio del bot
print_daily_summary('EURUSD')
```

---

### Caso 4: Validar día operativo antes de iniciar

```python
from Base.news_checker import validate_trading_day

def is_trading_day() -> bool:
    """Verifica si hoy es un día operativo"""
    is_trading, reason, holidays = validate_trading_day()
    
    if not is_trading:
        print(f"❌ {reason}")
        if holidays:
            print(f"   Festivos: {[h['title'] for h in holidays]}")
        return False
    
    print(f"✅ {reason}")
    return True

# Al inicio del bot
if not is_trading_day():
    print("El bot no operará hoy (día no operativo)")
    exit(0)
```

---

### Caso 5: Monitoreo continuo de noticias

```python
from Base.news_checker import check_high_impact_news_calendar
import time
from datetime import datetime

def monitor_news(symbol: str, interval: int = 300):
    """Monitorea noticias cada X segundos"""
    while True:
        news_list = check_high_impact_news_calendar(symbol, hours_ahead=2)
        
        if news_list:
            print(f"\n[{datetime.now()}] ⚠️  {len(news_list)} noticia(s) próxima(s):")
            for news in news_list:
                time_until = (news['time'] - datetime.now(news['time'].tzinfo)).total_seconds() / 60
                print(f"  📰 {news['title']} en {time_until:.1f} minutos")
        else:
            print(f"[{datetime.now()}] ✅ Sin noticias próximas")
        
        time.sleep(interval)

# Usar (ejecutar en thread separado)
# monitor_news('EURUSD', 300)  # Cada 5 minutos
```

---

## ⚙️ Configuración y Parámetros

### Niveles de Impacto

- **0**: Todos los eventos (incluye holidays)
- **1**: Bajo impacto
- **2**: Impacto medio
- **3**: Alto impacto (recomendado para trading)

### Timezone

Todas las funciones trabajan con **timezone de New York (America/New_York)**:
- Horario de trading: 9:00 AM - 1:00 PM NY
- Noticias extendidas: Hasta 3:00 PM NY (para eventos importantes como FOMC)

### Monedas Soportadas

Por defecto, el módulo filtra noticias de:
- **USD** (Dólar estadounidense)
- **EUR** (Euro)
- **EU** (Eventos de la Unión Europea)

Puedes especificar otras monedas usando el parámetro `currencies`:

```python
# Solo noticias de GBP y JPY
news = scrape_investing_calendar('GBPJPY', currencies=['GBP', 'JPY'])
```

---

## 🔍 Funciones Avanzadas

### `scrape_investing_calendar()` - Función base

Función interna que hace el scraping del calendario económico. Normalmente no se usa directamente, pero está disponible para casos avanzados.

```python
from Base.news_checker import scrape_investing_calendar

# Obtener noticias con parámetros personalizados
news = scrape_investing_calendar(
    symbol='EURUSD',
    month=12,
    year=2025,
    hours_ahead=4,
    min_impact=3,
    currencies=['USD', 'EUR']
)
```

**Parámetros:**
- `symbol` (str): Símbolo a verificar
- `month` (int, opcional): Mes (1-12)
- `year` (int, opcional): Año
- `hours_ahead` (int, opcional): Horas adelante para buscar
- `min_impact` (int, opcional): Nivel mínimo de impacto (0-3). Default: 3
- `currencies` (List[str], opcional): Monedas a filtrar
- `week` (str, opcional): 'prev', 'current', o 'next'

**Retorno:**
- `List[Dict]`: Lista de noticias encontradas

---

## ⚠️ Consideraciones Importantes

1. **Web Scraping**: Este módulo hace scraping de Investing.com. Respeta los términos de uso y no abuses de las peticiones.

2. **Reintentos**: El módulo incluye lógica de reintentos (3 intentos) en caso de errores de conexión.

3. **Timezone**: Todas las fechas y horas están en timezone de New York. Asegúrate de convertir si necesitas otra zona horaria.

4. **Noticias de 3 estrellas**: Por defecto, solo se filtran noticias de alto impacto (3 estrellas). Esto es intencional para evitar ruido.

5. **Holidays**: Los días festivos se detectan pero no bloquean operaciones por sí solos (a menos que uses `validate_trading_day()`).

6. **Performance**: El scraping puede tomar 1-3 segundos. Considera cachear resultados si necesitas consultas frecuentes.

---

## 🔗 Integración con Estrategias

### Ejemplo completo de integración

```python
from Base.news_checker import can_trade_now, get_daily_news_summary
from Base.fvg_detector import detect_fvg
from strategies import BaseStrategy
import numpy as np
from typing import Optional, Dict

class FVGNewsStrategy(BaseStrategy):
    """Estrategia que combina FVG y verificación de noticias"""
    
    def __init__(self):
        super().__init__()
        # Mostrar resumen al inicio
        print(get_daily_news_summary('EURUSD'))
    
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        # 1. Verificar noticias primero
        can_trade, reason, next_news = can_trade_now(symbol)
        if not can_trade:
            self.logger.info(f"Bloqueado por noticias: {reason}")
            return None
        
        # 2. Detectar FVG
        fvg = detect_fvg(symbol, 'H4')
        if not fvg:
            return None
        
        # 3. Lógica de la estrategia
        if fvg['fvg_filled_completely'] and fvg['exited_fvg']:
            if fvg['exit_direction'] == 'ALCISTA':
                return self._create_signal('BUY', symbol, rates[-1]['close'])
            elif fvg['exit_direction'] == 'BAJISTA':
                return self._create_signal('SELL', symbol, rates[-1]['close'])
        
        return None
```

---

## 📋 Resumen de Funciones

| Función | Descripción | Uso Principal | Notas |
|---------|-------------|---------------|-------|
| `can_trade_now()` | Verifica si se puede operar | **Estrategias** | Solo noticias pendientes |
| `get_daily_news_summary()` | Resumen formateado del día | Inicio del bot | Solo noticias pendientes |
| `validate_trading_day()` | Valida día operativo | Inicio del bot | - |
| `check_high_impact_news_calendar()` | Noticias próximas | Monitoreo | Solo noticias pendientes |
| `get_weekly_news()` | Noticias de la semana | Planificación | Solo noticias pendientes |
| `get_monthly_news()` | Noticias del mes | Planificación | Solo noticias pendientes |
| `get_daily_news_list()` | Lista de noticias del día | Procesamiento | Solo noticias pendientes |
| `scrape_investing_calendar()` | Función base de scraping | Avanzado | Puede incluir pasadas |

**Nota:** Todas las funciones públicas (excepto `scrape_investing_calendar`) filtran automáticamente las noticias pasadas y solo muestran noticias PENDIENTES (futuras).

---

## 📞 Soporte

Para problemas o preguntas:
- Revisa los logs del bot
- Consulta la implementación en `Base/news_checker.py`
- Verifica que la conexión a Internet esté funcionando
- Asegúrate de que Investing.com esté accesible

---

## 🔄 Cambios Recientes

### Diciembre 2025 - Filtrado de Noticias Pasadas

**Cambio importante:** Todas las funciones ahora filtran automáticamente las noticias pasadas y solo muestran noticias PENDIENTES (futuras).

**Funciones afectadas:**
- `get_daily_news_summary()` - Solo muestra noticias pendientes del día
- `get_daily_news_list()` - Solo retorna noticias pendientes
- `check_high_impact_news_calendar()` - Solo retorna noticias pendientes
- `get_weekly_news()` - Solo retorna noticias pendientes de la semana
- `get_monthly_news()` - Solo retorna noticias pendientes del mes

**Lógica de filtrado:**
```python
# Todas las funciones verifican:
if news_time_ny > now_ny:  # Solo incluir si la noticia es FUTURA
    pending_news.append(news)
```

**Beneficios:**
- ✅ Solo ves noticias relevantes para decisiones futuras
- ✅ No hay confusión con noticias que ya pasaron
- ✅ Resultados más limpios y útiles
- ✅ Mejor para toma de decisiones en tiempo real

---

**Última actualización**: Diciembre 2025

