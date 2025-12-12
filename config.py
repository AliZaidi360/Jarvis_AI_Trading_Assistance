import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass # dotenv not installed, relying on environment variables

class Config:
    # ---------------------------------------------------------
    # EXCHANGE SETTINGS
    # ---------------------------------------------------------
    EXCHANGE_ID = 'binance'  # Default to Binance
    SANDBOX_MODE = True      # Default to True for safety
    SYMBOL = 'BTC/USDT'      # Perpetual pair
    TIMEFRAME = '1m'
    
    API_KEY = os.getenv('EXCHANGE_API_KEY', '')
    API_SECRET = os.getenv('EXCHANGE_SECRET', '')

    # ---------------------------------------------------------
    # RISK MANAGEMENT (HARD CONSTRAINTS)
    # ---------------------------------------------------------
    # Max equity risk per trade (0.5%)
    RISK_PER_TRADE_PERCENT = 0.005
    
    # Hard stop if Daily PnL drops below -2%
    MAX_DAILY_DRAWDOWN_PERCENT = 0.02
    
    # Stop trading after this many consecutive losses
    MAX_CONSECUTIVE_LOSSES = 3
    
    # Maximum leverage allowed under ANY condition
    MAX_LEVERAGE_CAP = 5.0
    
    # Volatility window for calculations (number of candles)
    VOLATILITY_WINDOW = 20
    
    # Time horizon for "Worst Case Move" calculation (e.g., 4 hours = 240 mins)
    # sqrt(h) factor for VaR
    HOLDING_HORIZON_CANDLES = 240 

    # ---------------------------------------------------------
    # TRADING POLICY
    # ---------------------------------------------------------
    # Spread threshold to allow entry (e.g. 0.1% or 0.001)
    # If spread/mid > this, DO NOT ENTER
    MAX_SPREAD_THRESHOLD = 0.001 
    
    # Minimum expected edge (for funding check)
    MIN_EXPECTED_EDGE = 0.0005 # 5 bps

    # ---------------------------------------------------------
    # EXIT LOGIC
    # ---------------------------------------------------------
    # Volatility Multiplier for Stop Loss
    # Stop = m * sigma * sqrt(h)
    STOP_LOSS_M_FACTOR = 2.0
    
    # Time Stop: Max candles to hold without favorable move
    MAX_HOLD_DURATION_CANDLES = 60 # 1 hour if 1m candles

    # ---------------------------------------------------------
    # EXECUTION
    # ---------------------------------------------------------
    # Order Book depth to fetch
    ORDER_BOOK_DEPTH = 10
    
    # Timeout for unfilled limit orders (seconds)
    ORDER_TIMEOUT_SECONDS = 30
    
    # ---------------------------------------------------------
    # LOGGING
    # ---------------------------------------------------------
    LOG_FILE = 'trading_agent.jsonl'
    
    # ---------------------------------------------------------
    # LLM EXPLAINER
    # ---------------------------------------------------------
    LLM_API_KEY = os.getenv('LLM_API_KEY', None)
    LLM_MODEL = "gpt-4-turbo" # or equivalent

