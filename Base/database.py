"""
Módulo de Base de Datos SQL Server
Maneja la conexión y operaciones de base de datos para guardar logs y órdenes
"""

import logging
from datetime import datetime, date
from typing import Dict, Optional, Any, List
import json

try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    try:
        import pymssql
        PYMSSQL_AVAILABLE = True
    except ImportError:
        PYMSSQL_AVAILABLE = False
    PYODBC_AVAILABLE = False


class DatabaseManager:
    """Gestor de conexión y operaciones con SQL Server"""
    
    @staticmethod
    def _json_serializer(obj):
        """
        Serializador JSON personalizado que maneja objetos datetime y date
        
        Args:
            obj: Objeto a serializar
            
        Returns:
            String serializado o lanza TypeError si no puede serializar
        """
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    def __init__(self, config: Dict):
        """
        Inicializa el gestor de base de datos
        
        Args:
            config: Configuración con credenciales de BD
        """
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.connection = None
        self._tables_created = False  # Flag para evitar verificaciones repetidas - SIEMPRE inicializar
        
        # Cargar configuración de base de datos
        db_config = config.get('database', {})
        self.enabled = db_config.get('enabled', False)
        self.server = db_config.get('server', '')
        self.database = db_config.get('database', '')
        self.username = db_config.get('username', '')
        self.password = db_config.get('password', '')
        self.driver = db_config.get('driver', 'ODBC Driver 17 for SQL Server')
        
        if self.enabled:
            if self._connect():
                # Crear tablas al inicializar (si no existen) - solo una vez
                self._create_logs_table()
                self._create_orders_table()
                self._tables_created = True
                self.logger.info("✅ Tablas de base de datos verificadas/creadas")
    
    def _connect(self) -> bool:
        """
        Establece conexión con SQL Server
        
        Returns:
            True si la conexión fue exitosa, False en caso contrario
        """
        try:
            if not self.server or not self.database:
                self.logger.warning("Configuración de base de datos incompleta")
                return False
            
            # Intentar con pyodbc primero
            if PYODBC_AVAILABLE:
                connection_string = (
                    f"DRIVER={{{self.driver}}};"
                    f"SERVER={self.server};"
                    f"DATABASE={self.database};"
                    f"UID={self.username};"
                    f"PWD={self.password};"
                    f"TrustServerCertificate=yes;"
                )
                self.connection = pyodbc.connect(connection_string, timeout=10)
                self.logger.info(f"✅ Conectado a SQL Server: {self.server}/{self.database}")
                return True
            
            # Intentar con pymssql como alternativa
            elif PYMSSQL_AVAILABLE:
                self.connection = pymssql.connect(
                    server=self.server,
                    user=self.username,
                    password=self.password,
                    database=self.database,
                    timeout=10
                )
                self.logger.info(f"✅ Conectado a SQL Server (pymssql): {self.server}/{self.database}")
                return True
            
            else:
                self.logger.error(
                    "No se encontró ningún driver de SQL Server. "
                    "Instala 'pyodbc' o 'pymssql': pip install pyodbc"
                )
                return False
                
        except Exception as e:
            self.logger.error(f"Error al conectar a SQL Server: {e}", exc_info=True)
            self.connection = None
            return False
    
    def _ensure_connection(self) -> bool:
        """
        Verifica y restablece la conexión si es necesario
        
        Returns:
            True si hay conexión activa, False en caso contrario
        """
        if not self.enabled:
            return False
        
        try:
            if self.connection is None:
                return self._connect()
            
            # Verificar que la conexión sigue activa
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
            
        except Exception:
            # Conexión perdida, intentar reconectar
            self.logger.warning("Conexión de BD perdida, intentando reconectar...")
            try:
                self.connection.close()
            except:
                pass
            self.connection = None
            return self._connect()
    
    def save_log(self, level: str, logger_name: str, message: str, 
                 symbol: Optional[str] = None, strategy: Optional[str] = None,
                 extra_data: Optional[Dict] = None) -> bool:
        """
        Guarda un log en la base de datos
        
        Args:
            level: Nivel del log (INFO, ERROR, WARNING, DEBUG)
            logger_name: Nombre del logger
            message: Mensaje del log
            symbol: Símbolo relacionado (opcional)
            strategy: Estrategia relacionada (opcional)
            extra_data: Datos adicionales en formato dict (opcional)
            
        Returns:
            True si se guardó exitosamente, False en caso contrario
        """
        try:
            if not self._ensure_connection():
                return False
            
            cursor = self.connection.cursor()
            
            # Intentar insertar en tabla de logs (si existe)
            # Si la tabla no existe, simplemente retornar False sin error
            try:
                extra_json = json.dumps(extra_data, default=self._json_serializer) if extra_data else None
                
                query = """
                    INSERT INTO Logs (
                        Level, LoggerName, Message, Symbol, Strategy, 
                        ExtraData, CreatedAt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """
                
                cursor.execute(query, (
                    level,
                    logger_name,
                    message,
                    symbol,
                    strategy,
                    extra_json,
                    datetime.now()
                ))
                
                self.connection.commit()
                cursor.close()
                return True
                
            except Exception as e:
                # Si la tabla no existe o hay error, intentar crear la tabla
                if "Invalid object name" in str(e) or "does not exist" in str(e):
                    self.logger.debug(f"Tabla Logs no existe, intentando crear...")
                    if self._create_logs_table():
                        # Reintentar insertar
                        cursor.execute(query, (
                            level,
                            logger_name,
                            message,
                            symbol,
                            strategy,
                            extra_json,
                            datetime.now()
                        ))
                        self.connection.commit()
                        cursor.close()
                        return True
                else:
                    raise
                    
        except Exception as e:
            self.logger.error(f"Error al guardar log en BD: {e}", exc_info=True)
            try:
                self.connection.rollback()
            except:
                pass
            return False
    
    def save_order(self, ticket: int, symbol: str, order_type: str, 
                   entry_price: float, volume: float, stop_loss: Optional[float] = None,
                   take_profit: Optional[float] = None, strategy: Optional[str] = None,
                   rr: Optional[float] = None, comment: Optional[str] = None,
                   extra_data: Optional[Dict] = None) -> bool:
        """
        Guarda una orden ejecutada en la base de datos
        
        Args:
            ticket: Ticket de la orden en MT5
            symbol: Símbolo operado
            order_type: Tipo de orden (BUY, SELL)
            entry_price: Precio de entrada
            volume: Volumen en lotes
            stop_loss: Precio de stop loss (opcional)
            take_profit: Precio de take profit (opcional)
            strategy: Nombre de la estrategia (opcional)
            rr: Risk/Reward ratio (opcional)
            comment: Comentario de la orden (opcional)
            extra_data: Datos adicionales en formato dict (opcional)
            
        Returns:
            True si se guardó exitosamente, False en caso contrario
        """
        try:
            if not self._ensure_connection():
                return False
            
            cursor = self.connection.cursor()
            
            try:
                extra_json = json.dumps(extra_data, default=self._json_serializer) if extra_data else None
                
                query = """
                    INSERT INTO Orders (
                        Ticket, Symbol, OrderType, EntryPrice, Volume,
                        StopLoss, TakeProfit, Strategy, RiskReward, 
                        Comment, ExtraData, Status, CreatedAt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
                """
                
                cursor.execute(query, (
                    ticket,
                    symbol,
                    order_type,
                    entry_price,
                    volume,
                    stop_loss,
                    take_profit,
                    strategy,
                    rr,
                    comment,
                    extra_json,
                    datetime.now()
                ))
                
                self.connection.commit()
                cursor.close()
                return True
                
            except Exception as e:
                # Si la tabla no existe, intentar crearla
                if "Invalid object name" in str(e) or "does not exist" in str(e):
                    self.logger.debug(f"Tabla Orders no existe, intentando crear...")
                    if self._create_orders_table():
                        # Reintentar insertar
                        cursor.execute(query, (
                            ticket,
                            symbol,
                            order_type,
                            entry_price,
                            volume,
                            stop_loss,
                            take_profit,
                            strategy,
                            rr,
                            comment,
                            extra_json,
                            datetime.now()
                        ))
                        self.connection.commit()
                        cursor.close()
                        return True
                else:
                    raise
                    
        except Exception as e:
            self.logger.error(f"Error al guardar orden en BD: {e}", exc_info=True)
            try:
                self.connection.rollback()
            except:
                pass
            return False
    
    def _create_logs_table(self) -> bool:
        """Crea la tabla Logs si no existe"""
        try:
            cursor = self.connection.cursor()
            
            # Crear tabla
            create_table_query = """
                IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Logs]') AND type in (N'U'))
                BEGIN
                    CREATE TABLE Logs (
                        Id INT IDENTITY(1,1) PRIMARY KEY,
                        Level NVARCHAR(50) NOT NULL,
                        LoggerName NVARCHAR(255),
                        Message NVARCHAR(MAX) NOT NULL,
                        Symbol NVARCHAR(50),
                        Strategy NVARCHAR(255),
                        ExtraData NVARCHAR(MAX),
                        CreatedAt DATETIME NOT NULL DEFAULT GETDATE()
                    )
                END
            """
            cursor.execute(create_table_query)
            self.connection.commit()
            
            # Crear índices si no existen
            indexes = [
                "IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_Logs_CreatedAt') CREATE INDEX IX_Logs_CreatedAt ON Logs(CreatedAt)",
                "IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_Logs_Level') CREATE INDEX IX_Logs_Level ON Logs(Level)",
                "IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_Logs_Symbol') CREATE INDEX IX_Logs_Symbol ON Logs(Symbol)",
                "IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_Logs_Strategy') CREATE INDEX IX_Logs_Strategy ON Logs(Strategy)"
            ]
            
            for index_query in indexes:
                try:
                    cursor.execute(index_query)
                    self.connection.commit()
                except Exception as e:
                    # Si el índice ya existe, ignorar error
                    self.connection.rollback()
            
            cursor.close()
            # No loguear aquí - se loguea en __init__ solo cuando se crea por primera vez
            return True
        except Exception as e:
            self.logger.error(f"Error al crear tabla Logs: {e}", exc_info=True)
            return False
    
    def _create_orders_table(self) -> bool:
        """Crea la tabla Orders si no existe"""
        try:
            cursor = self.connection.cursor()
            
            # Crear tabla
            create_table_query = """
                IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Orders]') AND type in (N'U'))
                BEGIN
                    CREATE TABLE Orders (
                        Id INT IDENTITY(1,1) PRIMARY KEY,
                        Ticket BIGINT NOT NULL UNIQUE,
                        Symbol NVARCHAR(50) NOT NULL,
                        OrderType NVARCHAR(10) NOT NULL,
                        EntryPrice DECIMAL(18,5) NOT NULL,
                        Volume DECIMAL(18,2) NOT NULL,
                        StopLoss DECIMAL(18,5),
                        TakeProfit DECIMAL(18,5),
                        Strategy NVARCHAR(255),
                        RiskReward DECIMAL(10,2),
                        Comment NVARCHAR(500),
                        ExtraData NVARCHAR(MAX),
                        Status NVARCHAR(20) NOT NULL DEFAULT 'OPEN',
                        CloseReason NVARCHAR(50),  -- TP, SL, MANUAL, AUTO_CLOSE
                        ClosePrice DECIMAL(18,5),  -- Precio al que se cerró
                        ClosedAt DATETIME NULL,
                        CreatedAt DATETIME NOT NULL DEFAULT GETDATE()
                    )
                END
                ELSE
                BEGIN
                    -- Agregar columnas Status y ClosedAt si no existen (para tablas existentes)
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'[dbo].[Orders]') AND name = 'Status')
                    BEGIN
                        ALTER TABLE Orders ADD Status NVARCHAR(20) NOT NULL DEFAULT 'OPEN'
                    END
                    
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'[dbo].[Orders]') AND name = 'ClosedAt')
                    BEGIN
                        ALTER TABLE Orders ADD ClosedAt DATETIME NULL
                    END
                    
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'[dbo].[Orders]') AND name = 'CloseReason')
                    BEGIN
                        ALTER TABLE Orders ADD CloseReason NVARCHAR(50) NULL
                    END
                    
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'[dbo].[Orders]') AND name = 'ClosePrice')
                    BEGIN
                        ALTER TABLE Orders ADD ClosePrice DECIMAL(18,5) NULL
                    END
                END
            """
            cursor.execute(create_table_query)
            self.connection.commit()
            
            # Crear índices si no existen
            indexes = [
                "IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_Orders_Ticket') CREATE INDEX IX_Orders_Ticket ON Orders(Ticket)",
                "IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_Orders_Symbol') CREATE INDEX IX_Orders_Symbol ON Orders(Symbol)",
                "IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_Orders_Strategy') CREATE INDEX IX_Orders_Strategy ON Orders(Strategy)",
                "IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_Orders_CreatedAt') CREATE INDEX IX_Orders_CreatedAt ON Orders(CreatedAt)"
            ]
            
            for index_query in indexes:
                try:
                    cursor.execute(index_query)
                    self.connection.commit()
                except Exception as e:
                    # Si el índice ya existe, ignorar error
                    self.connection.rollback()
            
            cursor.close()
            # Solo loguear si realmente se creó la tabla, no cada vez que se verifica
            # El mensaje se muestra solo una vez al inicializar
            return True
        except Exception as e:
            self.logger.error(f"Error al crear tabla Orders: {e}", exc_info=True)
            return False
    
    def mark_order_as_closed(self, ticket: int, close_reason: Optional[str] = None, 
                             close_price: Optional[float] = None) -> bool:
        """
        Marca una orden como cerrada en la base de datos
        
        Args:
            ticket: Ticket de la orden a marcar como cerrada
            close_reason: Razón del cierre (TP, SL, MANUAL, AUTO_CLOSE) - opcional, se detecta automáticamente
            close_price: Precio al que se cerró - opcional, se detecta automáticamente
            
        Returns:
            True si se actualizó exitosamente, False en caso contrario
        """
        try:
            if not self._ensure_connection():
                return False
            
            # Obtener información de la orden desde BD para determinar close_reason si no se proporciona
            if close_reason is None or close_price is None:
                order_info = self._get_order_by_ticket(ticket)
                if order_info:
                    # Si no se proporcionó close_price, intentar obtenerlo de MT5
                    if close_price is None:
                        try:
                            import MetaTrader5 as mt5
                            deals = mt5.history_deals_get(ticket=ticket)
                            if deals and len(deals) > 0:
                                # Buscar el último deal de cierre
                                for deal in reversed(deals):
                                    if deal.entry == mt5.DEAL_ENTRY_OUT:
                                        close_price = float(deal.price)
                                        break
                        except:
                            pass
                    
                    # Si no se proporcionó close_reason, detectarlo comparando con TP/SL
                    if close_reason is None and close_price is not None and order_info:
                        entry_price = float(order_info.get('entry_price', 0))
                        tp = float(order_info.get('take_profit', 0)) if order_info.get('take_profit') else None
                        sl = float(order_info.get('stop_loss', 0)) if order_info.get('stop_loss') else None
                        order_type = order_info.get('order_type', '')
                        
                        # Detectar si cerró por TP o SL
                        if tp and sl:
                            # Calcular distancias
                            if order_type == 'BUY':
                                distance_to_tp = abs(close_price - tp) if tp else float('inf')
                                distance_to_sl = abs(close_price - sl) if sl else float('inf')
                            else:  # SELL
                                distance_to_tp = abs(tp - close_price) if tp else float('inf')
                                distance_to_sl = abs(sl - close_price) if sl else float('inf')
                            
                            # Si está más cerca del TP que del SL, probablemente cerró por TP
                            # Usamos un margen de tolerancia de 5 pips (0.0005 para pares de 5 decimales)
                            tolerance = 0.0005
                            if distance_to_tp < tolerance:
                                close_reason = 'TP'
                            elif distance_to_sl < tolerance:
                                close_reason = 'SL'
                            else:
                                close_reason = 'MANUAL'
                        else:
                            close_reason = 'MANUAL'
                else:
                    close_reason = close_reason or 'MANUAL'
            
            cursor = self.connection.cursor()
            
            query = """
                UPDATE Orders 
                SET Status = 'CLOSED', ClosedAt = ?, CloseReason = ?, ClosePrice = ?
                WHERE Ticket = ? AND Status = 'OPEN'
            """
            
            cursor.execute(query, (datetime.now(), close_reason, close_price, ticket))
            self.connection.commit()
            rows_affected = cursor.rowcount
            cursor.close()
            
            if rows_affected > 0:
                self.logger.debug(f"Orden {ticket} marcada como cerrada en BD: {close_reason} @ {close_price}")
                return True
            else:
                # La orden ya estaba cerrada o no existe
                return False
                
        except Exception as e:
            self.logger.error(f"Error al marcar orden {ticket} como cerrada: {e}", exc_info=True)
            try:
                self.connection.rollback()
            except:
                pass
            return False
    
    def _get_order_by_ticket(self, ticket: int) -> Optional[Dict]:
        """
        Obtiene información de una orden por su ticket
        
        Args:
            ticket: Ticket de la orden
            
        Returns:
            Dict con información de la orden o None si no existe
        """
        try:
            if not self._ensure_connection():
                return None
            
            self._create_orders_table()
            
            cursor = self.connection.cursor()
            query = "SELECT Ticket, Symbol, OrderType, EntryPrice, Volume, StopLoss, TakeProfit, Strategy FROM Orders WHERE Ticket = ?"
            cursor.execute(query, (ticket,))
            row = cursor.fetchone()
            cursor.close()
            
            if row:
                return {
                    'ticket': row[0],
                    'symbol': row[1],
                    'order_type': row[2],
                    'entry_price': row[3],
                    'volume': row[4],
                    'stop_loss': row[5],
                    'take_profit': row[6],
                    'strategy': row[7]
                }
            return None
        except Exception as e:
            self.logger.error(f"Error al obtener orden {ticket}: {e}", exc_info=True)
            return None
    
    def get_open_orders(self, symbol: Optional[str] = None, strategy: Optional[str] = None, today_only: bool = True) -> List[Dict]:
        """
        Obtiene las órdenes abiertas desde la base de datos
        
        Args:
            symbol: Filtrar por símbolo (opcional)
            strategy: Filtrar por estrategia (opcional)
            today_only: Si True, solo retorna órdenes del día actual (default: True)
            
        Returns:
            Lista de diccionarios con información de órdenes abiertas
        """
        try:
            if not self._ensure_connection():
                return []
            
            # Asegurar que las tablas existen (solo si no se han creado aún)
            if not getattr(self, '_tables_created', False):
                self._create_orders_table()
                self._tables_created = True
            
            cursor = self.connection.cursor()
            
            # Consultar órdenes con Status = 'OPEN' (case insensitive y sin espacios)
            # Filtrar explícitamente por Status = 'OPEN' y asegurar que no estén cerradas
            # IMPORTANTE: Solo incluir órdenes del día actual por defecto
            query = """
                SELECT Ticket, Symbol, OrderType, EntryPrice, Volume, StopLoss, TakeProfit, Strategy, Status, CreatedAt 
                FROM Orders 
                WHERE UPPER(LTRIM(RTRIM(Status))) = 'OPEN' 
                  AND (ClosedAt IS NULL OR ClosedAt = '')
            """
            params = []
            
            # Filtrar por fecha del día actual si today_only es True
            if today_only:
                today = date.today()
                query += " AND CONVERT(DATE, CreatedAt) = ?"
                params.append(today)
            
            if symbol:
                query += " AND Symbol = ?"
                params.append(symbol)
            
            if strategy:
                query += " AND Strategy = ?"
                params.append(strategy)
            
            query += " ORDER BY CreatedAt DESC"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            cursor.close()
            
            orders = []
            for row in rows:
                orders.append({
                    'ticket': row[0],
                    'symbol': row[1],
                    'order_type': row[2],
                    'entry_price': float(row[3]),
                    'volume': float(row[4]),
                    'stop_loss': float(row[5]) if row[5] else None,
                    'take_profit': float(row[6]) if row[6] else None,
                    'strategy': row[7],
                    'status': row[8] if len(row) > 8 else 'OPEN',  # Incluir Status en el resultado
                    'created_at': row[9] if len(row) > 9 else row[8]  # Ajustar índice si Status está incluido
                })
            
            return orders
            
        except Exception as e:
            self.logger.error(f"Error al obtener órdenes abiertas desde BD: {e}", exc_info=True)
            return []
    
    def count_trades_today(self, strategy: Optional[str] = None, symbol: Optional[str] = None) -> int:
        """
        Cuenta los trades ejecutados hoy desde la base de datos
        
        Args:
            strategy: Filtrar por estrategia (opcional)
            symbol: Filtrar por símbolo (opcional)
            
        Returns:
            Número de trades ejecutados hoy
        """
        try:
            if not self._ensure_connection():
                return 0
            
            # Asegurar que las tablas existen (solo si no se han creado aún)
            if not getattr(self, '_tables_created', False):
                self._create_orders_table()
                self._tables_created = True
            
            cursor = self.connection.cursor()
            
            # Obtener fecha de hoy (solo fecha, sin hora)
            today = date.today()
            
            # Usar CONVERT en lugar de CAST para mejor compatibilidad con SQL Server
            query = """
                SELECT COUNT(*) 
                FROM Orders 
                WHERE CONVERT(DATE, CreatedAt) = ?
            """
            params = [today]
            
            if strategy:
                query = query.replace("WHERE", "WHERE Strategy = ? AND")
                params.insert(0, strategy)
            
            if symbol:
                if strategy:
                    query = query.replace("AND CONVERT", "AND Symbol = ? AND CONVERT")
                    params.insert(-1, symbol)
                else:
                    query = query.replace("WHERE", "WHERE Symbol = ? AND")
                    params.insert(0, symbol)
            
            cursor.execute(query, params)
            count = cursor.fetchone()[0]
            cursor.close()
            
            return count
            
        except Exception as e:
            self.logger.error(f"Error al contar trades del día desde BD: {e}", exc_info=True)
            return 0
    
    def first_trade_closed_with_tp(self, strategy: Optional[str] = None, symbol: Optional[str] = None) -> bool:
        """
        Verifica si el primer trade del día cerró con Take Profit
        
        Args:
            strategy: Filtrar por estrategia (opcional)
            symbol: Filtrar por símbolo (opcional)
            
        Returns:
            True si el primer trade del día cerró con TP, False en caso contrario
        """
        try:
            if not self._ensure_connection():
                return False
            
            self._create_orders_table()
            
            cursor = self.connection.cursor()
            
            # Obtener fecha de hoy
            today = date.today()
            
            # Obtener la primera orden del día (ordenada por CreatedAt ASC)
            query = """
                SELECT TOP 1 CloseReason 
                FROM Orders 
                WHERE CONVERT(DATE, CreatedAt) = ?
                  AND UPPER(LTRIM(RTRIM(Status))) = 'CLOSED'
            """
            params = [today]
            
            if strategy:
                query = query.replace("WHERE", "WHERE Strategy = ? AND")
                params.insert(0, strategy)
            
            if symbol:
                if strategy:
                    query = query.replace("AND CONVERT", "AND Symbol = ? AND CONVERT")
                    params.insert(-1, symbol)
                else:
                    query = query.replace("WHERE", "WHERE Symbol = ? AND")
                    params.insert(0, symbol)
            
            query += " ORDER BY CreatedAt ASC"
            
            cursor.execute(query, params)
            row = cursor.fetchone()
            cursor.close()
            
            if row and row[0]:
                close_reason = str(row[0]).upper().strip()
                return close_reason == 'TP'
            
            # Si no hay trades cerrados hoy, retornar False
            return False
            
        except Exception as e:
            self.logger.error(f"Error al verificar primer trade con TP: {e}", exc_info=True)
            return False
    
    def sync_orders_with_mt5(self, mt5_positions: List[Dict]) -> Dict:
        """
        Sincroniza el estado de las órdenes en BD con las posiciones abiertas en MT5
        Marca como cerradas las órdenes que ya no están abiertas en MT5
        
        Args:
            mt5_positions: Lista de posiciones abiertas en MT5 (formato de get_positions)
            
        Returns:
            Dict con información de sincronización
        """
        try:
            if not self._ensure_connection():
                return {'synced': 0, 'closed': 0}
            
            # Asegurar que las tablas existen (solo si no se han creado aún)
            if not getattr(self, '_tables_created', False):
                self._create_orders_table()
                self._tables_created = True
            
            # Obtener tickets de posiciones abiertas en MT5
            mt5_tickets = {pos['ticket'] for pos in mt5_positions}
            
            # Obtener órdenes abiertas en BD
            db_open_orders = self.get_open_orders()
            db_tickets = {order['ticket'] for order in db_open_orders}
            
            # Encontrar órdenes que están abiertas en BD pero cerradas en MT5
            closed_in_mt5 = db_tickets - mt5_tickets
            
            closed_count = 0
            for ticket in closed_in_mt5:
                # Cuando se sincroniza con MT5, intentar detectar si cerró por TP o SL
                # Si no se puede detectar, marcar como MANUAL
                if self.mark_order_as_closed(ticket, close_reason=None, close_price=None):
                    closed_count += 1
            
            self.logger.debug(f"Sincronización BD-MT5: {closed_count} orden(es) marcada(s) como cerrada(s)")
            
            return {
                'synced': len(db_tickets),
                'closed': closed_count,
                'still_open': len(mt5_tickets & db_tickets)
            }
            
        except Exception as e:
            self.logger.error(f"Error al sincronizar órdenes con MT5: {e}", exc_info=True)
            return {'synced': 0, 'closed': 0}
    
    def close(self):
        """Cierra la conexión a la base de datos"""
        try:
            if self.connection:
                self.connection.close()
                self.connection = None
                self.logger.info("Conexión a BD cerrada")
        except Exception as e:
            self.logger.error(f"Error al cerrar conexión BD: {e}")

