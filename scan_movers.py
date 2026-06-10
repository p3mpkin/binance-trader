#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# Scan Binance markets for unusual movers.

import argparse
import concurrent.futures
import sys
import time
from typing import Dict, List, Optional

sys.path.insert(0, './app')

import config
from BinanceAPI import BinanceAPI
from FuturesAPI import FuturesAPI
from Indicators import Indicators


def parse_args():
    parser = argparse.ArgumentParser(
        description='Scan Binance markets for volume, volatility, and Bollinger Band anomalies'
    )
    parser.add_argument('--market_type', choices=['futures', 'spot'], default='futures',
                        help='Market to scan (default: futures)')
    parser.add_argument('--quote_asset', default='USDT',
                        help='Quote asset to scan (default: USDT)')
    parser.add_argument('--interval', default='5m',
                        help='Kline interval for anomaly scan (default: 5m)')
    parser.add_argument('--scan_mode', choices=['trend', 'mean_reversion'], default='trend',
                        help='Direction mode: trend follows breakouts, mean_reversion fades extremes (default: trend)')
    parser.add_argument('--kline_limit', type=int, default=60,
                        help='Klines per symbol (default: 60)')
    parser.add_argument('--candidates', type=int, default=120,
                        help='Most liquid symbols to inspect with klines (default: 120)')
    parser.add_argument('--top', type=int, default=20,
                        help='Number of rows to print (default: 20)')
    parser.add_argument('--min_quote_volume', type=float, default=50000000,
                        help='Minimum 24h quote volume (default: 50000000)')
    parser.add_argument('--min_score', type=float, default=0,
                        help='Minimum anomaly score to print (default: 0)')
    parser.add_argument('--min_volume_ratio', type=float, default=0,
                        help='Minimum latest-volume/average-volume ratio (default: 0)')
    parser.add_argument('--min_range_pct', type=float, default=0,
                        help='Minimum latest candle range percent (default: 0)')
    parser.add_argument('--bb_period', type=int, default=20,
                        help='Bollinger Bands period (default: 20)')
    parser.add_argument('--bb_stddev', type=float, default=2.0,
                        help='Bollinger Bands std dev multiplier (default: 2.0)')
    parser.add_argument('--workers', type=int, default=8,
                        help='Concurrent kline requests (default: 8)')
    parser.add_argument('--retries', type=int, default=2,
                        help='Retries per symbol when fetching klines (default: 2)')
    parser.add_argument('--retry_wait', type=float, default=0.5,
                        help='Seconds to wait between retries (default: 0.5)')
    return parser.parse_args()


def make_client(market_type: str):
    if market_type == 'futures':
        return FuturesAPI(config.api_key, config.api_secret)
    return BinanceAPI(config.api_key, config.api_secret)


def interval_to_seconds(interval: str) -> int:
    multipliers = {'m': 60, 'h': 3600, 'd': 86400}
    return int(interval[:-1]) * multipliers.get(interval[-1], 60)


def fetch_symbols(client, market_type: str, quote_asset: str) -> set:
    info = client.get_exchange_info()
    if isinstance(info, dict) and 'msg' in info and 'symbols' not in info:
        raise RuntimeError(info['msg'])

    symbols = set()
    for item in info.get('symbols', []):
        if item.get('quoteAsset') != quote_asset:
            continue
        if item.get('status') != 'TRADING':
            continue
        if market_type == 'futures' and item.get('contractType') != 'PERPETUAL':
            continue
        symbols.add(item['symbol'])

    return symbols


def fetch_tickers(client) -> List[Dict]:
    tickers = client.get_tickers()
    if isinstance(tickers, dict) and 'msg' in tickers:
        raise RuntimeError(tickers['msg'])
    if not isinstance(tickers, list):
        raise RuntimeError(f'Unexpected ticker response: {tickers}')
    return tickers


def liquid_candidates(tickers: List[Dict], symbols: set, min_quote_volume: float, limit: int) -> List[Dict]:
    rows = []
    for ticker in tickers:
        symbol = ticker.get('symbol')
        if symbol not in symbols:
            continue

        quote_volume = float(ticker.get('quoteVolume', 0) or 0)
        if quote_volume < min_quote_volume:
            continue

        rows.append({
            'symbol': symbol,
            'quote_volume': quote_volume,
            'price_change_pct_24h': float(ticker.get('priceChangePercent', 0) or 0),
            'last_price': float(ticker.get('lastPrice', 0) or 0),
        })

    rows.sort(key=lambda row: row['quote_volume'], reverse=True)
    return rows[:limit]


def fetch_klines(client, symbol: str, interval: str, limit: int, retries: int = 2, retry_wait: float = 0.5):
    end_time = int(time.time() * 1000)
    start_time = end_time - interval_to_seconds(interval) * 1000 * limit

    last_error = None
    for attempt in range(retries + 1):
        try:
            return client.get_klines(symbol, interval, start_time, end_time, limit=limit)
        except TypeError:
            return client.get_klines(symbol, interval, start_time, end_time)
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(retry_wait * (attempt + 1))

    raise last_error


