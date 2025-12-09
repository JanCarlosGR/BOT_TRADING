# Documentación: Ejecutor de Órdenes MT5

## 📖 Introducción

El módulo `order_executor` proporciona una clase reutilizable para ejecutar órdenes de compra y venta en MetaTrader 5. Maneja automáticamente la normalización de precios, volúmenes, y validación de parámetros.

**Características principales:**
- ✅ Ejecutar órdenes de compra (BUY) y venta (SELL)
- ✅ Normalización automática de precios y volúmenes
- ✅ Soporte para stop loss y take profit
- ✅ Validación de parámetros
- ✅ Manejo de errores completo
- ✅ Cerrar posiciones existentes
- ✅ Obtener posiciones abiertas

---

## 🚀 Uso Básico

### Importar la clase

```python
from Base import OrderExecutor, OrderType, buy_order, sell_order, create_order_executor
```

### ¿Qué es OrderType?

`OrderType` es un enum que define los tipos de orden disponibles:
- `OrderType.BUY` - Orden de compra
- `OrderType.SELL` - Orden de venta

Se usa principalmente con el método `execute_order()`:

```python
from Base import OrderExecutor, OrderType

executor = OrderExecutor()
result = executor.execute_order(
    symbol='EURUSD',
    order_type=OrderType.BUY,  # o OrderType.SELL
    volume=0.1
)
```

---

## 📊 Estructura de Respuesta

Todas las funciones retornan un diccionario con el siguiente formato:

```python
{
    'success': bool,              # True si la orden se ejecutó exitosamente
    'order_ticket': int or None,  # Número de ticket de la orden
    'price': float or None,       # Precio de ejecución
    'volume': float or None,      # Volumen ejecutado
    'error': str or None,         # Código de error si hay problema
    'message': str                # Mensaje descriptivo
}
```

---

## 💡 Ejemplos de Uso

### Ejemplo 1: Compra simple (precio de mercado)

```python
from Base import OrderExecutor

executor = OrderExecutor()

# Comprar 0.1 lotes de EURUSD al precio de mercado
result = executor.buy('EURUSD', volume=0.1)

if result['success']:
    print(f"✅ Orden ejecutada: Ticket {result['order_ticket']}")
    print(f"   Precio: {result['price']}")
    print(f"   Volumen: {result['volume']}")
else:
    print(f"❌ Error: {result['message']}")
```

### Ejemplo 2: Venta con stop loss y take profit

```python
from Base import OrderExecutor

executor = OrderExecutor()

# Vender 0.1 lotes con SL y TP
current_price = 1.1000
stop_loss = 1.1050  # 50 pips arriba
take_profit = 1.0900  # 100 pips abajo

result = executor.sell(
    symbol='EURUSD',
    volume=0.1,
    stop_loss=stop_loss,
    take_profit=take_profit,
    comment="Venta con SL/TP"
)

if result['success']:
    print(f"✅ Venta ejecutada: {result['order_ticket']}")
else:
    print(f"❌ Error: {result['error']} - {result['message']}")
```

### Ejemplo 2.5: Orden con precio de entrada específico

```python
from Base import OrderExecutor

executor = OrderExecutor()

# Comprar a un precio específico (no precio de mercado)
precio_entrada = 1.1000  # Precio específico donde quieres entrar
stop_loss = 1.0950
take_profit = 1.1100

result = executor.buy(
    symbol='EURUSD',
    volume=0.1,
    price=precio_entrada,  # ✅ Precio específico (no None)
    stop_loss=stop_loss,
    take_profit=take_profit,
    comment="Entrada a precio específico"
)

if result['success']:
    print(f"✅ Orden ejecutada a precio {result['price']}")
else:
    print(f"❌ Error: {result['message']}")
```

### Ejemplo 3: Usar funciones de conveniencia

```python
from Base import buy_order, sell_order

# Compra rápida
result = buy_order('EURUSD', volume=0.1, stop_loss=1.0950, take_profit=1.1100)

# Venta rápida
result = sell_order('GBPUSD', volume=0.05, stop_loss=1.2800, take_profit=1.2600)
```

### Ejemplo 4: Integración en estrategia

