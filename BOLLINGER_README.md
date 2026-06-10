# Bollinger Bands Trading Bot - Setup & Usage Guide

## 🚀 Quick Start

Get started with the advanced Bollinger Bands trading bot in 5 minutes!

### Prerequisites

- Python 3.6 or higher
- Binance account with API access
- Basic understanding of cryptocurrency trading

### Installation

1. **Clone the repository** (if not already done)
   ```bash
   git clone https://github.com/yasinkuyu/binance-trader.git
   cd binance-trader
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure API keys**
   ```bash
   cp app/config.sample.py app/config.py
   nano app/config.py
   ```

   Add your Binance API credentials:
   ```python
   api_key = 'your_binance_api_key_here'
   api_secret = 'your_binance_api_secret_here'
   ```

4. **Test the bot** (no real trades)
   ```bash
   python trader_bollinger.py --symbol BTCUSDT --amount 100 --test_mode
   ```

5. **Start live trading** (when ready)
   ```bash
   python trader_bollinger.py --symbol BTCUSDT --amount 100
   ```

---

## 📖 Table of Contents

1. [Features](#features)
2. [How It Works](#how-it-works)
3. [Configuration](#configuration)
4. [Usage Examples](#usage-examples)
5. [Safety & Risk Management](#safety--risk-management)
6. [Troubleshooting](#troubleshooting)
7. [FAQ](#faq)

---

## ✨ Features

### Advanced Technical Analysis
- ✅ **Bollinger Bands** - Adaptive volatility-based bands
- ✅ **RSI** - Momentum confirmation
- ✅ **Volume Analysis** - Trend strength validation
- ✅ **ATR-based Stop Loss** - Dynamic risk management
- ✅ **Multiple Timeframes** - From 1m to 1d intervals

### Risk Management
- 💰 **Position Sizing** - Risk-based or fixed amount
- 🛡️ **Dynamic Stop Loss** - Adapts to market volatility
- 🎯 **Flexible Take Profit** - Multiple strategies
- 📊 **Performance Tracking** - Win rate, profit/loss, statistics

### User-Friendly
- 🧪 **Test Mode** - Practice without risking money
- 📝 **Detailed Logging** - Track every decision
- ⚙️ **Highly Configurable** - 20+ parameters
- 🚦 **Confidence Scoring** - Know signal quality
- 📈 **Real-time Analysis** - Live market monitoring

---

## 🔍 How It Works

### The Strategy in Simple Terms

1. **Wait for Opportunity**
   - Bot monitors price movement within Bollinger Bands
   - Calculates RSI to measure momentum
   - Analyzes volume to confirm trends

2. **Buy Signal**
   - Price drops to/below lower Bollinger Band (oversold zone)
   - RSI confirms oversold condition (< 30)
   - Volume shows strong interest
   - Bot calculates optimal entry, stop loss, and take profit

3. **Hold Position**
   - Monitors price vs stop loss (exit if hit)
   - Monitors price vs take profit (exit if reached)
   - Continuously analyzes for better exit opportunities

4. **Sell Signal**
   - Price reaches take profit target (usually middle band)
   - Or price shows reversal signals
   - Or stop loss triggered to limit loss

5. **Repeat**
   - Strategy runs continuously
   - Adapts to changing market conditions
   - Maintains consistent risk per trade

### Signal Quality (Confidence Score)

The bot calculates a confidence score (0-100%) for each signal:

- **70-100%**: Strong signal - High probability setup
- **50-69%**: Good signal - Decent probability
- **30-49%**: Weak signal - Filtered out (unless you lower threshold)
- **0-29%**: No signal - Stay in cash

---

## ⚙️ Configuration

### Basic Configuration

**Minimum required parameters:**
```bash
--symbol BTCUSDT    # Trading pair
--amount 100        # Amount to trade (in USDT)
```

**Recommended for beginners:**
```bash
python trader_bollinger.py \
  --symbol BTCUSDT \
  --amount 100 \
  --market_type futures \
  --leverage 20 \
  --interval 5m \
  --test_mode
```

**5% margin with 20x leverage and moving exits:**
```bash
python trader_bollinger.py \
  --symbol BTCUSDT \
  --position_pct 5 \
  --paper_balance 1000 \
  --market_type futures \
  --leverage 20 \
  --futures_side BOTH \
  --move_exits \
  --test_mode
