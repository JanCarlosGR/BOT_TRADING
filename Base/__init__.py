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
from .turtle_soup_detector import detect_turtle_soup_h4, TurtleSoupDetector
from .crt_detector import (
    detect_crt_sweep,
    detect_crt_vayas,
    detect_engulfing,
    CRTDetector,
)
from .crt_continuation_detector import (
    detect_crt_continuation,
    CRTContinuationDetector,
)
from .crt_revision_detector import (
    detect_crt_revision,
    CRTRevisionDetector,
)
from .crt_extreme_detector import (
    detect_crt_extreme,
    CRTextremeDetector,
)
from .daily_levels_detector import (
    get_previous_daily_levels,
    detect_daily_level_touch,
    detect_daily_high_take,
    detect_daily_low_take,
    get_yesterday_levels,
    is_price_near_daily_level,
    DailyLevelsDetector,
)
from .strategy_scheduler import StrategyScheduler

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
    # Turtle Soup Detector
    'detect_turtle_soup_h4',
    'TurtleSoupDetector',
    # CRT Detector
    'detect_crt_sweep',
    'detect_crt_vayas',
    'detect_engulfing',
    'CRTDetector',
    # CRT Continuation Detector
    'detect_crt_continuation',
    'CRTContinuationDetector',
    # CRT Revision Detector
    'detect_crt_revision',
    'CRTRevisionDetector',
    # CRT Extreme Detector
    'detect_crt_extreme',
    'CRTextremeDetector',
    # Daily Levels Detector
    'get_previous_daily_levels',
    'detect_daily_level_touch',
    'detect_daily_high_take',
    'detect_daily_low_take',
    'get_yesterday_levels',
    'is_price_near_daily_level',
    'DailyLevelsDetector',
    # Strategy Scheduler
    'StrategyScheduler',
]

