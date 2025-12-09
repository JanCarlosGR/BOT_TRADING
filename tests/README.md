# Tests Unitarios

Esta carpeta contiene los tests unitarios para el bot de trading.

## Estructura

```
tests/
├── __init__.py
├── README.md
├── test_candle_reader.py      # Tests para candle_reader
├── test_fvg_detector.py        # Tests para fvg_detector
├── test_news_checker.py        # Tests para news_checker
├── test_strategies.py          # Tests para estrategias
└── test_trading_hours.py       # Tests para trading_hours
```

## Ejecutar Tests

```bash
# Ejecutar todos los tests
python -m pytest tests/

# Ejecutar un test específico
python -m pytest tests/test_candle_reader.py

# Con cobertura
python -m pytest tests/ --cov=Base --cov-report=html
```

## Instalar pytest

```bash
pip install pytest pytest-cov
```

