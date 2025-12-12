"""
Módulo para ejecutar órdenes en MetaTrader 5
Clase reutilizable para comprar y vender desde cualquier estrategia
"""

import MetaTrader5 as mt5
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime
from enum import Enum


class OrderType(Enum):
    """Tipos de orden disponibles"""
    BUY = "BUY"
    SELL = "SELL"


class OrderExecutor:
    """
    Clase reutilizable para ejecutar órdenes en MT5
    Permite comprar y vender con validación y manejo de errores
    """
    
    def __init__(self):
        """Inicializa el ejecutor de órdenes"""
        self.logger = logging.getLogger(__name__)
        self._verify_mt5_connection()
    
    def _verify_mt5_connection(self) -> bool:
        """
        Verifica que MT5 esté conectado y activo
        Intenta reconectar si la conexión se perdió
        
        Returns:
            True si está conectado, False si no se pudo conectar
        """
        # Verificar si MT5 está inicializado
        if not mt5.initialize():
            error = mt5.last_error()
            self.logger.warning(f"MT5 no está inicializado: {error}, intentando reinicializar...")
            # Intentar reinicializar
            mt5.shutdown()
            if not mt5.initialize():
                self.logger.error(f"No se pudo reinicializar MT5: {mt5.last_error()}")
                return False
        
        # Verificar que la conexión sigue activa
        account_info = mt5.account_info()
        if account_info is None:
            self.logger.warning("Conexión MT5 perdida - No se pudo obtener información de la cuenta")
            # Intentar reinicializar
            mt5.shutdown()
            if not mt5.initialize():
                self.logger.error(f"No se pudo reconectar MT5: {mt5.last_error()}")
                return False
            # Verificar nuevamente
            account_info = mt5.account_info()
            if account_info is None:
                self.logger.error("No se pudo reconectar a MT5 después del intento")
                return False
        
        self.logger.debug(f"MT5 conectado - Cuenta: {account_info.login}")
        return True
    
    def _get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Obtiene información del símbolo
        
        Args:
            symbol: Símbolo a verificar (ej: 'EURUSD')
            
        Returns:
            Dict con información del símbolo o None si hay error
        """
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            self.logger.error(f"Símbolo {symbol} no encontrado en MT5")
            return None
        
        if not symbol_info.visible:
            # Intentar habilitar el símbolo
            if not mt5.symbol_select(symbol, True):
                self.logger.error(f"No se pudo habilitar el símbolo {symbol}")
                return None
        
        return {
            'name': symbol_info.name,
            'bid': symbol_info.bid,
            'ask': symbol_info.ask,
            'spread': symbol_info.spread,
            'digits': symbol_info.digits,
            'point': symbol_info.point,
            'volume_min': symbol_info.volume_min,
            'volume_max': symbol_info.volume_max,
            'volume_step': symbol_info.volume_step,
            'trade_stops_level': symbol_info.trade_stops_level,  # Distancia mínima para SL/TP en puntos
        }
    
    def _normalize_volume(self, symbol: str, volume: float) -> Optional[float]:
        """
        Normaliza el volumen según las reglas del símbolo
        
        Args:
            symbol: Símbolo
            volume: Volumen deseado
            
        Returns:
            Volumen normalizado o None si hay error
        """
        symbol_info = self._get_symbol_info(symbol)
        if symbol_info is None:
            return None
        
        # Redondear al step más cercano
        volume_step = symbol_info['volume_step']
        normalized = round(volume / volume_step) * volume_step
        
        # Verificar límites
        if normalized < symbol_info['volume_min']:
            self.logger.warning(f"Volumen {normalized} menor al mínimo {symbol_info['volume_min']}")
            normalized = symbol_info['volume_min']
        elif normalized > symbol_info['volume_max']:
            self.logger.warning(f"Volumen {normalized} mayor al máximo {symbol_info['volume_max']}")
            normalized = symbol_info['volume_max']
        
        return normalized
    
    def _normalize_price(self, symbol: str, price: float) -> float:
        """
        Normaliza el precio según los dígitos del símbolo
        
        Args:
            symbol: Símbolo
            price: Precio a normalizar
            
        Returns:
            Precio normalizado
        """
        symbol_info = self._get_symbol_info(symbol)
        if symbol_info is None:
            return round(price, 5)  # Default a 5 decimales
        
        digits = symbol_info['digits']
        return round(price, digits)
    
    def _validate_and_adjust_stops(self, symbol: str, order_type: OrderType, 
                                   entry_price: float, stop_loss: Optional[float] = None,
                                   take_profit: Optional[float] = None) -> Tuple[Optional[float], Optional[float]]:
        """
        Valida y ajusta los niveles de Stop Loss y Take Profit según el stop level del broker
        
        Args:
            symbol: Símbolo
            order_type: Tipo de orden (BUY o SELL)
            entry_price: Precio de entrada
            stop_loss: Stop Loss propuesto
            take_profit: Take Profit propuesto
            
        Returns:
            Tuple con (stop_loss_ajustado, take_profit_ajustado)
        """
        symbol_info = self._get_symbol_info(symbol)
        if symbol_info is None:
            return stop_loss, take_profit
        
        stop_level = symbol_info.get('trade_stops_level', 0)  # Puntos mínimos requeridos
        point = symbol_info['point']
        min_distance = stop_level * point  # Distancia mínima en precio
        
        adjusted_sl = stop_loss
        adjusted_tp = take_profit
        
        if stop_loss:
            if order_type == OrderType.BUY:
                # Para compras: SL debe estar debajo del entry
                if stop_loss >= entry_price:
                    self.logger.warning(f"SL {stop_loss} debe estar debajo del entry {entry_price} para BUY")
                    adjusted_sl = None
                else:
                    # Verificar distancia mínima
                    distance = entry_price - stop_loss
                    if distance < min_distance:
                        # Ajustar SL para cumplir con la distancia mínima
                        adjusted_sl = self._normalize_price(symbol, entry_price - min_distance)
                        self.logger.info(f"SL ajustado de {stop_loss} a {adjusted_sl} para cumplir stop level ({stop_level} puntos)")
            else:  # SELL
                # Para ventas: SL debe estar arriba del entry
                if stop_loss <= entry_price:
                    self.logger.warning(f"SL {stop_loss} debe estar arriba del entry {entry_price} para SELL")
                    adjusted_sl = None
                else:
                    # Verificar distancia mínima
                    distance = stop_loss - entry_price
                    if distance < min_distance:
                        # Ajustar SL para cumplir con la distancia mínima
                        adjusted_sl = self._normalize_price(symbol, entry_price + min_distance)
                        self.logger.info(f"SL ajustado de {stop_loss} a {adjusted_sl} para cumplir stop level ({stop_level} puntos)")
        
        if take_profit:
            if order_type == OrderType.BUY:
                # Para compras: TP debe estar arriba del entry
                if take_profit <= entry_price:
                    self.logger.warning(f"TP {take_profit} debe estar arriba del entry {entry_price} para BUY")
                    adjusted_tp = None
                else:
                    # Verificar distancia mínima
                    distance = take_profit - entry_price
                    if distance < min_distance:
                        # Ajustar TP para cumplir con la distancia mínima
                        adjusted_tp = self._normalize_price(symbol, entry_price + min_distance)
                        self.logger.info(f"TP ajustado de {take_profit} a {adjusted_tp} para cumplir stop level ({stop_level} puntos)")
            else:  # SELL
                # Para ventas: TP debe estar debajo del entry
                if take_profit >= entry_price:
                    self.logger.warning(f"TP {take_profit} debe estar debajo del entry {entry_price} para SELL")
                    adjusted_tp = None
                else:
                    # Verificar distancia mínima
                    distance = entry_price - take_profit
                    if distance < min_distance:
                        # Ajustar TP para cumplir con la distancia mínima
                        adjusted_tp = self._normalize_price(symbol, entry_price - min_distance)
                        self.logger.info(f"TP ajustado de {take_profit} a {adjusted_tp} para cumplir stop level ({stop_level} puntos)")
        
        return adjusted_sl, adjusted_tp
    
    def _create_order_request(self, symbol: str, order_type: OrderType, volume: float,
                             price: Optional[float] = None, stop_loss: Optional[float] = None,
                             take_profit: Optional[float] = None, comment: str = "") -> Dict:
        """
        Crea un diccionario de solicitud de orden para MT5
        
        Args:
            symbol: Símbolo a operar
            order_type: Tipo de orden (BUY o SELL)
            volume: Volumen de la orden
            price: Precio de entrada (None para mercado)
            stop_loss: Precio de stop loss (opcional)
            take_profit: Precio de take profit (opcional)
            comment: Comentario para la orden
            
        Returns:
            Dict con la solicitud de orden
        """
        symbol_info = self._get_symbol_info(symbol)
        if symbol_info is None:
            raise ValueError(f"No se pudo obtener información del símbolo {symbol}")
        
        # Obtener precio actual si no se especifica
        if price is None:
            if order_type == OrderType.BUY:
                price = symbol_info['ask']  # Precio de compra
            else:
                price = symbol_info['bid']  # Precio de venta
        
        # Normalizar precio de entrada
        price = self._normalize_price(symbol, price)
        
        # Validar y ajustar Stop Loss y Take Profit según stop level del broker
        stop_loss, take_profit = self._validate_and_adjust_stops(
            symbol=symbol,
            order_type=order_type,
            entry_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        
        # Normalizar volumen
        volume = self._normalize_volume(symbol, volume)
        if volume is None:
            raise ValueError(f"No se pudo normalizar el volumen para {symbol}")
        
        # Determinar tipo de orden MT5
        if order_type == OrderType.BUY:
            order_type_mt5 = mt5.ORDER_TYPE_BUY
        else:
            order_type_mt5 = mt5.ORDER_TYPE_SELL
        
        # Crear solicitud
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type_mt5,
            "price": price,
            "deviation": 20,  # Desviación máxima en puntos
            "magic": 234000,  # Número mágico para identificar órdenes del bot
            "comment": comment or f"Bot Trading - {order_type.value}",
            "type_time": mt5.ORDER_TIME_GTC,  # Good Till Cancel
            "type_filling": mt5.ORDER_FILLING_IOC,  # Immediate or Cancel
        }
        
        # Agregar stop loss y take profit si se especifican
        if stop_loss:
            request["sl"] = stop_loss
        if take_profit:
            request["tp"] = take_profit
        
        return request
    
    def execute_order(self, symbol: str, order_type: OrderType, volume: float,
                     price: Optional[float] = None, stop_loss: Optional[float] = None,
                     take_profit: Optional[float] = None, comment: str = "") -> Dict:
        """
        Ejecuta una orden en MT5 (compra o venta)
        
        Args:
            symbol: Símbolo a operar (ej: 'EURUSD')
            order_type: Tipo de orden (OrderType.BUY o OrderType.SELL)
            volume: Volumen de la orden (en lotes)
            price: Precio de entrada (None para precio de mercado)
            stop_loss: Precio de stop loss (opcional)
            take_profit: Precio de take profit (opcional)
            comment: Comentario para la orden (opcional)
            
        Returns:
            Dict con información del resultado:
            {
                'success': bool,
                'order_ticket': int or None,
                'price': float or None,
                'volume': float or None,
                'error': str or None,
                'message': str
            }
        """
        try:
            # Verificar y reconectar MT5 si es necesario
            if not self._verify_mt5_connection():
                return {
                    'success': False,
                    'order_ticket': None,
                    'price': None,
                    'volume': None,
                    'error': 'MT5_NO_CONNECTED',
                    'message': 'MT5 no está conectado - Intenta verificar que MT5 esté abierto y la cuenta esté activa'
                }
            
            # Crear solicitud de orden
            request = self._create_order_request(
                symbol=symbol,
                order_type=order_type,
                volume=volume,
                price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                comment=comment
            )
            
            # Enviar orden
            result = mt5.order_send(request)
            
            if result is None:
                error_code = mt5.last_error()[0]
                error_msg = mt5.last_error()[1]
                self.logger.error(f"Error al enviar orden: {error_code} - {error_msg}")
                return {
                    'success': False,
                    'order_ticket': None,
                    'price': None,
                    'volume': None,
                    'error': f'MT5_ERROR_{error_code}',
                    'message': error_msg
                }
            
            # Verificar resultado
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                self.logger.warning(f"Orden no ejecutada: {result.retcode} - {result.comment}")
                return {
                    'success': False,
                    'order_ticket': result.order,
                    'price': result.price,
                    'volume': result.volume,
                    'error': f'MT5_RETCODE_{result.retcode}',
                    'message': result.comment
                }
            
            # Orden ejecutada exitosamente
            self.logger.info(
                f"✅ Orden {order_type.value} ejecutada: {symbol} | "
                f"Ticket: {result.order} | Volumen: {result.volume} | Precio: {result.price}"
            )
            
            return {
                'success': True,
                'order_ticket': result.order,
                'price': result.price,
                'volume': result.volume,
                'error': None,
                'message': f"Orden {order_type.value} ejecutada exitosamente"
            }
            
        except Exception as e:
            self.logger.error(f"Excepción al ejecutar orden: {e}", exc_info=True)
            return {
                'success': False,
                'order_ticket': None,
                'price': None,
                'volume': None,
                'error': 'EXCEPTION',
                'message': str(e)
            }
    
    def buy(self, symbol: str, volume: float, price: Optional[float] = None,
           stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
           comment: str = "") -> Dict:
        """
        Ejecuta una orden de compra (BUY)
        
        Args:
            symbol: Símbolo a comprar (ej: 'EURUSD')
            volume: Volumen en lotes
            price: Precio de entrada (None para mercado)
            stop_loss: Precio de stop loss (opcional)
            take_profit: Precio de take profit (opcional)
            comment: Comentario (opcional)
            
        Returns:
            Dict con resultado de la orden
        """
        return self.execute_order(
            symbol=symbol,
            order_type=OrderType.BUY,
            volume=volume,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment or f"BUY {symbol}"
        )
    
    def sell(self, symbol: str, volume: float, price: Optional[float] = None,
            stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
            comment: str = "") -> Dict:
        """
        Ejecuta una orden de venta (SELL)
        
        Args:
            symbol: Símbolo a vender (ej: 'EURUSD')
            volume: Volumen en lotes
            price: Precio de entrada (None para mercado)
            stop_loss: Precio de stop loss (opcional)
            take_profit: Precio de take profit (opcional)
            comment: Comentario (opcional)
            
        Returns:
            Dict con resultado de la orden
        """
        return self.execute_order(
            symbol=symbol,
            order_type=OrderType.SELL,
            volume=volume,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment or f"SELL {symbol}"
        )
    
    def close_position(self, ticket: int) -> Dict:
        """
        Cierra una posición existente por su ticket
        
        Args:
            ticket: Número de ticket de la posición a cerrar
            
        Returns:
            Dict con resultado del cierre
        """
        try:
            # Obtener información de la posición
            position = mt5.positions_get(ticket=ticket)
            if position is None or len(position) == 0:
                return {
                    'success': False,
                    'message': f'Posición con ticket {ticket} no encontrada',
                    'error': 'POSITION_NOT_FOUND'
                }
            
            position_info = position[0]
            symbol = position_info.symbol
            volume = position_info.volume
            order_type = OrderType.BUY if position_info.type == mt5.ORDER_TYPE_BUY else OrderType.SELL
            
            # Crear orden de cierre (opuesta a la posición)
            close_type = OrderType.SELL if order_type == OrderType.BUY else OrderType.BUY
            
            return self.execute_order(
                symbol=symbol,
                order_type=close_type,
                volume=volume,
                comment=f"Cerrar posición {ticket}"
            )
            
        except Exception as e:
            self.logger.error(f"Error al cerrar posición {ticket}: {e}", exc_info=True)
            return {
                'success': False,
                'message': str(e),
                'error': 'EXCEPTION'
            }
    
    def get_positions(self, symbol: Optional[str] = None) -> list:
        """
        Obtiene las posiciones abiertas
        
        Args:
            symbol: Filtrar por símbolo (opcional)
            
        Returns:
            Lista de posiciones abiertas
        """
        try:
            if symbol:
                positions = mt5.positions_get(symbol=symbol)
            else:
                positions = mt5.positions_get()
            
            if positions is None:
                return []
            
            result = []
            for pos in positions:
                result.append({
                    'ticket': pos.ticket,
                    'symbol': pos.symbol,
                    'type': 'BUY' if pos.type == mt5.ORDER_TYPE_BUY else 'SELL',
                    'volume': pos.volume,
                    'price_open': pos.price_open,
                    'price_current': pos.price_current,
                    'price_stop_loss': pos.sl,
                    'price_take_profit': pos.tp,
                    'profit': pos.profit,
                    'swap': pos.swap,
                    'comment': pos.comment,
                    'time': datetime.fromtimestamp(pos.time),
                })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error al obtener posiciones: {e}", exc_info=True)
            return []
    
    def modify_position_sl(self, ticket: int, new_stop_loss: float, new_take_profit: Optional[float] = None) -> Dict:
        """
        Modifica el stop loss (y opcionalmente take profit) de una posición abierta
        
        Args:
            ticket: Ticket de la posición a modificar
            new_stop_loss: Nuevo precio de stop loss
            new_take_profit: Nuevo precio de take profit (opcional, None para mantener el actual)
            
        Returns:
            Dict con resultado de la modificación
        """
        try:
            # Obtener información de la posición
            positions = mt5.positions_get(ticket=ticket)
            if positions is None or len(positions) == 0:
                return {
                    'success': False,
                    'message': f'Posición con ticket {ticket} no encontrada',
                    'error': 'POSITION_NOT_FOUND'
                }
            
            position = positions[0]
            symbol = position.symbol
            
            # Obtener información del símbolo
            symbol_info = self._get_symbol_info(symbol)
            if symbol_info is None:
                return {
                    'success': False,
                    'message': f'No se pudo obtener información del símbolo {symbol}',
                    'error': 'SYMBOL_INFO_ERROR'
                }
            
            # Usar TP actual si no se especifica uno nuevo
            if new_take_profit is None:
                new_take_profit = position.tp if position.tp > 0 else 0
            else:
                # Validar y ajustar TP
                new_take_profit, _ = self._validate_and_adjust_stops(
                    symbol=symbol,
                    order_type=OrderType.BUY if position.type == mt5.ORDER_TYPE_BUY else OrderType.SELL,
                    entry_price=position.price_open,
                    stop_loss=new_stop_loss,
                    take_profit=new_take_profit
                )
                if new_take_profit is None:
                    new_take_profit = position.tp if position.tp > 0 else 0
            
            # Validar y ajustar SL
            adjusted_sl, _ = self._validate_and_adjust_stops(
                symbol=symbol,
                order_type=OrderType.BUY if position.type == mt5.ORDER_TYPE_BUY else OrderType.SELL,
                entry_price=position.price_open,
                stop_loss=new_stop_loss,
                take_profit=new_take_profit
            )
            
            if adjusted_sl is None:
                return {
                    'success': False,
                    'message': f'Stop loss {new_stop_loss} inválido para posición {ticket}',
                    'error': 'INVALID_STOP_LOSS'
                }
            
            # Normalizar precios
            adjusted_sl = self._normalize_price(symbol, adjusted_sl)
            new_take_profit = self._normalize_price(symbol, new_take_profit) if new_take_profit > 0 else 0
            
            # Crear solicitud de modificación
            request = {
                'action': mt5.TRADE_ACTION_SLTP,
                'symbol': symbol,
                'position': ticket,
                'sl': adjusted_sl,
                'tp': new_take_profit if new_take_profit > 0 else None,
            }
            
            # Enviar solicitud
            result = mt5.order_send(request)
            
            if result is None:
                error_code = mt5.last_error()[0]
                error_msg = mt5.last_error()[1]
                self.logger.error(f"Error al modificar posición {ticket}: {error_code} - {error_msg}")
                return {
                    'success': False,
                    'message': error_msg,
                    'error': f'MT5_ERROR_{error_code}'
                }
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                self.logger.warning(f"Posición {ticket} no modificada: {result.retcode} - {result.comment}")
                return {
                    'success': False,
                    'message': result.comment,
                    'error': f'MT5_RETCODE_{result.retcode}'
                }
            
            self.logger.info(f"✅ Posición {ticket} modificada - SL: {adjusted_sl:.5f}, TP: {new_take_profit:.5f}")
            return {
                'success': True,
                'ticket': ticket,
                'stop_loss': adjusted_sl,
                'take_profit': new_take_profit,
                'message': 'Stop loss modificado exitosamente'
            }
            
        except Exception as e:
            self.logger.error(f"Error al modificar posición {ticket}: {e}", exc_info=True)
            return {
                'success': False,
                'message': str(e),
                'error': 'EXCEPTION'
            }


# Función global para facilitar el uso
def create_order_executor() -> OrderExecutor:
    """
    Crea una instancia de OrderExecutor
    
    Returns:
        OrderExecutor: Instancia del ejecutor de órdenes
    """
    return OrderExecutor()


# Funciones de conveniencia
def buy_order(symbol: str, volume: float, price: Optional[float] = None,
             stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
             comment: str = "") -> Dict:
    """
    Función de conveniencia para ejecutar una orden de compra
    
    Args:
        symbol: Símbolo a comprar
        volume: Volumen en lotes
        price: Precio de entrada (None para mercado)
        stop_loss: Precio de stop loss (opcional)
        take_profit: Precio de take profit (opcional)
        comment: Comentario (opcional)
        
    Returns:
        Dict con resultado de la orden
    """
    executor = OrderExecutor()
    return executor.buy(symbol, volume, price, stop_loss, take_profit, comment)


def sell_order(symbol: str, volume: float, price: Optional[float] = None,
              stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
              comment: str = "") -> Dict:
    """
    Función de conveniencia para ejecutar una orden de venta
    
    Args:
        symbol: Símbolo a vender
        volume: Volumen en lotes
        price: Precio de entrada (None para mercado)
        stop_loss: Precio de stop loss (opcional)
        take_profit: Precio de take profit (opcional)
        comment: Comentario (opcional)
        
    Returns:
        Dict con resultado de la orden
    """
    executor = OrderExecutor()
    return executor.sell(symbol, volume, price, stop_loss, take_profit, comment)

