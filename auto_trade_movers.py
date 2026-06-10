#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# Scan movers, confirm with Bollinger strategy, then track and trade.

import argparse
import concurrent.futures
import json
import logging
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, './app')

from BollingerTradingBot import BollingerTradingBot
from scan_movers import (
    fetch_symbols,
    fetch_tickers,
    liquid_candidates,
    make_client,
    score_symbol,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Automatically scan movers, confirm signals, and trade selected futures symbols'
    )

    # Scan settings
    parser.add_argument('--market_type', choices=['futures'], default='futures',
                        help='Market type to scan/trade (default: futures)')
    parser.add_argument('--quote_asset', default='USDT',
                        help='Quote asset to scan (default: USDT)')
    parser.add_argument('--scan_interval', default='5m',
                        help='Kline interval for scanning and trading (default: 5m)')
    parser.add_argument('--scan_mode', choices=['auto', 'trend', 'mean_reversion'], default='auto',
                        help='Scanner direction mode. auto follows --strategy_mode (default: auto)')
    parser.add_argument('--scan_every', type=float, default=60,
                        help='Seconds between scans (default: 60)')
    parser.add_argument('--candidates', type=int, default=120,
                        help='Most liquid symbols to inspect per scan (default: 120)')
    parser.add_argument('--top', type=int, default=10,
                        help='Top scanned movers to consider per scan (default: 10)')
    parser.add_argument('--min_quote_volume', type=float, default=50000000,
                        help='Minimum 24h quote volume (default: 50000000)')
    parser.add_argument('--min_mover_score', type=float, default=60,
                        help='Minimum scanner score before strategy confirmation (default: 60)')
    parser.add_argument('--min_volume_ratio', type=float, default=0,
                        help='Minimum scan volume spike filter (default: 0)')
    parser.add_argument('--min_range_pct', type=float, default=0,
                        help='Minimum scan latest candle range filter (default: 0)')
    parser.add_argument('--scan_workers', type=int, default=6,
                        help='Concurrent scanner workers (default: 6)')
    parser.add_argument('--scan_retries', type=int, default=2,
                        help='Retries per scanner kline request (default: 2)')
    parser.add_argument('--scan_retry_wait', type=float, default=0.5,
                        help='Seconds between scanner retries (default: 0.5)')

    # Trading settings
    parser.add_argument('--amount', type=float, default=0,
                        help='Fixed notional amount in quote currency; ignored when --position_pct is set')
    parser.add_argument('--quantity', type=float, default=0,
                        help='Fixed contract quantity')
    parser.add_argument('--position_pct', type=float, default=5,
                        help='Position margin as percent of available balance/equity (default: 5)')
    parser.add_argument('--paper_balance', type=float, default=1000,
                        help='Virtual balance for paper mode percentage sizing (default: 1000)')
    parser.add_argument('--leverage', type=int, default=20,
                        help='USD-M futures leverage (default: 20)')
    parser.add_argument('--futures_side', choices=['LONG', 'SHORT', 'BOTH'], default='BOTH',
                        help='Allowed trade direction (default: BOTH)')
    parser.add_argument('--max_positions', type=int, default=3,
                        help='Maximum simultaneous tracked positions (default: 3)')
    parser.add_argument('--entries_per_scan', type=int, default=1,
                        help='Maximum new entries per scan cycle (default: 1)')
    parser.add_argument('--cooldown', type=float, default=900,
                        help='Seconds before re-entering the same symbol after close/reject (default: 900)')
    parser.add_argument('--live', action='store_true',
                        help='Place real futures orders. Omit for paper trading.')
    parser.add_argument('--state_file', default='paper_state.json',
                        help='Paper trading state file (default: paper_state.json)')
    parser.add_argument('--resume_state', action='store_true',
                        help='Resume paper positions and stats from --state_file')

    # Strategy settings
    parser.add_argument('--strategy_mode', choices=['mean_reversion', 'breakout'], default='mean_reversion',
                        help='Trading strategy mode (default: mean_reversion)')
    parser.add_argument('--bb_period', type=int, default=20)
    parser.add_argument('--bb_stddev', type=float, default=2.0)
    parser.add_argument('--rsi_period', type=int, default=14)
    parser.add_argument('--rsi_oversold', type=float, default=30)
    parser.add_argument('--rsi_overbought', type=float, default=70)
    parser.add_argument('--volume_threshold', type=float, default=1.2)
    parser.add_argument('--stop_loss_atr', type=float, default=2.0)
    parser.add_argument('--take_profit', default='middle')
    parser.add_argument('--take_profit_strategy',
                        choices=['legacy', 'band', 'percent', 'atr', 'risk_reward', 'trailing'],
                        default='legacy')
    parser.add_argument('--take_profit_value', type=float, default=2.0)
    parser.add_argument('--take_profit_band', choices=['middle', 'outer'], default='middle')
    parser.add_argument('--risk_per_trade', type=float, default=2.0)
    parser.add_argument('--move_exits', action='store_true',
                        help='Move stop loss/take profit while holding')
    parser.add_argument('--min_bb_width', type=float, default=1.0)
    parser.add_argument('--max_bb_width', type=float, default=10.0)
    parser.add_argument('--min_confidence', type=int, default=50)
    parser.add_argument('--kline_limit', type=int, default=100)
    parser.add_argument('--wait_time', type=float, default=10,
                        help='Seconds between position tracking ticks (default: 10)')
    parser.add_argument('--max_trades', type=int, default=0,
                        help='Stop after this many closed trades across all symbols (0 = unlimited)')
    parser.add_argument('--commission', default='BNB')
    parser.add_argument('--debug', action='store_true')

    args = parser.parse_args()

    if args.leverage < 1 or args.leverage > 125:
        parser.error('--leverage must be between 1 and 125')
    if args.position_pct < 0 or args.position_pct > 100:
        parser.error('--position_pct must be between 0 and 100')
    if args.max_positions < 1:
        parser.error('--max_positions must be at least 1')
    if args.entries_per_scan < 1:
        parser.error('--entries_per_scan must be at least 1')

    return args