```

### Advanced Configuration

**Full parameter list:**

```bash
python trader_bollinger.py \
  # Required
  --symbol BTCUSDT \

  # Position sizing (choose one)
  --amount 100 \              # Amount in quote currency (recommended)
  --quantity 0.01 \           # Fixed quantity
  --position_pct 5 \          # Margin percent of balance/equity
  --paper_balance 1000 \      # Virtual balance for --test_mode sizing

  # Market
  --market_type futures \      # futures or spot (default: futures)
  --leverage 20 \              # USD-M futures leverage
  --futures_side LONG \        # LONG, SHORT, or BOTH

  # Bollinger Bands
  --bb_period 20 \            # BB lookback period
  --bb_stddev 2.0 \           # Standard deviation multiplier

  # RSI
  --rsi_period 14 \           # RSI calculation period
  --rsi_oversold 30 \         # Oversold threshold
  --rsi_overbought 70 \       # Overbought threshold

  # Volume
  --volume_threshold 1.2 \    # Volume ratio for confirmation

  # Risk Management
  --stop_loss_atr 2.0 \       # Stop loss distance (ATR multiplier)
  --take_profit middle \      # Take profit: middle, upper, or %
  --take_profit_strategy legacy \ # legacy, band, percent, atr, risk_reward, trailing
  --take_profit_value 2.0 \   # value for percent/atr/risk_reward
  --take_profit_band middle \ # middle or outer for band strategy
  --risk_per_trade 2.0 \      # Risk per trade (% of balance)
  --move_exits \              # Move SL/TP with ATR and BB while holding

  # Filters
  --min_bb_width 1.0 \        # Minimum volatility
  --max_bb_width 10.0 \       # Maximum volatility
  --min_confidence 50 \       # Minimum signal confidence

  # Data
  --interval 5m \             # Candlestick interval
  --kline_limit 100 \         # Historical candles to fetch

  # Bot Behavior
  --wait_time 10 \            # Seconds between cycles
  --max_trades 10 \           # Max trades before stopping (0=unlimited)
  --test_mode \               # Paper trading (no real orders)
  --debug                     # Verbose logging
```

---

## 💡 Usage Examples

### Scan Movers Before Trading
```bash
# Find unusual USD-M futures movers
python scan_movers.py --market_type futures --interval 5m --top 20

# Require stronger short-term activity
python scan_movers.py \
  --market_type futures \
  --interval 5m \
  --min_quote_volume 50000000 \
  --min_volume_ratio 2 \
  --min_range_pct 1 \
  --top 20
```

The scanner prints symbols with a composite score based on 24h change, recent
volume spike, latest candle range, Bollinger Band width, and band breakout
position. Use the `Dir` column as a watchlist hint, then run the trading bot on
the symbols you want to test.

### Auto-Trade Scanned Movers
```bash
# Paper trading: scan movers, confirm with strategy, then track positions
python auto_trade_movers.py \
  --strategy_mode mean_reversion \
  --position_pct 5 \
  --paper_balance 1000 \
  --leverage 20 \
  --futures_side BOTH \
  --move_exits \
  --max_positions 3 \
  --entries_per_scan 1

# Resume paper positions/stats after an interruption
python auto_trade_movers.py \
  --strategy_mode mean_reversion \
  --position_pct 5 \
  --paper_balance 1000 \
  --leverage 20 \
  --futures_side BOTH \
  --move_exits \
  --state_file paper_state.json \
  --resume_state

# Trend breakout mode
python auto_trade_movers.py \
  --strategy_mode breakout \
  --take_profit_strategy risk_reward \
  --take_profit_value 2 \
  --position_pct 5 \
  --paper_balance 1000 \
  --leverage 20 \
  --futures_side BOTH \
  --move_exits \
  --min_confidence 60

# Short-term scalping mode
python auto_trade_movers.py \
  --strategy_mode scalping \
  --scan_interval 1m \
  --scan_every 15 \
  --wait_time 3 \
  --position_pct 2 \
  --paper_balance 1000 \
  --leverage 20 \
  --futures_side BOTH \
  --scalping_take_profit_pct 0.4 \
  --scalping_stop_loss_pct 0.25 \
  --move_exits \
  --max_positions 2 \
  --entries_per_scan 1 \
  --state_file paper_state.json \
  --resume_state

# Live mode requires explicit confirmation
python auto_trade_movers.py \
  --strategy_mode mean_reversion \
  --position_pct 5 \
  --leverage 20 \
  --futures_side BOTH \
  --move_exits \
  --max_positions 3 \
  --entries_per_scan 1 \
  --live
