# Logs

Esta carpeta contiene los archivos de log del bot de trading.

## Archivos de Log

- `trading_bot.log` - Log principal del bot con todos los eventos

## Configuración

Los logs se configuran en `bot_trading.py` y se guardan automáticamente en esta carpeta.

## Niveles de Log

Configurables en `config.yaml`:

```yaml
general:
  log_level: "INFO"  # DEBUG, INFO, WARNING, ERROR
```

## Rotación de Logs

Por defecto, los logs se acumulan en un solo archivo. Para implementar rotación:

1. Usar `RotatingFileHandler` en lugar de `FileHandler`
2. Configurar tamaño máximo y número de archivos de respaldo

## Limpieza

Los archivos `.log` están en `.gitignore` y no se suben al repositorio.

Para limpiar logs antiguos manualmente:

```bash
# Windows PowerShell
Remove-Item logs\*.log -Force

# Linux/Mac
rm logs/*.log
```

