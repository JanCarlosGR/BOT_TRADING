# Guía de Uso: Sistema de Estrategias por Jornada

## 📖 Introducción

El sistema de estrategias por jornada permite configurar diferentes estrategias para diferentes horarios durante el día de trading. Esto es útil cuando quieres usar estrategias diferentes según las condiciones del mercado en diferentes momentos del día.

## 🚀 Configuración Básica

### Modo Simple (Retrocompatible)

Si no necesitas estrategias por jornada, simplemente deja `strategy_schedule.enabled = false`:

```yaml
strategy:
  name: "turtle_soup_fvg"

strategy_schedule:
  enabled: false  # Sistema de jornadas deshabilitado
```

### Modo Jornadas (Nuevo)

Para habilitar estrategias por jornada:

```yaml
strategy:
  name: "turtle_soup_fvg"  # Fallback si no hay sesión activa

strategy_schedule:
  enabled: true  # ✅ Habilitar sistema de jornadas
  timezone: "America/New_York"
  sessions:
    - name: "Sesión Mañana"
      start_time: "09:00"
      end_time: "12:00"
      strategy: "turtle_soup_fvg"
      description: "Estrategia Turtle Soup para sesión de mañana"
    
    - name: "Sesión Tarde"
      start_time: "12:00"
      end_time: "16:00"
      strategy: "default"
      description: "Estrategia por defecto para sesión de tarde"
    
    - name: "Sesión Noche"
      start_time: "16:00"
      end_time: "23:59"
      strategy: "turtle_soup_fvg"
      description: "Estrategia Turtle Soup para sesión nocturna"
```

## 📋 Parámetros de Configuración

### `strategy_schedule`

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `enabled` | boolean | Sí | Habilitar/deshabilitar sistema de jornadas |
| `timezone` | string | Sí | Zona horaria para los horarios (ej: "America/New_York") |
| `sessions` | list | Sí | Lista de sesiones/jornadas |

### `sessions[]` - Cada sesión

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `name` | string | Sí | Nombre descriptivo de la sesión |
| `start_time` | string | Sí | Hora de inicio (formato HH:MM) |
| `end_time` | string | Sí | Hora de fin (formato HH:MM) |
| `strategy` | string | Sí | Nombre de la estrategia a usar |
| `description` | string | No | Descripción opcional de la sesión |

## 💡 Ejemplos de Configuración

### Ejemplo 1: Dos Sesiones

```yaml
strategy_schedule:
  enabled: true
  timezone: "America/New_York"
  sessions:
    - name: "Sesión Europea"
      start_time: "09:00"
      end_time: "12:00"
      strategy: "turtle_soup_fvg"
      description: "Sesión de mercado europeo"
    
    - name: "Sesión Americana"
      start_time: "12:00"
      end_time: "16:00"
      strategy: "default"
      description: "Sesión de mercado americano"
```

### Ejemplo 2: Tres Sesiones con Diferentes Estrategias

```yaml
strategy_schedule:
  enabled: true
  timezone: "America/New_York"
  sessions:
    - name: "Apertura"
      start_time: "09:00"
      end_time: "11:00"
      strategy: "turtle_soup_fvg"
      description: "Estrategia agresiva para apertura"
    
    - name: "Medio Día"
      start_time: "11:00"
      end_time: "14:00"
      strategy: "default"
      description: "Estrategia conservadora para medio día"
    
    - name: "Cierre"
      start_time: "14:00"
      end_time: "16:00"
      strategy: "turtle_soup_fvg"
      description: "Estrategia agresiva para cierre"
```

### Ejemplo 3: Sesión que Cruza Medianoche

```yaml
strategy_schedule:
  enabled: true
  timezone: "America/New_York"
  sessions:
    - name: "Día"
      start_time: "09:00"
      end_time: "17:00"
      strategy: "turtle_soup_fvg"
    
    - name: "Noche"
      start_time: "17:00"
      end_time: "09:00"  # Cruza medianoche
      strategy: "default"
```

**Nota:** Las sesiones que cruzan medianoche están soportadas, pero se recomienda evitar solapamientos.

## ⚠️ Validaciones y Reglas

1. **No solapamientos**: Las sesiones no deben solaparse (se detectará y se mostrará advertencia)
2. **Estrategias válidas**: Las estrategias referenciadas deben estar registradas en `StrategyManager`
3. **Formato de hora**: Debe ser `HH:MM` (ej: "09:00", "16:30")
4. **Cobertura completa**: Se recomienda que las sesiones cubran todo el horario operativo

## 🔄 Comportamiento del Sistema

### Cambio Automático de Estrategia

El sistema cambia automáticamente de estrategia cuando:
- La hora actual entra en una nueva sesión
- Se detecta el cambio en el siguiente ciclo de análisis

### Logging

El sistema loguea:
- ✅ Cuando cambia de sesión
- ✅ Estrategia activa en cada análisis
- ⚠️ Advertencias si hay gaps en las sesiones
- ⚠️ Advertencias si hay solapamientos

### Ejemplo de Logs

```
📅 Sistema de jornadas activo - Sesión actual: 'Sesión Mañana' → Estrategia: 'turtle_soup_fvg'
🔄 Cambio de sesión: 'Sesión Mañana' → 'Sesión Tarde' | Estrategia: 'turtle_soup_fvg' → 'default'
Analizando mercado para 1 símbolo(s) con estrategia: default
```

## 🛠️ Uso Programático

Si necesitas usar el scheduler en tu código:

```python
from Base.strategy_scheduler import StrategyScheduler

# En tu código
scheduler = StrategyScheduler(config)

# Obtener estrategia actual
current_strategy = scheduler.get_current_strategy()

# Obtener información de sesión actual
session_info = scheduler.get_current_session_info()
if session_info:
    print(f"Sesión: {session_info['name']}")
    print(f"Estrategia: {session_info['strategy']}")

# Obtener próxima transición
next_change = scheduler.get_next_session_change()
if next_change:
    print(f"Próximo cambio: {next_change}")
```

## 📝 Notas Importantes

1. **Retrocompatibilidad**: Si `enabled = false`, el sistema usa `strategy.name` (comportamiento original)
2. **Timezone**: Asegúrate de usar la misma zona horaria que `trading_hours.timezone`
3. **Estrategias**: Las estrategias deben estar registradas en `StrategyManager` antes de usarlas
4. **Performance**: El cambio de estrategia es instantáneo y no afecta el rendimiento

## 🔍 Troubleshooting

### La estrategia no cambia

- Verifica que `strategy_schedule.enabled = true`
- Verifica que las sesiones estén correctamente configuradas
- Revisa los logs para ver qué sesión está activa

### Advertencia de solapamiento

- Revisa los horarios de las sesiones
- Asegúrate de que no se solapen
- Considera usar horarios exactos (ej: "12:00" para una, "12:01" para la otra)

### Estrategia no encontrada

- Verifica que la estrategia esté registrada en `StrategyManager`
- Revisa el nombre de la estrategia (case-sensitive)
- Usa los nombres exactos: "default", "turtle_soup_fvg", etc.

## 📚 Referencias

- Ver `Base/strategy_scheduler.py` para implementación
- Ver `bot_trading.py` para integración
- Ver `config.yaml` para ejemplos de configuración