def setup_logging(debug=False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('auto_trade_movers.log'),
            logging.StreamHandler(sys.stdout),
        ]
    )


def bot_args(args, symbol):
    return argparse.Namespace(
        symbol=symbol,
        quantity=args.quantity,
        amount=args.amount,
        position_pct=args.position_pct,
        paper_balance=args.paper_balance,
        market_type=args.market_type,
        leverage=args.leverage,
        futures_side=args.futures_side,
        strategy_mode=args.strategy_mode,
        bb_period=args.bb_period,
        bb_stddev=args.bb_stddev,
        rsi_period=args.rsi_period,
        rsi_oversold=args.rsi_oversold,
        rsi_overbought=args.rsi_overbought,
        volume_threshold=args.volume_threshold,
        stop_loss_atr=args.stop_loss_atr,
        take_profit=args.take_profit,
        take_profit_strategy=args.take_profit_strategy,
        take_profit_value=args.take_profit_value,
        take_profit_band=args.take_profit_band,
        risk_per_trade=args.risk_per_trade,
        move_exits=args.move_exits,
        min_bb_width=args.min_bb_width,
        max_bb_width=args.max_bb_width,
        min_confidence=args.min_confidence,
        interval=args.scan_interval,
        kline_limit=args.kline_limit,
        wait_time=args.wait_time,
        max_trades=args.max_trades,
        test_mode=not args.live,
        debug=args.debug,
        commission=args.commission,
    )


def serialize_position(position):
    if not position:
        return None

    data = position.copy()
    timestamp = data.get('timestamp')
    if isinstance(timestamp, datetime):
        data['timestamp'] = timestamp.isoformat()
    return data


def deserialize_position(position):
    if not position:
        return None

    data = position.copy()
    timestamp = data.get('timestamp')
    if isinstance(timestamp, str):
        try:
            data['timestamp'] = datetime.fromisoformat(timestamp)
        except ValueError:
            data['timestamp'] = datetime.now()
    elif not isinstance(timestamp, datetime):
        data['timestamp'] = datetime.now()
    return data


def save_state(args, bots, cooldown_until, logger):
    if args.live or not args.state_file:
        return

    state = {
        'version': 1,
        'mode': 'paper',
        'saved_at': datetime.now().isoformat(),
        'settings': {
            'market_type': args.market_type,
            'strategy_mode': args.strategy_mode,
            'scan_interval': args.scan_interval,
            'leverage': args.leverage,
            'position_pct': args.position_pct,
            'paper_balance': args.paper_balance,
        },
        'cooldown_until': cooldown_until,
        'bots': {},
    }

    for symbol, bot in bots.items():
        state['bots'][symbol] = {
            'position': serialize_position(bot.position),
            'trades_executed': bot.trades_executed,
            'total_profit': bot.total_profit,
            'total_fees': bot.total_fees,
            'winning_trades': bot.winning_trades,
            'losing_trades': bot.losing_trades,
        }

    tmp_file = f'{args.state_file}.tmp'
    with open(tmp_file, 'w', encoding='utf-8') as file:
        json.dump(state, file, indent=2, sort_keys=True)
    os.replace(tmp_file, args.state_file)
    logger.debug(f'Paper state saved to {args.state_file}')


