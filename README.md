# MVP Perpetual Futures Trading Agent

## Mission
> Build a perpetual futures trading agent that proves it can survive volatility and compound small edges without blowing up.

## Overview
This is a **risk-first** algorithmic trading agent designed for crypto perpetual futures (e.g., BTC/USDT). It prioritizes **survivability** over profit maximization by enforcing hard-coded risk constraints and volatility-based position sizing.

**Key Features:**
- **Modular Architecture**: Separate `Risk`, `Alpha`, `Execution`, and `MarketData` modules.
- **Hard Risk Constraints**:
    - Daily PnL Stop (-2%)
    - Max Consecutive Losses (3)
    - Max Leverage Cap (5x)
- **Volatility Sizing**: Position size scales inversely with realized volatility.
- **No Black Box**: Logic is explicit and deterministic.

## Math & Formulas (Hard-Coded)
The agent strictly enforces the following equations:

### 1. Feature Computation
**Order Book Imbalance**:
```math
I_{book} = \frac{\sum w_i V^{bid}_i - \sum w_i V^{ask}_i}{\sum w_i V^{bid}_i + \sum w_i V^{ask}_i}
```
*Implemented in `src/market_data.py`*

**Order Flow Imbalance**:
```math
I_{flow} = \frac{BuyVol - SellVol}{BuyVol + SellVol}
```
*Implemented in `src/market_data.py`*

**Direction Score**:
```math
D = \tanh(0.5 \cdot I_{book} + 0.5 \cdot I_{flow})
```
*Implemented in `src/alpha.py`*

### 2. Risk & Sizing
**Worst-Case Move**:
```math
\Delta_{wc} = 2 \cdot \hat\sigma \cdot \sqrt{h}
```

**Position Notional**:
```math
Notional = \frac{0.005 \cdot Equity}{\Delta_{wc}}
```

**Leverage Cap**:
```math
Leverage = \min\left(5,\; \frac{1}{\hat\sigma},\; \frac{0.5}{Spread}\right)
```

**Volatility Stop**:
```math
Stop = m \cdot \hat\sigma \cdot \sqrt{h}
```
*All Risk Logic implemented in `src/risk.py`*

## Project Structure
```
.
├── src/
│   ├── alpha.py        # Signal generation (Orderbook/Flow Imbalance)
│   ├── bot.py          # Main orchestration loop
│   ├── execution.py    # Order placement & management
│   ├── market_data.py  # CCXT integration & feature extraction
│   └── risk.py         # Hard constraints & sizing logic (CRITICAL)
├── tests/
│   └── test_risk.py    # Unit tests for risk constraints
├── config.py           # Configuration (Risk limits, Symbols, API Keys)
├── main.py             # Entry point
├── requirements.txt    # Dependencies
└── README.md
```

## Setup & Usage

### 1. Installation
Clones the repo and install dependencies:
```bash
git clone https://github.com/AliZaidi360/Jarvis_AI_Trading_Assistance.git
cd Jarvis_AI_Trading_Assistance
pip install -r requirements.txt
```

### 2. Configuration
Create a `.env` file or modify `config.py` directly (not recommended for keys):
```ini
# .env
EXCHANGE_API_KEY=your_api_key
EXCHANGE_SECRET=your_secret
```
*Note: By default, `config.py` enables `SANDBOX_MODE = True`. Disable this only when ready for real trading.*

### 3. Run Verification
Ensure risk logic is working:
```bash
python -m unittest tests/test_risk.py
```

### 4. Run Agent
```bash
python main.py
```

## Risk Philosophy
The agent enforces strict rules that **cannot** be overridden by the trading signal:
1. **Capital Preservation**: Never risk more than 0.5% equity per trade.
2. **Circuit Breakers**: Stop trading immediately if daily drawdown hits 2%.
3. **Market Regimes**: Do not trade if spread is too high (>0.1%) or liquidity is low.
