"""
Sistema Multi-Estrategia
Gestiona diferentes estrategias de trading
"""

import logging
from typing import Dict, Optional, Any
from datetime import datetime
import numpy as np


class StrategyManager:
    """Gestiona múltiples estrategias de trading"""
    
    def __init__(self, config: Dict):
        """
        Inicializa el gestor de estrategias
        
        Args:
            config: Configuración completa del bot
        """
        self.logger = logging.getLogger(__name__)
        self.config = config
        
        # Registrar estrategias disponibles
        from strategies.turtle_soup_fvg_strategy import TurtleSoupFVGStrategy
        from strategies.default_strategy import DefaultStrategy
        
        self.strategies = {
            'default': DefaultStrategy(config),
            'turtle_soup_fvg': TurtleSoupFVGStrategy(config),
            # Aquí se agregarán más estrategias
            # 'rsi_strategy': RSIStrategy(config),
            # 'moving_average': MovingAverageStrategy(config),
        }
        
        self.logger.info(f"Estrategias disponibles: {list(self.strategies.keys())}")
    
    def analyze(self, symbol: str, rates: np.ndarray, strategy_name: str) -> Optional[Dict]:
        """
        Analiza el mercado usando la estrategia especificada
        
        Args:
            symbol: Símbolo a analizar (ej: 'EURUSD')
            rates: Array de velas OHLCV de MT5
            strategy_name: Nombre de la estrategia a usar
            
        Returns:
            Dict con señal de trading o None si no hay señal
        """
        if strategy_name not in self.strategies:
            self.logger.error(f"Estrategia '{strategy_name}' no encontrada")
            return None
        
        strategy = self.strategies[strategy_name]
        return strategy.analyze(symbol, rates)
    
    def needs_intensive_monitoring(self, strategy_name: str) -> bool:
        """
        Verifica si la estrategia necesita monitoreo intensivo
        
        Args:
            strategy_name: Nombre de la estrategia
            
        Returns:
            True si necesita monitoreo intensivo, False si no
        """
        if strategy_name not in self.strategies:
            return False
        
        strategy = self.strategies[strategy_name]
        if hasattr(strategy, 'needs_intensive_monitoring'):
            return strategy.needs_intensive_monitoring()
        
        return False