```python
from Base import OrderExecutor, can_trade_now, detect_fvg
from strategies import BaseStrategy
import numpy as np
from typing import Optional, Dict

class TradingStrategy(BaseStrategy):
    def __init__(self, config: Dict):
        super().__init__(config)
        self.executor = OrderExecutor()
        self.volume = config.get('risk_management', {}).get('volume', 0.1)
    
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        # 1. Verificar noticias
        can_trade, reason, _ = can_trade_now(symbol)
        if not can_trade:
            return None
        
        # 2. Detectar FVG
        fvg = detect_fvg(symbol, 'H4')
        if not fvg or not fvg['fvg_filled_completely']:
            return None
        
        # 3. Ejecutar orden según señal
        current_price = rates[-1]['close']
        
        if fvg['exit_direction'] == 'ALCISTA':
            # Señal de compra
            result = self.executor.buy(
                symbol=symbol,
                volume=self.volume,
                stop_loss=fvg['fvg_bottom'],
                take_profit=current_price + fvg['fvg_size'] * 2,
                comment="FVG Alcista"
            )
            
            if result['success']:
                self.logger.info(f"✅ Compra ejecutada: {result['order_ticket']}")
                return {'action': 'BUY_EXECUTED', 'ticket': result['order_ticket']}
        
        elif fvg['exit_direction'] == 'BAJISTA':
            # Señal de venta
            result = self.executor.sell(
                symbol=symbol,
                volume=self.volume,
                stop_loss=fvg['fvg_top'],
                take_profit=current_price - fvg['fvg_size'] * 2,
                comment="FVG Bajista"
            )
            
            if result['success']:
                self.logger.info(f"✅ Venta ejecutada: {result['order_ticket']}")
                return {'action': 'SELL_EXECUTED', 'ticket': result['order_ticket']}
        
        return None
```

---

## 🔧 Métodos Principales

### `OrderExecutor.buy()`

Ejecuta una orden de compra.

```python
result = executor.buy(
    symbol='EURUSD',
    volume=0.1,
    price=None,           # None = precio de mercado (ask)
    stop_loss=None,       # Opcional
    take_profit=None,     # Opcional
    comment=""            # Opcional
)
```

**Parámetros:**
- `symbol` (str): Símbolo a comprar
- `volume` (float): Volumen en lotes
- `price` (float, opcional): Precio de entrada. Si es None, usa precio de mercado (ask)
- `stop_loss` (float, opcional): Precio de stop loss
- `take_profit` (float, opcional): Precio de take profit
- `comment` (str, opcional): Comentario para la orden

---

### `OrderExecutor.sell()`

Ejecuta una orden de venta.

```python
result = executor.sell(
    symbol='EURUSD',
    volume=0.1,
    price=None,           # None = precio de mercado (bid)
    stop_loss=None,       # Opcional
    take_profit=None,     # Opcional
    comment=""            # Opcional
)
```

**Parámetros:**
- `symbol` (str): Símbolo a vender
- `volume` (float): Volumen en lotes
- `price` (float, opcional): Precio de entrada. Si es None, usa precio de mercado (bid)
- `stop_loss` (float, opcional): Precio de stop loss
- `take_profit` (float, opcional): Precio de take profit
- `comment` (str, opcional): Comentario para la orden

---

### `OrderExecutor.execute_order()`

Método genérico para ejecutar cualquier tipo de orden.

```python
from Base import OrderExecutor, OrderType

executor = OrderExecutor()

result = executor.execute_order(
    symbol='EURUSD',
    order_type=OrderType.BUY,  # o OrderType.SELL
    volume=0.1,
    price=None,
    stop_loss=1.0950,
    take_profit=1.1100,
    comment="Mi orden"
)
```

---

### `OrderExecutor.close_position()`

Cierra una posición existente por su ticket.

```python
result = executor.close_position(ticket=12345678)

if result['success']:
    print(f"✅ Posición {ticket} cerrada")
else:
    print(f"❌ Error: {result['message']}")
```

---

### `OrderExecutor.get_positions()`

Obtiene las posiciones abiertas.

```python
# Todas las posiciones
all_positions = executor.get_positions()

# Posiciones de un símbolo específico
eurusd_positions = executor.get_positions(symbol='EURUSD')

for pos in eurusd_positions:
    print(f"Ticket: {pos['ticket']}")
    print(f"Tipo: {pos['type']}")
    print(f"Volumen: {pos['volume']}")
    print(f"Profit: {pos['profit']}")
```

