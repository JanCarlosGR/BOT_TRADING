"""
Estrategias de Trading
Cada estrategia debe heredar de BaseStrategy

Nota: Las estrategias están en strategies.py en la raíz del proyecto.
Esta carpeta está preparada para cuando crezcas a muchas estrategias.
"""

# Por ahora, importar desde strategies.py en la raíz
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies import BaseStrategy, StrategyManager

__all__ = ['BaseStrategy', 'StrategyManager']

