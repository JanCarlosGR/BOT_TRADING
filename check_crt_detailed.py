"""
Script detallado para revisar qué CRT se cumplió hoy
Busca específicamente los mensajes de "COMPLETA" que indican detección real
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
        print("[ERROR] Base de datos no esta habilitada")
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
            return connection
        
        elif PYMSSQL_AVAILABLE:
            connection = pymssql.connect(
                server=server,
                user=username,
                password=password,
                database=database,
                timeout=10
            )
            return connection
        
        else:
            print("[ERROR] No se encontro driver de SQL Server")
            return None
            
    except Exception as e:
        print(f"[ERROR] Error al conectar: {e}")
        return None


def main():
    """Función principal"""
    import sys
    import io
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    print("=" * 70)
    print("ANALISIS DETALLADO: CRT CUMPLIDO HOY (30/12/2025)")
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
    
    today = date(2025, 12, 30)  # Específicamente 30 de diciembre
    print(f"Fecha analizada: {today.strftime('%Y-%m-%d')}")
    print()
    
    try:
        cursor = connection.cursor()
        
        # Buscar SOLO los mensajes de "COMPLETA" que indican detección real
        query = """
            SELECT Level, LoggerName, Message, Symbol, Strategy, ExtraData, CreatedAt
            FROM Logs 
            WHERE CONVERT(DATE, CreatedAt) = ?
              AND Message LIKE '%COMPLETA: CRT%'
            ORDER BY CreatedAt ASC
        """
        
        cursor.execute(query, (today,))
        rows = cursor.fetchall()
        cursor.close()
        
        if not rows:
            print("[INFO] No se encontraron mensajes de 'COMPLETA: CRT' hoy")
            print("       Buscando otros mensajes de deteccion...")
            print()
            
            # Buscar mensajes alternativos
            cursor = connection.cursor()
            query2 = """
                SELECT Level, LoggerName, Message, Symbol, Strategy, ExtraData, CreatedAt
                FROM Logs 
                WHERE CONVERT(DATE, CreatedAt) = ?
                  AND (
                      Message LIKE '%CRT de % detectado%'
                      OR Message LIKE '%CRT Continuación%'
                      OR Message LIKE '%CRT Revisión%'
                      OR Message LIKE '%CRT Extremo%'
                  )
                ORDER BY CreatedAt ASC
            """
            cursor.execute(query2, (today,))
            rows = cursor.fetchall()
            cursor.close()
        
        if rows:
            print(f"[OK] Se encontraron {len(rows)} deteccion(es) de CRT:")
            print()
            
            # Agrupar por tipo y hora
            detections_by_type = {}
            for row in rows:
                level, logger_name, message, symbol, strategy, extra_data_json, created_at = row
                
                # Determinar tipo de CRT
                crt_type = None
                message_lower = (message or '').lower()
                
                if 'continuación' in message_lower or 'continuation' in message_lower:
                    crt_type = 'CONTINUATION'
                elif 'revisión' in message_lower or 'revision' in message_lower:
                    crt_type = 'REVISION'
                elif 'extremo' in message_lower or 'extreme' in message_lower:
                    crt_type = 'EXTREME'
                
                if crt_type:
                    if crt_type not in detections_by_type:
                        detections_by_type[crt_type] = []
                    
                    detections_by_type[crt_type].append({
                        'time': created_at,
                        'symbol': symbol,
                        'message': message,
                        'full_message': message
                    })
            
            # Mostrar detecciones únicas (agrupar por hora)
            unique_detections = {}
            for crt_type, detections in detections_by_type.items():
                # Agrupar por hora (misma hora = misma detección)
                for det in detections:
                    hour_key = det['time'].strftime('%H:00')
                    key = f"{crt_type}_{hour_key}"
                    if key not in unique_detections:
                        unique_detections[key] = {
                            'type': crt_type,
                            'time': det['time'],
                            'symbol': det['symbol'],
                            'message': det['message']
                        }
            
            if unique_detections:
                print("=" * 70)
                print("DETECCIONES UNICAS DE CRT HOY:")
                print("=" * 70)
                print()
                
                for key, det in sorted(unique_detections.items(), key=lambda x: x[1]['time']):
                    time_str = det['time'].strftime('%H:%M:%S')
                    print(f"[{time_str}] {det['type']} - {det['symbol']}")
                    print(f"   Mensaje: {det['message'][:100]}...")
                    print()
                
                # Resumen final
                crt_types_found = set([d['type'] for d in unique_detections.values()])
                print("=" * 70)
                print("RESUMEN FINAL")
                print("=" * 70)
                print(f"Total de detecciones unicas: {len(unique_detections)}")
                print(f"Tipo(s) de CRT: {', '.join(sorted(crt_types_found))}")
                
                if len(unique_detections) == 1:
                    det = list(unique_detections.values())[0]
                    print()
                    print(f"*** SE CUMPLIO UN SOLO CRT HOY: {det['type']} ***")
                    print(f"    Hora: {det['time'].strftime('%H:%M:%S')}")
                    print(f"    Simbolo: {det['symbol']}")
            else:
                print("[INFO] No se pudieron identificar detecciones unicas")
        else:
            print("[INFO] No se encontraron detecciones de CRT hoy")
        
        connection.close()
        
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