def load_state(args, logger):
    bots = {}
    cooldown_until = {}

    if args.live or not args.resume_state:
        return bots, cooldown_until

    if not args.state_file or not os.path.exists(args.state_file):
        logger.warning(f'No paper state file found: {args.state_file}')
        return bots, cooldown_until

    try:
        with open(args.state_file, 'r', encoding='utf-8') as file:
            state = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error(f'Unable to load paper state from {args.state_file}: {exc}')
        return bots, cooldown_until

    if state.get('mode') != 'paper':
        logger.warning(f'Ignoring non-paper state file: {args.state_file}')
        return bots, cooldown_until

    cooldown_until = {
        symbol: float(until)
        for symbol, until in state.get('cooldown_until', {}).items()
    }

    for symbol, bot_state in state.get('bots', {}).items():
        bot = BollingerTradingBot(bot_args(args, symbol))
        if not bot.validate_symbol():
            logger.warning(f'{symbol}: skipped restored state because symbol validation failed')
            continue

        bot.position = deserialize_position(bot_state.get('position'))
        bot.trades_executed = int(bot_state.get('trades_executed', 0))
        bot.total_profit = float(bot_state.get('total_profit', 0.0))
        bot.total_fees = float(bot_state.get('total_fees', 0.0))
        bot.winning_trades = int(bot_state.get('winning_trades', 0))
        bot.losing_trades = int(bot_state.get('losing_trades', 0))
        bots[symbol] = bot

        if bot.position:
            side = bot.position.get('side', 'LONG')
            quantity = bot.position.get('quantity', 0)
            price = bot.position.get('price', 0)
            logger.info(f'{symbol}: restored PAPER {side} position {quantity} @ {price:.8f}')

    open_positions = sum(1 for bot in bots.values() if bot.position)
    logger.info(
        f'Resumed paper state from {args.state_file}: '
        f'{len(bots)} bot(s), {open_positions} open position(s)'
    )
    return bots, cooldown_until


