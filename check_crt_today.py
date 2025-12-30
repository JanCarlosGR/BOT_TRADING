"""
Script para revisar qué CRT se cumplió hoy
Consulta la base de datos para ver qué tipo de CRT (Continuation, Revision, Extreme) se detectó y ejecutó hoy
"""

import yaml
import json
from datetime import datetime, date
from typing import Dict, List, Optional

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


def load_config(config_path: str = "config.yaml") -> Dict:
    """Carga la configuración desde archivo YAML"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"Archivo de configuración no encontrado: {config_path}")
    except yaml.YAMLError as e:
        raise ValueError(f"Error al leer configuración: {e}")


def connect_db(config: Dict):
    """Conecta a la base de datos"""
    db_config = config.get('database', {})
    if not db_config.get('enabled', False):
        print("[ERROR] Base de datos no esta habilitada en la configuracion")
        return None
    
    server = db_config.get('server', '')
    database = db_config.get('database', '')
    username = db_config.get('username', '')
    password = db_config.get('password', '')
    driver = db_config.get('driver', 'ODBC Driver 17 for SQL Server')
    
    try:
        if PYODBC_AVAILABLE:
            connection_string = (
                f"DRIVER={{{driver}}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"UID={username};"
                f"PWD={password};"
                f"TrustServerCertificate=yes;"
            )
            connection = pyodbc.connect(connection_string, timeout=10)
            print(f"[OK] Conectado a SQL Server: {server}/{database}")
            return connection
        
        elif PYMSSQL_AVAILABLE:
            connection = pymssql.connect(
                server=server,
                user=username,
                password=password,
                database=database,
                timeout=10
            )
            print(f"[OK] Conectado a SQL Server (pymssql): {server}/{database}")
            return connection
        
        else:
            print("[ERROR] No se encontro ningun driver de SQL Server. Instala 'pyodbc' o 'pymssql'")
            return None
            
    except Exception as e:
        print(f"[ERROR] Error al conectar a SQL Server: {e}")
        return None


def check_crt_from_orders(connection, today: date) -> List[Dict]:
    """
    Revisa qué CRT se cumplió hoy desde la tabla Orders
    Busca en el campo Comment y ExtraData
    """
    try:
        cursor = connection.cursor()
        
        # Consultar órdenes de hoy que tengan CRT en el comment o strategy
        query = """
            SELECT Ticket, Symbol, OrderType, Strategy, Comment, ExtraData, CreatedAt, Status, CloseReason
            FROM Orders 
            WHERE CONVERT(DATE, CreatedAt) = ?
              AND (Comment LIKE '%CRT%' OR Strategy LIKE '%crt%')
            ORDER BY CreatedAt DESC
        """
        
        cursor.execute(query, (today,))
        rows = cursor.fetchall()
        cursor.close()
        
        crt_orders = []
        for row in rows:
            ticket, symbol, order_type, strategy, comment, extra_data_json, created_at, status, close_reason = row
            
            # Determinar tipo de CRT
            crt_type = None
            if 'continuation' in strategy.lower() or 'continuación' in (comment or '').lower():
                crt_type = 'CONTINUATION'
            elif 'revision' in strategy.lower() or 'revisión' in (comment or '').lower():
                crt_type = 'REVISION'
            elif 'extreme' in strategy.lower() or 'extremo' in (comment or '').lower():
                crt_type = 'EXTREME'
            elif 'crt' in (comment or '').lower():
                # Intentar determinar desde extra_data
                if extra_data_json:
                    try:
                        extra_data = json.loads(extra_data_json)
                        if 'crt_continuation' in extra_data:
                            crt_type = 'CONTINUATION'
                        elif 'crt_revision' in extra_data:
                            crt_type = 'REVISION'
                        elif 'crt_extreme' in extra_data:
                            crt_type = 'EXTREME'
                    except:
                        pass
            
            crt_orders.append({
                'ticket': ticket,
                'symbol': symbol,
                'order_type': order_type,
                'strategy': strategy,
                'crt_type': crt_type,
                'comment': comment,
                'status': status,
                'close_reason': close_reason,
                'created_at': created_at
            })
        
        return crt_orders
        
    except Exception as e:
        print(f"❌ Error al consultar órdenes: {e}")
        return []


def check_crt_from_logs(connection, today: date) -> List[Dict]:
    """
    Revisa qué CRT se detectó hoy desde la tabla Logs
    Busca mensajes que mencionen CRT
    """
    try:
        cursor = connection.cursor()
        
        # Consultar logs de hoy que mencionen CRT
        query = """
            SELECT Level, LoggerName, Message, Symbol, Strategy, ExtraData, CreatedAt
            FROM Logs 
            WHERE CONVERT(DATE, CreatedAt) = ?
              AND (Message LIKE '%CRT%' OR Message LIKE '%Continuación%' OR Message LIKE '%Revisión%' OR Message LIKE '%Extremo%')
            ORDER BY CreatedAt DESC
        """
        
        cursor.execute(query, (today,))
        rows = cursor.fetchall()
        cursor.close()
        
        crt_logs = []
        for row in rows:
            level, logger_name, message, symbol, strategy, extra_data_json, created_at = row
            
            # Determinar tipo de CRT desde el mensaje
            crt_type = None
            message_lower = (message or '').lower()
            
            if 'continuación' in message_lower or 'continuation' in message_lower:
                crt_type = 'CONTINUATION'
            elif 'revisión' in message_lower or 'revision' in message_lower:
                crt_type = 'REVISION'
            elif 'extremo' in message_lower or 'extreme' in message_lower:
                crt_type = 'EXTREME'
            
            crt_logs.append({
                'level': level,
                'logger': logger_name,
                'message': message,
                'symbol': symbol,
                'strategy': strategy,
                'crt_type': crt_type,
                'created_at': created_at
            })
        
        return crt_logs
        
    except Exception as e:
        print(f"❌ Error al consultar logs: {e}")
        return []


def main():
    """Función principal"""
    import sys
    import io
    # Configurar stdout para UTF-8 en Windows
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    print("=" * 70)
    print("REVISION DE CRT DETECTADOS HOY")
    print("=" * 70)
    print()
    
    # Cargar configuración
    try:
        config = load_config()
    except Exception as e:
        print(f"[ERROR] Error al cargar configuracion: {e}")
        return
    
    # Conectar a BD
    connection = connect_db(config)
    if not connection:
        return
    
    # Obtener fecha de hoy
    today = date.today()
    print(f"📅 Fecha: {today.strftime('%Y-%m-%d')}")
    print()
    
    # Revisar desde Orders
    print("📊 Revisando órdenes ejecutadas hoy...")
    crt_orders = check_crt_from_orders(connection, today)
    
    if crt_orders:
        print(f"✅ Se encontraron {len(crt_orders)} orden(es) CRT ejecutada(s) hoy:")
        print()
        
        # Agrupar por tipo de CRT
        crt_types = {}
        for order in crt_orders:
            crt_type = order['crt_type'] or 'DESCONOCIDO'
            if crt_type not in crt_types:
                crt_types[crt_type] = []
            crt_types[crt_type].append(order)
        
        for crt_type, orders in crt_types.items():
            print(f"  📌 {crt_type}: {len(orders)} orden(es)")
            for order in orders:
                status_icon = "✅" if order['status'] == 'CLOSED' else "🔄"
                close_info = f" - Cerrado: {order['close_reason']}" if order['close_reason'] else ""
                print(f"     {status_icon} Ticket: {order['ticket']} | {order['symbol']} | {order['order_type']} | Status: {order['status']}{close_info}")
                print(f"        Creada: {order['created_at']}")
        print()
    else:
        print("⚠️  No se encontraron órdenes CRT ejecutadas hoy")
        print()
    
    # Revisar desde Logs
    print("📋 Revisando logs de detección de CRT hoy...")
    crt_logs = check_crt_from_logs(connection, today)
    
    if crt_logs:
        print(f"✅ Se encontraron {len(crt_logs)} log(s) de CRT detectado(s) hoy:")
        print()
        
        # Agrupar por tipo de CRT
        crt_types_logs = {}
        for log in crt_logs:
            crt_type = log['crt_type'] or 'DESCONOCIDO'
            if crt_type not in crt_types_logs:
                crt_types_logs[crt_type] = []
            crt_types_logs[crt_type].append(log)
        
        for crt_type, logs in crt_types_logs.items():
            print(f"  📌 {crt_type}: {len(logs)} detección(es)")
            for log in logs[:5]:  # Mostrar máximo 5 por tipo
                print(f"     [{log['level']}] {log['symbol'] or 'N/A'}: {log['message'][:80]}...")
            if len(logs) > 5:
                print(f"     ... y {len(logs) - 5} más")
        print()
    else:
        print("⚠️  No se encontraron logs de detección de CRT hoy")
        print()
    
    # Resumen
    print("=" * 70)
    print("📊 RESUMEN")
    print("=" * 70)
    
    all_crt_types = set()
    if crt_orders:
        for order in crt_orders:
            if order['crt_type']:
                all_crt_types.add(order['crt_type'])
    
    if crt_logs:
        for log in crt_logs:
            if log['crt_type']:
                all_crt_types.add(log['crt_type'])
    
    if all_crt_types:
        print(f"✅ CRT detectado(s) hoy: {', '.join(sorted(all_crt_types))}")
    else:
        print("⚠️  No se detectaron CRT hoy")
    
    print()
    
    # Cerrar conexión
    try:
        connection.close()
    except:
        pass


if __name__ == "__main__":
    main()