```

The auto trader does not open directly from scanner direction alone. It first
uses `scan_movers.py` logic to find candidates, then runs the Bollinger strategy
on each candidate. A `LONG` candidate must confirm with `Signal=BUY`; a `SHORT`
candidate must confirm with `Signal=SELL`.

In paper mode, the auto trader saves positions and performance stats to
`paper_state.json` by default. Use `--resume_state` to restore that simulated
state after restarting the process. This does not affect live Binance futures
positions, which remain on the exchange.

While paper positions are open, the auto trader logs per-position unrealized P/L
and a portfolio summary line. These paper P/L logs use Chinese field labels for
easier reading in `auto_trade_movers.log`.

`--strategy_mode scalping` uses EMA9/EMA21 short-term trend, pullback/reclaim
near the fast EMA, RSI, volume, and MACD confirmation. Its default paper targets
are small: 0.4% take profit and 0.25% stop loss.

### Example 1: Conservative Long-Term Trading
```bash
# Low risk, high confidence required, larger timeframe
python trader_bollinger.py \
  --symbol BTCUSDT \
  --amount 50 \
  --interval 1h \
  --min_confidence 70 \
  --risk_per_trade 1.0 \
  --rsi_oversold 25 \
  --rsi_overbought 75
```

### Example 2: Balanced Day Trading
```bash
# Recommended for most users
python trader_bollinger.py \
  --symbol ETHUSDT \
  --amount 100 \
  --interval 5m \
  --min_confidence 50 \
  --risk_per_trade 2.0
```

### Example 3: Aggressive Scalping
```bash
# Higher frequency, lower confidence threshold
python trader_bollinger.py \
  --symbol BNBUSDT \
  --amount 200 \
  --interval 1m \
  --min_confidence 40 \
  --risk_per_trade 3.0 \
  --rsi_oversold 35 \
  --rsi_overbought 65 \
  --bb_stddev 1.5
```

### Example 4: Test Mode (Practice)
```bash
# Perfect for learning without risking money
python trader_bollinger.py \
  --symbol BTCUSDT \
  --amount 100 \
  --test_mode \
  --debug
```

### Example 5: Multiple Pairs (Run Separately)
```bash
# Terminal 1
python trader_bollinger.py --symbol BTCUSDT --amount 100

# Terminal 2
python trader_bollinger.py --symbol ETHUSDT --amount 50

# Terminal 3
python trader_bollinger.py --symbol ADAUSDT --amount 25
```

---

## 🛡️ Safety & Risk Management

### Before Live Trading

**Checklist:**
- [ ] API keys configured correctly
- [ ] Trading enabled on API key
- [ ] Withdrawals DISABLED on API key (for security)
- [ ] Tested in `--test_mode` for at least 1 week
- [ ] Understand all parameters
- [ ] Know how to stop the bot (Ctrl+C)
- [ ] Have monitored logs and understand output
- [ ] Started with small amounts

### Risk Management Best Practices

1. **Never risk more than 2% per trade**
   ```bash
   --risk_per_trade 2.0  # Maximum recommended
   ```

2. **Start small**
   ```bash
   --amount 50  # Start with minimum viable amount
   ```

3. **Use test mode first**
   ```bash
   --test_mode  # Always test before going live
   ```

4. **Set trade limits**
   ```bash
   --max_trades 5  # Limit daily trades while learning
   ```

5. **Monitor regularly**
   ```bash
   tail -f bollinger_trader.log  # Watch in real-time
   ```

### Security Best Practices

**API Key Setup:**
1. Go to Binance → API Management
2. Create new API key
3. Enable: ✅ Read Info, ✅ Enable Spot Trading
4. Disable: ❌ Enable Withdrawals, ❌ Enable Futures
5. Set IP whitelist (recommended)
6. Store secret key securely

**Never share your API keys!**

---

## 🔧 Troubleshooting

### Common Issues

#### 1. "Invalid symbol" error
```
Problem: Symbol not recognized
Solution: Use exact Binance symbol format (e.g., BTCUSDT, not BTC/USDT)
Check: https://www.binance.com/en/markets
```

#### 2. "MIN_NOTIONAL" error
```
Problem: Trade amount too small
Solution: Increase --amount or --quantity
Minimum: Usually $10-20 USD equivalent
```

#### 3. "Insufficient balance" error
```
Problem: Not enough funds in account
Solution: Deposit more funds or reduce --amount
Check balance: python balance.py
```

#### 4. "Timestamp ahead of server" error
```
Problem: System clock not synchronized
Solution: Sync your system clock
Linux: sudo ntpdate -s time.nist.gov
Windows: Right-click clock → Adjust date/time → Sync now
```

#### 5. "No kline data available" error
```
Problem: Can't fetch historical data
Solution:
- Check internet connection
- Verify symbol is correct
- Try different interval (--interval 5m)
```

#### 6. Bot not executing trades
```
Problem: Signals generated but no trades
Possible causes:
1. Test mode enabled (--test_mode)
2. Confidence too low (increase --min_confidence)
3. Volatility outside range (adjust --min_bb_width / --max_bb_width)
4. Insufficient funds

