"""
Handler de Logging personalizado para guardar logs en base de datos
Extiende logging.Handler para integrar con DatabaseManager
"""

import logging
import re
from typing import Optional, Dict
from Base.database import DatabaseManager


class DatabaseLogHandler(logging.Handler):
    """
    Handler de logging que guarda logs en base de datos SQL Server
    """
    
    def __init__(self, db_manager: DatabaseManager, 
                 min_level: int = logging.INFO,
                 extract_symbol: bool = True,
                 extract_strategy: bool = True):
        """
        Inicializa el handler de base de datos
        
        Args:
            db_manager: Instancia de DatabaseManager
            min_level: Nivel mínimo de log a guardar (default: INFO)
            extract_symbol: Si True, intenta extraer símbolo del mensaje (default: True)
            extract_strategy: Si True, intenta extraer estrategia del logger name (default: True)
        """
        super().__init__()
        self.db_manager = db_manager
        self.setLevel(min_level)
        self.extract_symbol = extract_symbol
        self.extract_strategy = extract_strategy
        
        # Patrón para extraer símbolos del mensaje (ej: [EURUSD], [GBPUSD])
        self.symbol_pattern = re.compile(r'\[([A-Z]{6,12})\]')
    
    def emit(self, record: logging.LogRecord):
        """
        Guarda el log en la base de datos
        
        Args:
            record: Registro de log
        """
        try:
            # Extraer símbolo del mensaje si está habilitado
            symbol = None
            if self.extract_symbol:
                symbol_match = self.symbol_pattern.search(record.getMessage())
                if symbol_match:
                    symbol = symbol_match.group(1)
            
            # Extraer estrategia del logger name si está habilitado
            strategy = None
            if self.extract_strategy:
                logger_name = record.name
                # Buscar nombres comunes de estrategias en el logger name
                if 'TurtleSoup' in logger_name:
                    strategy = 'turtle_soup_fvg'
                elif 'FVG' in logger_name and 'Strategy' in logger_name:
                    strategy = 'fvg_strategy'
                elif 'DefaultStrategy' in logger_name:
                    strategy = 'default'
            
            # Preparar datos extra si hay información adicional
            extra_data = {}
            if hasattr(record, 'extra_data'):
                extra_data = record.extra_data
            
            # Guardar en base de datos
            self.db_manager.save_log(
                level=record.levelname,
                logger_name=record.name,
                message=self.format(record),
                symbol=symbol,
                strategy=strategy,
                extra_data=extra_data if extra_data else None
            )
            
        except Exception as e:
            # No loguear errores del handler para evitar loops infinitos
            # Solo imprimir en caso de debug
            pass