def scan_candidates(args, scan_client, logger):
    symbols = fetch_symbols(scan_client, args.market_type, args.quote_asset)
    tickers = fetch_tickers(scan_client)
    candidates = liquid_candidates(tickers, symbols, args.min_quote_volume, args.candidates)

    scan_mode = args.scan_mode
    if scan_mode == 'auto':
        scan_mode = 'trend' if args.strategy_mode == 'breakout' else 'mean_reversion'

    scan_args = argparse.Namespace(
        interval=args.scan_interval,
        scan_mode=scan_mode,
        kline_limit=max(args.kline_limit, args.bb_period + 20),
        bb_period=args.bb_period,
        bb_stddev=args.bb_stddev,
        min_score=args.min_mover_score,
        min_volume_ratio=args.min_volume_ratio,
        min_range_pct=args.min_range_pct,
        retries=args.scan_retries,
        retry_wait=args.scan_retry_wait,
    )

    results = []
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.scan_workers) as executor:
        futures = {
            executor.submit(score_symbol, scan_client, candidate, scan_args): candidate['symbol']
            for candidate in candidates
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
            except Exception:
                failures += 1
                continue
            if result:
                results.append(result)

    results.sort(key=lambda row: row['score'], reverse=True)
    logger.info(f'Scan found {len(results)} movers from {len(candidates)} candidates ({failures} request failures, mode={scan_mode})')
    return results[:args.top]


def direction_allowed(args, direction):
    if direction == 'LONG':
        return args.futures_side in ['LONG', 'BOTH']
    if direction == 'SHORT':
        return args.futures_side in ['SHORT', 'BOTH']
    return False


def maybe_open_position(args, mover, bots, cooldown_until, logger):
    symbol = mover['symbol']
    direction = mover['direction']

    if direction not in ['LONG', 'SHORT']:
        return False
    if not direction_allowed(args, direction):
        return False
    if symbol in bots and bots[symbol].position:
        return False
    if time.time() < cooldown_until.get(symbol, 0):
        return False

    bot = bots.get(symbol)
    if not bot:
        bot = BollingerTradingBot(bot_args(args, symbol))
        if not bot.validate_symbol():
            cooldown_until[symbol] = time.time() + args.cooldown
            save_state(args, bots, cooldown_until, logger)
            return False
        bots[symbol] = bot

    analysis = bot.analyze_market()
    if not analysis:
        cooldown_until[symbol] = time.time() + args.cooldown
        save_state(args, bots, cooldown_until, logger)
        return False

    logger.info(
        f'{symbol}: mover={direction} score={mover["score"]:.1f}, '
        f'strategy={analysis["signal"]} confidence={analysis["confidence"]:.0f}%'
    )

    opened = False
    if direction == 'LONG':
        if analysis['signal'] == 'BUY' and analysis['confidence'] >= args.min_confidence:
            opened = bot.execute_buy(analysis)
    elif direction == 'SHORT':
        if analysis['signal'] == 'SELL' and analysis['confidence'] >= args.min_confidence:
            opened = bot.execute_short(analysis)

    if opened:
        logger.info(f'{symbol}: opened {direction} after scanner + strategy confirmation')
        save_state(args, bots, cooldown_until, logger)
    else:
        cooldown_until[symbol] = time.time() + args.cooldown
        save_state(args, bots, cooldown_until, logger)

    return opened


def track_positions(args, bots, cooldown_until, logger):
    closed = 0
    for symbol, bot in list(bots.items()):
        if not bot.position:
            continue

        analysis = bot.analyze_market()
        if not analysis:
            continue

        exits_moved = bot.update_position_exits(analysis)
        if exits_moved:
            save_state(args, bots, cooldown_until, logger)

        side = bot.position.get('side', 'LONG')
        should_close = False
        reason = ''

        if side == 'SHORT':
            if analysis['price'] >= bot.position['stop_loss']:
                should_close = True
                reason = 'Stop Loss'
            elif bot.position['take_profit'] > 0 and analysis['price'] <= bot.position['take_profit']:
                should_close = True
                reason = 'Take Profit'
            elif analysis['signal'] == 'BUY' and analysis['confidence'] >= args.min_confidence:
                should_close = True
                reason = 'Signal'
        else:
            if analysis['price'] <= bot.position['stop_loss']:
                should_close = True
                reason = 'Stop Loss'
            elif bot.position['take_profit'] > 0 and analysis['price'] >= bot.position['take_profit']:
                should_close = True
                reason = 'Take Profit'
            elif analysis['signal'] in ['SELL', 'TAKE_PROFIT'] and analysis['confidence'] >= args.min_confidence:
                should_close = True
                reason = 'Signal'

        if should_close and bot.execute_sell(analysis, reason):
            closed += 1
            cooldown_until[symbol] = time.time() + args.cooldown
            logger.info(f'{symbol}: closed {side} ({reason})')
            save_state(args, bots, cooldown_until, logger)

    return closed


def total_closed_trades(bots):
    return sum(bot.trades_executed for bot in bots.values())


def main():
    args = parse_args()
    setup_logging(args.debug)
    logger = logging.getLogger('AutoTradeMovers')

    mode = 'LIVE FUTURES ORDERS' if args.live else 'PAPER TRADING'
    logger.info(f'Starting auto mover trader in {mode}')
    logger.info(
        f'Sizing: position_pct={args.position_pct}%, leverage={args.leverage}x, '
        f'max_positions={args.max_positions}, entries_per_scan={args.entries_per_scan}'
    )
    logger.info(f'Strategy mode: {args.strategy_mode}, scan mode: {args.scan_mode}')

    if args.live:
        print('WARNING: --live will place real Binance futures orders.')
        response = input('Type "START" to begin live auto trading, or anything else to exit: ')
        if response.strip().upper() != 'START':
            print('Exiting...')
            return

    scan_client = make_client(args.market_type)
    bots, cooldown_until = load_state(args, logger)
    next_scan_at = 0

    while True:
        closed = track_positions(args, bots, cooldown_until, logger)

        if args.max_trades > 0 and total_closed_trades(bots) >= args.max_trades:
            logger.info(f'Max closed trades reached ({args.max_trades}). Stopping.')
            break

        if time.time() >= next_scan_at:
            open_positions = sum(1 for bot in bots.values() if bot.position)
            slots = max(args.max_positions - open_positions, 0)

            if slots > 0:
                movers = scan_candidates(args, scan_client, logger)
                entries_left = min(args.entries_per_scan, slots)

                for mover in movers:
                    if entries_left <= 0:
                        break
                    if maybe_open_position(args, mover, bots, cooldown_until, logger):
                        entries_left -= 1
            else:
                logger.info(f'Max positions reached ({args.max_positions}); tracking only this cycle')

            next_scan_at = time.time() + args.scan_every

        if closed:
            logger.info(f'Closed {closed} position(s) this tick')

        time.sleep(args.wait_time)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nAuto trader stopped by user.')