class BaseStrategy:
    """Clase base para todas las estrategias"""
    
    def __init__(self, config: Dict):
        """Inicializa la estrategia base"""
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.risk_config = config.get('risk_management', {})
        # Inicializar OrderExecutor para verificar posiciones (se inicializa lazy cuando se necesita)
        self._order_executor = None
        # Inicializar DatabaseManager para guardar en BD (lazy initialization)
        self._db_manager = None
    
    def _get_order_executor(self):
        """Obtiene la instancia de OrderExecutor (lazy initialization)"""
        if self._order_executor is None:
            from Base.order_executor import OrderExecutor
            self._order_executor = OrderExecutor()
        return self._order_executor
    
    def _get_db_manager(self):
        """Obtiene la instancia de DatabaseManager (lazy initialization)"""
        if self._db_manager is None:
            from Base.database import DatabaseManager
            self._db_manager = DatabaseManager(self.config)
        return self._db_manager
    
    def save_order_to_db(self, ticket: int, symbol: str, order_type: str,
                         entry_price: float, volume: float, stop_loss: Optional[float] = None,
                         take_profit: Optional[float] = None, rr: Optional[float] = None,
                         comment: Optional[str] = None, extra_data: Optional[Dict] = None) -> bool:
        """
        Guarda una orden ejecutada en la base de datos
        
        Este método está disponible para todas las estrategias que heredan de BaseStrategy.
        La estrategia se detecta automáticamente del nombre de la clase.
        
        Args:
            ticket: Ticket de la orden en MT5
            symbol: Símbolo operado
            order_type: Tipo de orden (BUY, SELL)
            entry_price: Precio de entrada
            volume: Volumen en lotes
            stop_loss: Precio de stop loss (opcional)
            take_profit: Precio de take profit (opcional)
            rr: Risk/Reward ratio (opcional)
            comment: Comentario de la orden (opcional)
            extra_data: Datos adicionales en formato dict (opcional)
            
        Returns:
            True si se guardó exitosamente, False en caso contrario
        """
        try:
            db_manager = self._get_db_manager()
            if not db_manager.enabled:
                return False
            
            # Detectar nombre de estrategia desde el nombre de la clase
            strategy_name = self.__class__.__name__
            # Convertir CamelCase a snake_case y hacer lowercase
            strategy_name = strategy_name.replace('Strategy', '').lower()
            if 'turtlesoup' in strategy_name or 'turtle_soup' in strategy_name:
                strategy_name = 'turtle_soup_fvg'
            elif 'fvg' in strategy_name and 'turtle' not in strategy_name:
                strategy_name = 'fvg_strategy'
            elif 'default' in strategy_name:
                strategy_name = 'default'
            
            # Convertir order_type si es necesario (BULLISH/BEARISH -> BUY/SELL)
            if order_type == 'BULLISH':
                order_type = 'BUY'
            elif order_type == 'BEARISH':
                order_type = 'SELL'
            
            return db_manager.save_order(
                ticket=ticket,
                symbol=symbol,
                order_type=order_type,
                entry_price=entry_price,
                volume=volume,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy=strategy_name,
                rr=rr,
                comment=comment,
                extra_data=extra_data
            )
        except Exception as e:
            self.logger.error(f"Error al guardar orden en BD: {e}", exc_info=True)
            return False
    
    def _should_close_day_after_first_tp(self) -> bool:
        """
        Verifica si está habilitada la opción de cerrar el día después del primer TP
        
        Returns:
            True si está habilitado, False en caso contrario
        """
        risk_config = self.config.get('risk_management', {})
        return risk_config.get('close_day_on_first_tp', False)
    
    def _check_first_trade_tp_closure(self, symbol: str) -> bool:
        """
        Verifica si el primer trade del día cerró con TP y si debe cerrar el día operativo
        
        Args:
            symbol: Símbolo a verificar
            
        Returns:
            True si el día debe cerrarse (primer TP detectado), False si puede continuar
        """
        try:
            # Solo verificar si está habilitada la opción
            if not self._should_close_day_after_first_tp():
                return False
            
            # Solo aplicar si hay más de 1 trade permitido por día
            max_trades = self.risk_config.get('max_trades_per_day', 1)
            if max_trades <= 1:
                return False  # No aplica si solo se permite 1 trade
            
            db_manager = self._get_db_manager()
            if not db_manager.enabled:
                return False
            
            # Verificar si el primer trade del día cerró con TP
            # Detectar nombre de estrategia desde el nombre de la clase
            class_name = self.__class__.__name__
            if 'TurtleSoup' in class_name:
                strategy_name = 'turtle_soup_fvg'
            elif 'FVG' in class_name and 'Strategy' in class_name:
                strategy_name = 'fvg_strategy'
            elif 'Default' in class_name:
                strategy_name = 'default'
            else:
                # Intentar convertir CamelCase a snake_case
                strategy_name = class_name.replace('Strategy', '').lower()
                # Reemplazar mayúsculas con guión bajo
                import re
                strategy_name = re.sub(r'(?<!^)(?=[A-Z])', '_', strategy_name).lower()
            
            first_was_tp = db_manager.first_trade_closed_with_tp(strategy=strategy_name, symbol=symbol)
            
            if first_was_tp:
                self.logger.info(
                    f"[{symbol}] ✅ Primer trade del día cerró con TP - "
                    f"Cerrando día operativo (no se colocarán más órdenes hasta próxima sesión)"
                )
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"[{symbol}] Error al verificar cierre por primer TP: {e}", exc_info=True)
            return False
    
    def _has_open_positions(self, symbol: str) -> bool:
        """
        Verifica si hay posiciones abiertas para el símbolo dado
        
        Esta verificación usa la base de datos como fuente de verdad principal,
        y también verifica MT5 para sincronización. Una estrategia no puede colocar
        una nueva entrada mientras hay una posición activa en proceso.
        
        Args:
            symbol: Símbolo a verificar (ej: 'EURUSD')
            
        Returns:
            True si hay posiciones abiertas, False si no hay posiciones
        """
        try:
            # Primero verificar en base de datos (fuente de verdad)
            db_manager = self._get_db_manager()
            if db_manager.enabled:
                db_orders = db_manager.get_open_orders(symbol=symbol)
                if db_orders:
                    self.logger.info(
                        f"[{symbol}] ⏸️  Hay {len(db_orders)} orden(es) abierta(s) en BD - "
                        f"No se puede colocar nueva entrada hasta que se cierre(n)"
                    )
                    for order in db_orders:
                        self.logger.debug(
                            f"[{symbol}]    • Ticket: {order['ticket']}, "
                            f"Tipo: {order['order_type']}, Volumen: {order['volume']}, "
                            f"Precio: {order['entry_price']:.5f}"
                        )
                    return True
            
            # Si BD no está disponible o no hay órdenes, verificar MT5 directamente
            executor = self._get_order_executor()
            positions = executor.get_positions(symbol=symbol)
            has_positions = len(positions) > 0
            
            if has_positions:
                self.logger.info(
                    f"[{symbol}] ⏸️  Hay {len(positions)} posición(es) abierta(s) en MT5 - "
                    f"No se puede colocar nueva entrada hasta que se cierre(n)"
                )
                # Sincronizar BD con MT5
                if db_manager.enabled:
                    db_manager.sync_orders_with_mt5(positions)
                for pos in positions:
                    self.logger.debug(
                        f"[{symbol}]    • Ticket: {pos['ticket']}, "
                        f"Tipo: {pos['type']}, Volumen: {pos['volume']}, "
                        f"Precio: {pos['price_open']:.5f}"
                    )
            
            return has_positions
            
        except Exception as e:
            self.logger.error(f"[{symbol}] Error al verificar posiciones abiertas: {e}", exc_info=True)
            # En caso de error, retornar False para no bloquear innecesariamente
            return False
    
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        """
        Método abstracto para análisis de mercado
        
        Args:
            symbol: Símbolo a analizar
            rates: Array de velas OHLCV
            
        Returns:
            Dict con señal de trading o None
        """
        raise NotImplementedError("Las estrategias deben implementar el método analyze()")
    
    def _create_signal(self, action: str, symbol: str, price: float, 
                      stop_loss: float = None, take_profit: float = None,
                      timestamp: int = None) -> Dict:
        """
        Crea un diccionario de señal estandarizado
        
        Args:
            action: 'BUY' o 'SELL'
            symbol: Símbolo
            price: Precio de entrada
            stop_loss: Precio de stop loss (opcional)
            take_profit: Precio de take profit (opcional)
            timestamp: Timestamp de la señal (opcional)
            
        Returns:
            Dict con la señal
        """
        return {
            'action': action,
            'symbol': symbol,
            'price': price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'timestamp': timestamp or int(datetime.now().timestamp())
        }


class DefaultStrategy(BaseStrategy):
    """
    Estrategia por defecto (placeholder)
    Esta estrategia debe ser reemplazada por tus estrategias reales
    """
    
    def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
        """
        Análisis básico - placeholder para estrategia real
        
        Args:
            symbol: Símbolo a analizar
            rates: Array de velas OHLCV
            
        Returns:
            None (no genera señales por ahora)
        """
        if len(rates) < 2:
            return None
        
        # Ejemplo básico: obtener último precio
        last_candle = rates[-1]
        current_price = last_candle['close']
        
        self.logger.debug(f"{symbol} - Precio actual: {current_price}")
        
        # TODO: Implementar lógica de estrategia aquí
        # Por ahora retorna None (no hay señal)
        
        return None


# Aquí puedes agregar más estrategias heredando de BaseStrategy
# Ejemplo:
#
# class RSIStrategy(BaseStrategy):
#     def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
#         # Implementar lógica RSI
#         pass
#
# class MovingAverageStrategy(BaseStrategy):
#     def analyze(self, symbol: str, rates: np.ndarray) -> Optional[Dict]:
#         # Implementar lógica de medias móviles
#         pass

