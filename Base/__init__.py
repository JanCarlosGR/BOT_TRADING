"""
Base - Módulos base para estrategias de trading
Contiene herramientas reutilizables para cualquier estrategia
"""

from .candle_reader import get_candle, create_candle_reader, CandleReader
from .fvg_detector import detect_fvg, FVGDetector
from .news_checker import (
    can_trade_now,
    get_daily_news_summary,
    validate_trading_day,
    check_high_impact_news_calendar,
    get_weekly_news,
    get_monthly_news,
    get_daily_news_list,
)
from .order_executor import (
    OrderExecutor,
    OrderType,
    create_order_executor,
    buy_order,
    sell_order,
)

__all__ = [
    # Candle Reader
    'get_candle',
    'create_candle_reader',
    'CandleReader',
    # FVG Detector
    'detect_fvg',
    'FVGDetector',
    # News Checker
    'can_trade_now',
    'get_daily_news_summary',
    'validate_trading_day',
    'check_high_impact_news_calendar',
    'get_weekly_news',
    'get_monthly_news',
    'get_daily_news_list',
    # Order Executor
    'OrderExecutor',
    'OrderType',
    'create_order_executor',
    'buy_order',
    'sell_order',
]

