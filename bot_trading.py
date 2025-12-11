"""
Bot de Trading para MetaTrader 5
Sistema multi-estrategia con gestión de horarios operativos
"""

import yaml
import logging
from datetime import datetime, time
from typing import List, Dict, Optional
import MetaTrader5 as mt5
from pytz import timezone
import time as time_module

from strategy_manager import StrategyManager
from Base.trading_hours import TradingHoursManager


class TradingBot:
    """Bot principal de trading con conexión a MT5"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Inicializa el bot de trading
        
        Args:
            config_path: Ruta al archivo de configuración
        """
        self.config = self._load_config(config_path)
        self._setup_logging()
        self.logger.info("Inicializando Bot de Trading...")
        
        # Inicializar componentes
        self.mt5_connected = False
        self.strategy_manager = StrategyManager(self.config)
        self.trading_hours = TradingHoursManager(self.config['trading_hours'])
        
        # Conectar a MT5
        self._connect_mt5()
        
    def _load_config(self, config_path: str) -> Dict:
        """Carga la configuración desde archivo YAML"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except FileNotFoundError:
            raise FileNotFoundError(f"Archivo de configuración no encontrado: {config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Error al leer configuración: {e}")
    
    def _setup_logging(self):
        """Configura el sistema de logging"""
        log_level = getattr(logging, self.config.get('general', {}).get('log_level', 'INFO'))
        
        # Crear carpeta logs si no existe
        import os
        os.makedirs('logs', exist_ok=True)
        
        # Configurar logging con archivo en carpeta logs/
        log_file = os.path.join('logs', 'trading_bot.log')
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def _connect_mt5(self) -> bool:
        """Conecta al terminal MT5"""
        mt5_config = self.config['mt5']
        
        # Cerrar conexión existente si hay
        if self.mt5_connected:
            mt5.shutdown()
            self.mt5_connected = False
        
        # Inicializar MT5
        if not mt5.initialize(path=mt5_config.get('path')):
            self.logger.error(f"Error al inicializar MT5: {mt5.last_error()}")
            return False
        
        # Intentar conexión
        login = mt5_config['login']
        password = mt5_config['password']
        server = mt5_config['server']
        
        self.logger.info(f"Conectando a MT5 - Login: {login}, Server: {server}")
        
        authorized = mt5.login(login, password=password, server=server)
        
        if not authorized:
            self.logger.error(f"Error al conectar a MT5: {mt5.last_error()}")
            mt5.shutdown()
            return False
        
        # Verificar conexión
        account_info = mt5.account_info()
        if account_info is None:
            self.logger.error("No se pudo obtener información de la cuenta")
            mt5.shutdown()
            return False
        
        self.mt5_connected = True
        self.logger.info(f"✓ Conectado exitosamente a MT5")
        self.logger.info(f"  Cuenta: {account_info.login}")
        self.logger.info(f"  Balance: {account_info.balance} {account_info.currency}")
        self.logger.info(f"  Servidor: {account_info.server}")
        
        return True
    
    def _check_and_reconnect_mt5(self) -> bool:
        """
        Verifica la conexión de MT5 y reconecta si es necesario
        
        Returns:
            True si está conectado, False si no se pudo conectar
        """
        if not self.mt5_connected:
            self.logger.warning("MT5 no está conectado, intentando reconectar...")
            return self._connect_mt5()
        
        # Verificar que la conexión sigue activa
        account_info = mt5.account_info()
        if account_info is None:
            self.logger.warning("Conexión MT5 perdida, intentando reconectar...")
            self.mt5_connected = False
            return self._connect_mt5()
        
        return True
    
    def _is_trading_time(self) -> bool:
        """Verifica si estamos en horario operativo"""
        return self.trading_hours.is_trading_time()
    
    def _analyze_market(self):
        """Analiza el mercado para los símbolos configurados"""
        # Verificar y reconectar MT5 si es necesario
        if not self._check_and_reconnect_mt5():
            self.logger.warning("No se pudo conectar a MT5, saltando análisis")
            return
        
        symbols = self.config['symbols']
        strategy_name = self.config['strategy']['name']
        
        self.logger.info(f"Analizando mercado para {len(symbols)} símbolo(s) con estrategia: {strategy_name}")
        
        for symbol in symbols:
            try:
                # Verificar que el símbolo existe en MT5
                symbol_info = mt5.symbol_info(symbol)
                if symbol_info is None:
                    self.logger.warning(f"Símbolo {symbol} no encontrado en MT5")
                    continue
                
                # Verificar que el símbolo está habilitado
                if not symbol_info.visible:
                    self.logger.info(f"Habilitando símbolo {symbol}...")
                    if not mt5.symbol_select(symbol, True):
                        self.logger.error(f"No se pudo habilitar {symbol}")
                        continue
                
                # Obtener datos del mercado
                timeframe = self._parse_timeframe(self.config['general']['timeframe'])
                rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 100)
                
                if rates is None or len(rates) == 0:
                    self.logger.warning(f"No se pudieron obtener datos para {symbol}")
                    continue
                
                # Ejecutar análisis con la estrategia
                self.logger.debug(f"Analizando {symbol} con {len(rates)} velas")
                signal = self.strategy_manager.analyze(symbol, rates, strategy_name)
                
                if signal:
                    self.logger.info(f"Señal generada para {symbol}: {signal}")
                    # Aquí se implementará la lógica de ejecución de órdenes
                else:
                    self.logger.debug(f"No hay señal para {symbol}")
                    
            except Exception as e:
                self.logger.error(f"Error al analizar {symbol}: {e}", exc_info=True)
    
    def _parse_timeframe(self, tf_str: str) -> int:
        """Convierte string de timeframe a constante MT5"""
        timeframe_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
        }
        return timeframe_map.get(tf_str.upper(), mt5.TIMEFRAME_M15)
    
    def run(self):
        """Ejecuta el bot en modo continuo"""
        self.logger.info("=" * 50)
        self.logger.info("Bot de Trading iniciado")
        self.logger.info("=" * 50)
        self.logger.info(f"Activos: {', '.join(self.config['symbols'])}")
        self.logger.info(f"Horario operativo: {self.config['trading_hours']['start_time']} - {self.config['trading_hours']['end_time']} ({self.config['trading_hours']['timezone']})")
        self.logger.info(f"Estrategia: {self.config['strategy']['name']}")
        self.logger.info("=" * 50)
        
        if not self.mt5_connected:
            self.logger.error("No se pudo conectar a MT5. El bot no puede continuar.")
            return
        
        try:
            while True:
                current_time = datetime.now()
                
                # Verificar si estamos en horario operativo
                if self._is_trading_time():
                    self.logger.info(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] ✅ Horario operativo activo - Analizando mercado...")
                    self._analyze_market()
                    
                    # Verificar si la estrategia necesita monitoreo intensivo
                    strategy_name = self.config['strategy']['name']
                    if self.strategy_manager.needs_intensive_monitoring(strategy_name):
                        # Monitoreo intensivo: evaluar cada segundo
                        sleep_interval = 1
                        self.logger.debug(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] 🔄 Modo monitoreo intensivo activo (cada {sleep_interval}s)")
                    else:
                        # Modo normal: usar intervalo configurado
                        sleep_interval = 60
                else:
                    next_trading = self.trading_hours.get_next_trading_time()
                    time_until = self.trading_hours.get_time_until_trading()
                    self.logger.info(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] ⏸️  Fuera de horario operativo - Próximo horario: {next_trading.strftime('%H:%M')} ({time_until})")
                    sleep_interval = 60
                
                # Esperar antes de la siguiente iteración
                time_module.sleep(sleep_interval)
                
        except KeyboardInterrupt:
            self.logger.info("Bot detenido por el usuario")
        except Exception as e:
            self.logger.error(f"Error crítico en el bot: {e}", exc_info=True)
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Cierra conexiones y finaliza el bot"""
        self.logger.info("Cerrando conexiones...")
        if self.mt5_connected:
            mt5.shutdown()
            self.mt5_connected = False
        self.logger.info("Bot finalizado correctamente")


if __name__ == "__main__":
    bot = TradingBot()
    bot.run()