**Parámetros:**
- `symbol` (str, opcional): Filtrar por símbolo. Si es None, retorna todas las posiciones

**Retorno:**
Lista de diccionarios con información de cada posición:
```python
{
    'ticket': int,
    'symbol': str,
    'type': 'BUY' or 'SELL',
    'volume': float,
    'price_open': float,
    'price_current': float,
    'profit': float,
    'swap': float,
    'comment': str,
    'time': datetime
}
```

---

### `create_order_executor()`

Función de conveniencia para crear una instancia de `OrderExecutor`.

```python
from Base import create_order_executor

executor = create_order_executor()
result = executor.buy('EURUSD', volume=0.1)
```

**Returns:**
- `OrderExecutor`: Instancia del ejecutor de órdenes

**Nota:** Es equivalente a `OrderExecutor()`, pero puede ser útil para mantener consistencia con otras funciones de conveniencia.

---

## ⚙️ Características Automáticas

### Normalización de Precios

Los precios se normalizan automáticamente según los dígitos del símbolo:
- EURUSD (5 dígitos): `1.10000`
- XAUUSD (2 dígitos): `2000.50`

### Normalización de Volúmenes

Los volúmenes se ajustan automáticamente:
- Se redondean al `volume_step` del símbolo
- Se validan contra `volume_min` y `volume_max`
- Ejemplo: Si `volume_step = 0.01`, un volumen de `0.123` se convierte en `0.12`

### Precios de Mercado

Si no especificas `price`:
- **BUY**: Usa el precio `ask` (precio de compra)
- **SELL**: Usa el precio `bid` (precio de venta)

---

## ⚠️ Manejo de Errores

### Códigos de Error Comunes

- `MT5_NO_CONNECTED`: MT5 no está conectado
- `MT5_ERROR_XXXX`: Error de MT5 (ver código de error)
- `MT5_RETCODE_XXXX`: Código de retorno de MT5 (ver documentación MT5)
- `EXCEPTION`: Excepción no manejada

### Ejemplo de Manejo de Errores

```python
result = executor.buy('EURUSD', volume=0.1)

if not result['success']:
    error = result['error']
    message = result['message']
    
    if error == 'MT5_NO_CONNECTED':
        print("⚠️ Conecta MT5 primero")
    elif error == 'MT5_RETCODE_10004':
        print("⚠️ Requiere activación del símbolo")
    else:
        print(f"⚠️ Error: {error} - {message}")
```

---

## 🎯 Casos de Uso Comunes

### Caso 1: Orden simple sin SL/TP

```python
from Base import OrderExecutor

executor = OrderExecutor()
result = executor.buy('EURUSD', volume=0.1)

if result['success']:
    print(f"Orden ejecutada: {result['order_ticket']}")
```

### Caso 2: Orden con gestión de riesgo

```python
from Base import OrderExecutor

executor = OrderExecutor()
current_price = 1.1000
risk_pips = 50  # 50 pips de riesgo
reward_pips = 100  # 100 pips de ganancia

result = executor.buy(
    symbol='EURUSD',
    volume=0.1,
    price=None,  # Precio de mercado (o especifica un precio)
    stop_loss=current_price - (risk_pips * 0.0001),
    take_profit=current_price + (reward_pips * 0.0001)
)
```

### Caso 2.5: Orden con precio de entrada específico

```python
from Base import OrderExecutor

executor = OrderExecutor()

# Entrar a un precio específico (ej: límite de orden)
precio_objetivo = 1.0980  # Precio donde quieres entrar
stop_loss = 1.0930
take_profit = 1.1080

result = executor.buy(
    symbol='EURUSD',
    volume=0.1,
    price=precio_objetivo,  # ✅ Precio específico
    stop_loss=stop_loss,
    take_profit=take_profit,
    comment="Entrada límite"
)
```

### Caso 3: Verificar posiciones antes de operar

```python
from Base import OrderExecutor

executor = OrderExecutor()

# Verificar si ya hay posiciones abiertas
positions = executor.get_positions(symbol='EURUSD')

if len(positions) > 0:
    print(f"Ya hay {len(positions)} posición(es) abierta(s) en EURUSD")
    for pos in positions:
        print(f"  - Ticket: {pos['ticket']}, Profit: {pos['profit']}")
else:
    # No hay posiciones, podemos abrir una nueva
    result = executor.buy('EURUSD', volume=0.1)
```