Solution: Check logs for exact reason
```

### Checking Logs

**Real-time monitoring:**
```bash
tail -f bollinger_trader.log
```

**Search for errors:**
```bash
grep ERROR bollinger_trader.log
```

**View recent activity:**
```bash
tail -100 bollinger_trader.log
```

---

## ❓ FAQ

### General Questions

**Q: Is this bot profitable?**
A: Past backtests show positive results, but profitability depends on market conditions, parameters, and risk management. No guarantees.

**Q: How much money do I need to start?**
A: Minimum $50-100 recommended. Start small and scale up as you gain confidence.

**Q: Can I run multiple bots on different pairs?**
A: Yes! Run each in a separate terminal/screen session.

**Q: Does it work 24/7?**
A: Yes, crypto markets are 24/7. Consider running on a VPS for uptime.

**Q: How often does it trade?**
A: Depends on market conditions and parameters. Average: 2-5 trades per day on 5m interval.

### Technical Questions

**Q: What timeframe is best?**
A: 5m or 15m recommended. 1m is too noisy, 1h is too slow for this strategy.

**Q: Can I use this on other exchanges?**
A: Code is Binance-specific but can be adapted with API changes.

**Q: How do I stop the bot?**
A: Press `Ctrl+C` in the terminal. It will shut down gracefully.

**Q: Will it close open positions on shutdown?**
A: No, you must manually close or restart the bot to manage positions.

**Q: How do I update the bot?**
A: `git pull` to get latest changes. Review changelog before running.

### Strategy Questions

**Q: Why Bollinger Bands?**
A: Mean reversion strategy proven effective in crypto markets with good risk/reward.

**Q: What's a good win rate?**
A: 55-65% is excellent. Higher win rate often means you're leaving profit on the table.

**Q: Should I use default parameters?**
A: Start with defaults, then optimize based on your results and market conditions.

**Q: Can I customize the strategy?**
A: Yes! All code is open source. Modify `BollingerStrategy.py` for custom logic.

### Risk Questions

**Q: What's the maximum drawdown?**
A: With 2% risk per trade, expect 10-15% max drawdown in backtests.

**Q: Can I lose all my money?**
A: Theoretically yes, like any trading. Use proper risk management (2% max risk).

**Q: What if there's a flash crash?**
A: Stop losses provide some protection, but extreme volatility can cause slippage.

**Q: Should I use leverage?**
A: No. This bot is designed for spot trading only. Leverage amplifies both gains and losses.

---

## 📊 Monitoring Performance

### Key Metrics to Track

**In the logs, monitor:**
```
📊 Stats: X trades, Win rate: Y%, Total P/L: Z
```

**Good performance indicators:**
- Win rate: >55%
- Profit factor: >1.5
- Average win > Average loss

**Warning signs:**
- Win rate: <45%
- Multiple consecutive losses (>5)
- Drawdown >15%

**Action if underperforming:**
1. Increase `--min_confidence` to 60-70
2. Reduce `--risk_per_trade` to 1.0
3. Pause and review parameter settings
4. Check if market conditions changed

---

## 🚀 Next Steps

### After Getting Started

1. **Run in test mode for 1 week**
   - Observe signals and trades
   - Understand bot behavior
   - Adjust parameters

2. **Start with small amounts**
   - Go live with $50-100
   - Run for 2 weeks minimum
   - Track all results

3. **Optimize parameters**
   - Analyze which settings work best
   - A/B test different configurations
   - Keep detailed notes

4. **Scale gradually**
   - Increase position size as confidence grows
   - Never risk more than you can afford to lose
   - Maintain discipline

### Learning Resources

- **Strategy Deep Dive**: See `BOLLINGER_STRATEGY.md`
- **Original Bot**: See `README.md`
- **Binance API**: https://binance-docs.github.io/apidocs/spot/en/
- **Bollinger Bands**: https://www.bollingerbands.com/

---

## 📝 Support

### Getting Help

1. **Check logs first**: `bollinger_trader.log`
2. **Read this README thoroughly**
3. **Review** `BOLLINGER_STRATEGY.md`
4. **Check existing issues**: GitHub Issues
5. **Create new issue**: Provide logs and config

### Contributing

Improvements welcome! Please:
1. Test thoroughly
2. Document changes
3. Submit pull request

---

## ⚠️ Disclaimer

**IMPORTANT LEGAL NOTICE:**

This software is provided "as is", without warranty of any kind. Trading cryptocurrencies carries significant risk. You can lose all your invested capital.

- ❌ Not financial advice
- ❌ No profit guarantees
- ❌ Use at your own risk
- ❌ Author not responsible for losses

**By using this bot, you accept all risks and responsibility for your trading decisions.**

---

## 📜 License

MIT License - See LICENSE file for details

---

**Good luck and trade responsibly! 🚀**

*Last updated: 2025*
