#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# Binance Trader with Advanced Bollinger Bands Strategy

import sys
import argparse
import time
import logging

sys.path.insert(0, './app')

from BollingerTradingBot import BollingerTradingBot


def setup_logging(debug=False):
    """Setup logging configuration"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bollinger_trader.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )


if __name__ == '__main__':
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description='Binance Bollinger Bands Trading Bot - Advanced Strategy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Basic usage with default settings
  python trader_bollinger.py --symbol BTCUSDT --amount 100 --test_mode

  # Futures paper trading with leverage
  python trader_bollinger.py --symbol BTCUSDT --position_pct 5 --market_type futures --leverage 20 --test_mode

  # Allow both long and short futures entries
  python trader_bollinger.py --symbol ETHUSDT --amount 50 --futures_side BOTH --test_mode

  # Spot mode is still available
  python trader_bollinger.py --symbol BTCUSDT --amount 100 --market_type spot --test_mode

  # Conservative trading with higher confidence requirement
  python trader_bollinger.py --symbol ADAUSDT --amount 100 --min_confidence 70 --test_mode
        '''
    )

    # Required parameters
    parser.add_argument('--symbol', type=str, required=True,
                        help='Trading pair symbol (e.g., BTCUSDT, ETHBTC)')

    # Position sizing (choose one)
    parser.add_argument('--quantity', type=float, default=0,
                        help='Fixed quantity to trade (default: 0 = auto-calculate)')
    parser.add_argument('--amount', type=float, default=0,
                        help='Amount in quote currency to trade (e.g., 100 USDT)')
    parser.add_argument('--position_pct', type=float, default=0,
                        help='Position margin as percent of available balance/equity (e.g., 5 = 5%%)')
    parser.add_argument('--paper_balance', type=float, default=1000.0,
                        help='Virtual account balance for --test_mode percentage sizing (default: 1000)')

    # Market type
    parser.add_argument('--market_type', type=str, choices=['futures', 'spot'], default='futures',
                        help='Trading market type: futures or spot (default: futures)')
    parser.add_argument('--leverage', type=int, default=20,
                        help='USD-M futures leverage, live mode will set it on Binance (default: 20)')
    parser.add_argument('--futures_side', type=str, choices=['LONG', 'SHORT', 'BOTH'], default='LONG',
                        help='Futures entry direction: LONG, SHORT, or BOTH (default: LONG)')

    # Bollinger Bands parameters
    parser.add_argument('--strategy_mode', type=str, choices=['mean_reversion', 'breakout', 'scalping'], default='mean_reversion',
                        help='Strategy mode: mean_reversion, breakout, or scalping (default: mean_reversion)')
    parser.add_argument('--bb_period', type=int, default=20,
                        help='Bollinger Bands period (default: 20)')
    parser.add_argument('--bb_stddev', type=float, default=2.0,
                        help='Bollinger Bands standard deviation (default: 2.0)')

    # RSI parameters
    parser.add_argument('--rsi_period', type=int, default=14,
                        help='RSI period (default: 14)')
    parser.add_argument('--rsi_oversold', type=float, default=30,
                        help='RSI oversold threshold (default: 30)')
    parser.add_argument('--rsi_overbought', type=float, default=70,
                        help='RSI overbought threshold (default: 70)')

    # Volume parameters
    parser.add_argument('--volume_threshold', type=float, default=1.2,
                        help='Volume ratio threshold for confirmation (default: 1.2)')

    # Scalping parameters
    parser.add_argument('--scalping_ema_fast', type=int, default=9,
                        help='Fast EMA period for scalping mode (default: 9)')
    parser.add_argument('--scalping_ema_slow', type=int, default=21,
                        help='Slow EMA period for scalping mode (default: 21)')
    parser.add_argument('--scalping_take_profit_pct', type=float, default=0.4,
                        help='Scalping fixed take profit percentage (default: 0.4)')
    parser.add_argument('--scalping_stop_loss_pct', type=float, default=0.25,
                        help='Scalping fixed stop loss percentage (default: 0.25)')
    parser.add_argument('--scalping_pullback_pct', type=float, default=0.15,
                        help='Max distance from fast EMA for scalping entry (default: 0.15)')

    # Risk management
    parser.add_argument('--stop_loss_atr', type=float, default=2.0,
                        help='Stop loss as multiple of ATR (default: 2.0)')
    parser.add_argument('--take_profit', type=str, default='middle',
                        help='Legacy take profit target: "middle", "upper", percentage, or "trailing" (default: middle)')
    parser.add_argument('--take_profit_strategy', type=str,
                        choices=['legacy', 'band', 'percent', 'atr', 'risk_reward', 'trailing'],
                        default='legacy',
                        help='Take profit strategy (default: legacy)')
    parser.add_argument('--take_profit_value', type=float, default=2.0,
                        help='Value for percent/atr/risk_reward take profit strategies (default: 2.0)')
    parser.add_argument('--take_profit_band', type=str, choices=['middle', 'outer'], default='middle',
                        help='Band target for --take_profit_strategy band (default: middle)')
    parser.add_argument('--risk_per_trade', type=float, default=2.0,
                        help='Risk percentage per trade (default: 2.0%%)')
    parser.add_argument('--move_exits', action='store_true',
                        help='Move stop loss/take profit using latest ATR and Bollinger Bands while holding')

    # Strategy filters
    parser.add_argument('--min_bb_width', type=float, default=1.0,
                        help='Minimum BB width to trade (volatility filter) (default: 1.0)')
    parser.add_argument('--max_bb_width', type=float, default=10.0,
                        help='Maximum BB width to trade (volatility filter) (default: 10.0)')
    parser.add_argument('--min_confidence', type=int, default=50,
                        help='Minimum confidence score to execute trade (default: 50)')

    # Data parameters
    parser.add_argument('--interval', type=str, default='5m',
                        help='Candlestick interval (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d) (default: 5m)')
    parser.add_argument('--kline_limit', type=int, default=100,
                        help='Number of historical candles to fetch (default: 100)')

    # Bot behavior
    parser.add_argument('--wait_time', type=float, default=10,
                        help='Wait time between analysis cycles (seconds) (default: 10)')
    parser.add_argument('--max_trades', type=int, default=0,
                        help='Maximum number of trades to execute (0 = unlimited) (default: 0)')
    parser.add_argument('--test_mode', action='store_true',
                        help='Paper trading mode - virtual positions, no real orders')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging')

    # Commission type
    parser.add_argument('--commission', type=str, default='BNB',
                        help='Commission payment type: BNB or TOKEN (default: BNB)')

    args = parser.parse_args()

    if args.leverage < 1 or args.leverage > 125:
        parser.error('--leverage must be between 1 and 125')
    if args.position_pct < 0 or args.position_pct > 100:
        parser.error('--position_pct must be between 0 and 100')
    if args.scalping_ema_fast < 1 or args.scalping_ema_slow < 1:
        parser.error('--scalping_ema_fast and --scalping_ema_slow must be positive')
    if args.scalping_take_profit_pct <= 0 or args.scalping_stop_loss_pct <= 0:
        parser.error('--scalping_take_profit_pct and --scalping_stop_loss_pct must be positive')

    # Setup logging
    setup_logging(args.debug)
    logger = logging.getLogger(__name__)

    # Display configuration
    print('=' * 70)
    print('BINANCE BOLLINGER BANDS TRADING BOT')
    print('=' * 70)
    print(f'\nTrading Symbol: {args.symbol}')
    print(f'Market Type: {args.market_type.upper()}')
    print(f'Interval: {args.interval}')
    print(f'Test Mode: {"YES - Paper trading, no real orders" if args.test_mode else "NO - Live trading"}')
    if args.market_type == 'futures':
        print(f'Futures Side: {args.futures_side}')
        print(f'Leverage: {args.leverage}x')
    print(f'\n--- Strategy Parameters ---')
    print(f'Strategy Mode: {args.strategy_mode}')
    print(f'Bollinger Bands: {args.bb_period} period, {args.bb_stddev} std dev')
    print(f'RSI: {args.rsi_period} period (Oversold: {args.rsi_oversold}, Overbought: {args.rsi_overbought})')
    print(f'Volume Threshold: {args.volume_threshold}x average')
    if args.strategy_mode == 'scalping':
        print(
            f'Scalping EMA: fast={args.scalping_ema_fast}, slow={args.scalping_ema_slow}; '
            f'TP={args.scalping_take_profit_pct}%, SL={args.scalping_stop_loss_pct}%, '
            f'pullback={args.scalping_pullback_pct}%'
        )
    print(f'BB Width Filter: {args.min_bb_width}% - {args.max_bb_width}%')
    print(f'Minimum Confidence: {args.min_confidence}%')
    print(f'\n--- Risk Management ---')
    print(f'Stop Loss: {args.stop_loss_atr}x ATR')
    print(f'Take Profit: {args.take_profit}')
    print(f'Take Profit Strategy: {args.take_profit_strategy}')
    if args.take_profit_strategy in ['percent', 'atr', 'risk_reward']:
        print(f'Take Profit Value: {args.take_profit_value}')
    if args.take_profit_strategy == 'band':
        print(f'Take Profit Band: {args.take_profit_band}')
    print(f'Risk per Trade: {args.risk_per_trade}%')
    print(f'Move Exits: {"YES" if args.move_exits else "NO"}')
    print(f'\n--- Position Sizing ---')
    if args.quantity > 0:
        print(f'Fixed Quantity: {args.quantity}')
    elif args.position_pct > 0:
        notional_pct = args.position_pct * args.leverage if args.market_type == 'futures' else args.position_pct
        print(f'Position Margin: {args.position_pct}% of balance')
        if args.market_type == 'futures':
            print(f'Approx Notional: {notional_pct}% of balance at {args.leverage}x')
        if args.test_mode:
            print(f'Paper Balance: {args.paper_balance}')
    elif args.amount > 0:
        print(f'Fixed Amount: {args.amount} (quote currency)')
    else:
        print(f'Dynamic sizing based on risk ({args.risk_per_trade}% per trade)')
    print(f'\n--- Operational Parameters ---')
    print(f'Wait Time: {args.wait_time}s between cycles')
    print(f'Max Trades: {args.max_trades if args.max_trades > 0 else "Unlimited"}')
    print(f'Commission Type: {args.commission}')
    print('=' * 70)
    print()

    # Confirmation for live trading
    if not args.test_mode:
        print('⚠️  WARNING: You are about to start LIVE TRADING with real money!')
        print('⚠️  Make sure you have:')
        print('   1. Configured your API keys in app/config.py')
        print('   2. Enabled trading permissions on your API key')
        print('   3. Tested the strategy in --test_mode first')
        print('   4. Understood the risks involved')
        print()
        response = input('Type "START" to begin live trading, or anything else to exit: ')
        if response.strip().upper() != 'START':
            print('Exiting...')
            sys.exit(0)
        print()

    try:
        # Initialize and run the trading bot
        bot = BollingerTradingBot(args)
        bot.run()

    except KeyboardInterrupt:
        logger.info('\n\nBot stopped by user (Ctrl+C)')
        print('\nBot stopped gracefully. Goodbye!')

    except Exception as e:
        logger.error(f'Fatal error: {e}', exc_info=True)
        print(f'\n❌ Fatal error: {e}')
        print('Check bollinger_trader.log for details')
        sys.exit(1)