### Caso 4: Cerrar todas las posiciones de un símbolo

```python
from Base import OrderExecutor

executor = OrderExecutor()

positions = executor.get_positions(symbol='EURUSD')

for pos in positions:
    result = executor.close_position(ticket=pos['ticket'])
    if result['success']:
        print(f"✅ Posición {pos['ticket']} cerrada")
```

---

## 🔗 Integración con Estrategias

### Ejemplo completo

```python
from Base import OrderExecutor, can_trade_now, detect_fvg
from strategies import BaseStrategy
import numpy as np
from typing import Optional, Dict

class AutoTradingStrategy(BaseStrategy):
    """Estrategia que ejecuta órdenes automáticamente"""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.executor = OrderExecutor()
        self.volume = config.get('risk_management', {}).get('volume', 0.1)
        self.max_positions = config.get('risk_management', {}).get('max_positions', 1)
    
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        # 1. Verificar noticias
        can_trade, reason, _ = can_trade_now(symbol)
        if not can_trade:
            self.logger.info(f"Bloqueado: {reason}")
            return None
        
        # 2. Verificar posiciones existentes
        positions = self.executor.get_positions(symbol=symbol)
        if len(positions) >= self.max_positions:
            self.logger.debug(f"Ya hay {len(positions)} posición(es) en {symbol}")
            return None
        
        # 3. Detectar señal
        fvg = detect_fvg(symbol, 'H4')
        if not fvg or not fvg['fvg_filled_completely'] or not fvg['exited_fvg']:
            return None
        
        # 4. Ejecutar orden
        current_price = rates[-1]['close']
        
        if fvg['exit_direction'] == 'ALCISTA':
            result = self.executor.buy(
                symbol=symbol,
                volume=self.volume,
                stop_loss=fvg['fvg_bottom'],
                take_profit=current_price + fvg['fvg_size'] * 2,
                comment="FVG Strategy"
            )
        elif fvg['exit_direction'] == 'BAJISTA':
            result = self.executor.sell(
                symbol=symbol,
                volume=self.volume,
                stop_loss=fvg['fvg_top'],
                take_profit=current_price - fvg['fvg_size'] * 2,
                comment="FVG Strategy"
            )
        else:
            return None
        
        # 5. Retornar resultado
        if result['success']:
            return {
                'action': 'ORDER_EXECUTED',
                'ticket': result['order_ticket'],
                'symbol': symbol,
                'type': fvg['exit_direction']
            }
        
        return None
```

---

## ⚠️ Consideraciones Importantes

1. **Conexión MT5**: Asegúrate de que MT5 esté conectado antes de ejecutar órdenes
2. **Volumen mínimo**: Cada símbolo tiene un volumen mínimo (ej: 0.01 lotes)
3. **Precios normalizados**: Los precios se normalizan automáticamente según los dígitos del símbolo
4. **Stop Loss/Take Profit**: Deben estar en el lado correcto según el tipo de orden
5. **Modo Demo vs Real**: Prueba primero en cuenta demo
6. **Gestión de riesgo**: Siempre usa stop loss y gestiona el volumen según tu riesgo

---

## 📋 Resumen de Funciones

| Función | Descripción | Uso Principal |
|---------|-------------|---------------|
| `OrderExecutor.buy()` | Ejecuta orden de compra | Estrategias |
| `OrderExecutor.sell()` | Ejecuta orden de venta | Estrategias |
| `OrderExecutor.execute_order()` | Método genérico | Avanzado |
| `OrderExecutor.close_position()` | Cierra posición | Gestión |
| `OrderExecutor.get_positions()` | Obtiene posiciones | Monitoreo |
| `buy_order()` | Función de conveniencia | Uso rápido |
| `sell_order()` | Función de conveniencia | Uso rápido |
| `create_order_executor()` | Crea instancia de OrderExecutor | Inicialización |
| `OrderType` | Enum con tipos de orden (BUY/SELL) | Tipado |

---

## 📞 Soporte

Para problemas o preguntas:
- Revisa los logs del bot
- Consulta la implementación en `Base/order_executor.py`
- Verifica que MT5 esté conectado y funcionando
- Asegúrate de tener permisos de trading en la cuenta

---

**Última actualización**: Diciembre 2025

