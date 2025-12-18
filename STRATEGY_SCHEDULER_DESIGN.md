# Diseño: Sistema de Estrategias por Jornada

## Objetivo
Permitir configurar diferentes estrategias para diferentes horarios/jornadas de trading durante el día.

## Estructura de Configuración Propuesta

```yaml
# Opción 1: Estrategia única (comportamiento actual - retrocompatible)
strategy:
  name: "turtle_soup_fvg"

# Opción 2: Estrategias por jornada (NUEVO)
strategy_schedule:
  enabled: true  # Habilitar sistema de jornadas
  timezone: "America/New_York"  # Zona horaria para los horarios
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

## Comportamiento

1. **Si `strategy_schedule.enabled = false` o no existe**: Usa `strategy.name` (comportamiento actual)
2. **Si `strategy_schedule.enabled = true`**: 
   - Determina la sesión actual según la hora
   - Usa la estrategia configurada para esa sesión
   - Cambia automáticamente cuando cambia la sesión

## Componentes Necesarios

### 1. StrategyScheduler (nuevo módulo)
- Determina qué estrategia usar según la hora actual
- Maneja transiciones entre sesiones
- Valida configuración

### 2. Modificaciones en StrategyManager
- Mantener compatibilidad con estrategia única
- Soporte para múltiples estrategias activas

### 3. Modificaciones en bot_trading.py
- Usar StrategyScheduler en lugar de `config['strategy']['name']`
- Detectar cambios de sesión y loguear

## Validaciones

- Las sesiones no deben solaparse
- Debe cubrir todo el horario operativo
- Las estrategias referenciadas deben existir
- Horarios en formato HH:MM válidos

## Ejemplo de Uso

```python
# En bot_trading.py
scheduler = StrategyScheduler(self.config)
current_strategy = scheduler.get_current_strategy()  # Retorna nombre de estrategia
```

## Logging

- Log cuando cambia de sesión
- Log de estrategia activa en cada análisis
- Advertencias si hay gaps en las sesiones