def score_symbol(client, candidate: Dict, args) -> Optional[Dict]:
    symbol = candidate['symbol']
    klines = fetch_klines(client, symbol, args.interval, args.kline_limit, args.retries, args.retry_wait)

    if isinstance(klines, dict):
        return None
    if not isinstance(klines, list) or len(klines) < max(args.bb_period, 21):
        return None

    closes = [float(kline[4]) for kline in klines]
    highs = [float(kline[2]) for kline in klines]
    lows = [float(kline[3]) for kline in klines]
    volumes = [float(kline[5]) for kline in klines]

    price = closes[-1]
    upper, middle, lower = Indicators.bollinger_bands(closes, args.bb_period, args.bb_stddev)
    if upper is None:
        return None

    previous_volumes = volumes[-21:-1]
    avg_volume = sum(previous_volumes) / len(previous_volumes) if previous_volumes else 0
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1.0
    range_pct = ((highs[-1] - lows[-1]) / price) * 100 if price else 0
    lookback_change_pct = ((closes[-1] - closes[0]) / closes[0]) * 100 if closes[0] else 0
    bb_width = Indicators.bb_width(upper, lower, middle)
    bb_percent = Indicators.bb_percent(price, upper, lower)
    rsi = Indicators.rsi(closes)

    breakout = 'inside'
    direction = 'WATCH'
    if price > upper:
        breakout = 'breakout_up'
        direction = 'LONG' if args.scan_mode == 'trend' else 'SHORT'
    elif price < lower:
        breakout = 'breakdown'
        direction = 'SHORT' if args.scan_mode == 'trend' else 'LONG'
    elif bb_percent >= 0.85:
        breakout = 'near_upper'
        direction = 'LONG' if args.scan_mode == 'trend' else 'SHORT'
    elif bb_percent <= 0.15:
        breakout = 'near_lower'
        direction = 'SHORT' if args.scan_mode == 'trend' else 'LONG'

    score = 0.0
    score += min(abs(candidate['price_change_pct_24h']) * 1.2, 25)
    score += min(max(volume_ratio - 1, 0) * 18, 30)
    score += min(range_pct * 10, 25)
    score += min(bb_width * 1.5, 20)
    if breakout in ['breakout_up', 'breakdown']:
        score += 15
    elif breakout in ['near_upper', 'near_lower']:
        score += 8

    result = {
        'symbol': symbol,
        'score': score,
        'direction': direction,
        'breakout': breakout,
        'price': price,
        'change_24h': candidate['price_change_pct_24h'],
        'lookback_change': lookback_change_pct,
        'quote_volume': candidate['quote_volume'],
        'volume_ratio': volume_ratio,
        'range_pct': range_pct,
        'bb_width': bb_width,
        'bb_percent': bb_percent,
        'rsi': rsi,
        'scan_mode': args.scan_mode,
    }

    if result['score'] < args.min_score:
        return None
    if result['volume_ratio'] < args.min_volume_ratio:
        return None
    if result['range_pct'] < args.min_range_pct:
        return None

    return result


def print_table(rows: List[Dict], args):
    if not rows:
        print('No movers matched the filters.')
        return

    header = (
        f'{"Symbol":<14} {"Score":>6} {"Dir":>6} {"24h%":>8} {"Lookbk%":>8} '
        f'{"VolX":>7} {"Range%":>7} {"BBW%":>7} {"%B":>6} {"RSI":>6} {"QuoteVol":>12}  Signal'
    )
    print(header)
    print('-' * len(header))

    for row in rows[:args.top]:
        quote_volume_m = row['quote_volume'] / 1000000
        print(
            f'{row["symbol"]:<14} '
            f'{row["score"]:>6.1f} '
            f'{row["direction"]:>6} '
            f'{row["change_24h"]:>8.2f} '
            f'{row["lookback_change"]:>8.2f} '
            f'{row["volume_ratio"]:>7.2f} '
            f'{row["range_pct"]:>7.2f} '
            f'{row["bb_width"]:>7.2f} '
            f'{row["bb_percent"]:>6.2f} '
            f'{row["rsi"]:>6.1f} '
            f'{quote_volume_m:>10.1f}M  '
            f'{row["breakout"]}'
        )


def main():
    args = parse_args()
    client = make_client(args.market_type)

    symbols = fetch_symbols(client, args.market_type, args.quote_asset)
    tickers = fetch_tickers(client)
    candidates = liquid_candidates(tickers, symbols, args.min_quote_volume, args.candidates)

    print(
        f'Scanning {len(candidates)} {args.quote_asset} {args.market_type} symbols '
        f'on {args.interval} candles ({args.scan_mode})...'
    )

    results = []
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(score_symbol, client, candidate, args): candidate['symbol']
            for candidate in candidates
        }
        for future in concurrent.futures.as_completed(futures):
            symbol = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                failures.append((symbol, str(exc)))
                continue

            if result:
                results.append(result)

    results.sort(key=lambda row: row['score'], reverse=True)
    print_table(results, args)

    if failures:
        failed_symbols = ', '.join(symbol for symbol, _ in failures[:10])
        suffix = '...' if len(failures) > 10 else ''
        print(f'\nSkipped {len(failures)} symbols due to request errors: {failed_symbols}{suffix}')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nScan stopped by user.')
    except Exception as exc:
        print(f'Scan failed: {exc}')
        sys.exit(1)
