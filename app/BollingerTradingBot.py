# -*- coding: UTF-8 -*-
# Bollinger Bands Trading Bot - Main Implementation

import time
import logging
import math
from datetime import datetime
from typing import Optional, Dict

import config
from BinanceAPI import BinanceAPI
from FuturesAPI import FuturesAPI
from BollingerStrategy import BollingerStrategy
from Orders import Orders
from Database import Database


class BollingerTradingBot:
    """
    Advanced Bollinger Bands Trading Bot for Binance

    Features:
    - Bollinger Bands with RSI and Volume confirmation
    - Dynamic risk management
    - Position sizing
    - Comprehensive logging
    """

    # Commission rates
    TOKEN_COMMISSION = 0.001  # 0.1%
    BNB_COMMISSION = 0.0005   # 0.05%

    def __init__(self, args):
        """
        Initialize the trading bot

        Args:
            args: Parsed command line arguments
        """
        self.args = args
        self.symbol = args.symbol
        self.logger = logging.getLogger(f'BollingerBot-{self.symbol}')
        self.market_type = getattr(args, 'market_type', 'futures')
        self.futures_side = getattr(args, 'futures_side', 'LONG')
        self.leverage = getattr(args, 'leverage', 1)
        self.paper_balance = getattr(args, 'paper_balance', 1000.0)

        # Initialize Binance API client
        if self.market_type == 'futures':
            self.client = FuturesAPI(config.api_key, config.api_secret)
        else:
            self.client = BinanceAPI(config.api_key, config.api_secret)

        # Set commission type
        self.commission = self.BNB_COMMISSION if args.commission == 'BNB' else self.TOKEN_COMMISSION

        # Initialize strategy
        strategy_config = {
            'strategy_mode': getattr(args, 'strategy_mode', 'mean_reversion'),
            'bb_period': args.bb_period,
            'bb_std_dev': args.bb_stddev,
            'rsi_period': args.rsi_period,
            'rsi_oversold': args.rsi_oversold,
            'rsi_overbought': args.rsi_overbought,
            'volume_threshold': args.volume_threshold,
            'stop_loss_atr': args.stop_loss_atr,
            'take_profit': args.take_profit,
            'take_profit_strategy': getattr(args, 'take_profit_strategy', 'legacy'),
            'take_profit_value': getattr(args, 'take_profit_value', 2.0),
            'take_profit_band': getattr(args, 'take_profit_band', 'middle'),
            'min_bb_width': args.min_bb_width,
            'max_bb_width': args.max_bb_width
        }
        self.strategy = BollingerStrategy(strategy_config)

        # Trading state
        self.position = None  # Current position {price, quantity, timestamp, order_id}
        self.trades_executed = 0
        self.total_profit = 0.0
        self.total_fees = 0.0
        self.winning_trades = 0
        self.losing_trades = 0

        # Market filters (populated during validation)
        self.step_size = 0
        self.tick_size = 0
        self.min_qty = 0
        self.min_notional = 0

    def validate_symbol(self) -> bool:
        """
        Validate symbol and get trading rules

        Returns:
            True if symbol is valid
        """
        try:
            if self.market_type == 'futures':
                info = self.client.get_exchange_info()
                if isinstance(info, dict) and 'msg' in info and 'symbols' not in info:
                    self.logger.error(f'Binance futures exchangeInfo error: {info["msg"]}')
                    return False
                symbol_info = next((market for market in info.get('symbols', []) if market['symbol'] == self.symbol), None)
            else:
                symbol_info = Orders.get_info(self.symbol)

            if not symbol_info:
                self.logger.error(f'Invalid symbol: {self.symbol}')
                return False

            # Extract filters
            filters = {item['filterType']: item for item in symbol_info['filters']}

            self.step_size = float(filters['LOT_SIZE']['stepSize'])
            self.tick_size = float(filters['PRICE_FILTER']['tickSize'])
            self.min_qty = float(filters['LOT_SIZE']['minQty'])
            
            # Spot and futures exchangeInfo use slightly different field names.
            notional_filter = filters.get('MIN_NOTIONAL') or filters.get('NOTIONAL') or {}
            self.min_notional = float(
                notional_filter.get(
                    'minNotional',
                    notional_filter.get('notional', notional_filter.get('minNotionalValue', 0))
                )
            )

            self.logger.info(f'Symbol validated: {self.symbol} ({self.market_type})')
            self.logger.debug(f'Step size: {self.step_size}, Tick size: {self.tick_size}')
            self.logger.debug(f'Min qty: {self.min_qty}, Min notional: {self.min_notional}')

            if self.market_type == 'futures' and not self.args.test_mode:
                leverage_result = self.client.change_leverage(self.symbol, self.leverage)
                if isinstance(leverage_result, dict) and 'leverage' in leverage_result:
                    self.logger.info(f'Futures leverage set: {leverage_result["leverage"]}x')
                else:
                    self.logger.error(f'Unable to set futures leverage: {leverage_result}')
                    return False

            return True

        except Exception as e:
            self.logger.error(f'Symbol validation error: {e}')
            self.logger.debug('Symbol validation traceback', exc_info=True)
            return False

    def format_quantity(self, quantity: float) -> float:
        """Format quantity according to step size"""
        return float(self.step_size * math.floor(quantity / self.step_size))

    def format_price(self, price: float) -> float:
        """Format price according to tick size"""
        return float(self.tick_size * math.floor(price / self.tick_size))

    def _calculate_quantity(self, analysis: Dict) -> float:
        """Calculate order quantity from CLI sizing options."""
        if self.args.quantity > 0:
            quantity = self.args.quantity
        elif getattr(self.args, 'position_pct', 0) > 0:
            balance = self.paper_balance if self.args.test_mode else self._get_balance()
            margin = balance * (self.args.position_pct / 100)
            notional = margin * self.leverage if self.market_type == 'futures' else margin
            quantity = notional / analysis['entry_price'] if analysis['entry_price'] else 0
        elif self.args.amount > 0:
            quantity = self.args.amount / analysis['entry_price']
        else:
            # Use strategy-based position sizing
            balance = self._get_balance()
            quantity = self.strategy.calculate_position_size(
                balance,
                analysis['entry_price'],
                self.args.risk_per_trade,
                analysis['stop_loss']
            )

        return self.format_quantity(quantity)

    def _log_trade_stats(self, prefix: str = 'Stats'):
        """Log cumulative performance statistics."""
        if self.trades_executed <= 0:
            return

        win_rate = (self.winning_trades / self.trades_executed) * 100
        self.logger.info(
            f'📊 {prefix}: {self.trades_executed} trades, '
            f'Win rate: {win_rate:.1f}%, '
            f'Total P/L: {self.total_profit:.8f}, '
            f'Fees: {self.total_fees:.8f}'
        )

    def update_position_exits(self, analysis: Dict) -> bool:
        """Move stop loss and take profit in the favorable direction while holding."""
        if not self.position or not getattr(self.args, 'move_exits', False):
            return False

        indicators = analysis.get('indicators', {})
        atr = indicators.get('atr', 0.0)
        if atr <= 0:
            return False

        price = analysis['price']
        position_side = self.position.get('side', 'LONG')
        old_stop = self.position['stop_loss']
        old_take = self.position['take_profit']

        if position_side == 'SHORT':
            new_stop = price + (atr * self.args.stop_loss_atr)
            if old_stop <= 0 or new_stop < old_stop:
                self.position['stop_loss'] = new_stop

            target = indicators.get('bb_lower', old_take)
            if old_take > 0 and target < old_take:
                self.position['take_profit'] = target
        else:
            new_stop = price - (atr * self.args.stop_loss_atr)
            if new_stop > old_stop:
                self.position['stop_loss'] = new_stop

            target = indicators.get('bb_upper', old_take)
            if old_take > 0 and target > old_take:
                self.position['take_profit'] = target

        if self.position['stop_loss'] != old_stop or self.position['take_profit'] != old_take:
            self.logger.info(
                f'↕️  Moved exits: Stop Loss {old_stop:.8f} -> {self.position["stop_loss"]:.8f}, '
                f'Take Profit {old_take:.8f} -> {self.position["take_profit"]:.8f}'
            )
            return True

        return False

    def get_klines(self) -> list:
        """
        Fetch historical kline data

        Returns:
            List of klines
        """
        try:
            # Calculate time range
            interval_seconds = self._interval_to_seconds(self.args.interval)
            end_time = int(time.time() * 1000)
            start_time = end_time - (interval_seconds * 1000 * self.args.kline_limit)

            klines = self.client.get_klines(
                self.symbol,
                self.args.interval,
                start_time,
                end_time
            )

            if isinstance(klines, dict):
                self.logger.error(f'Binance kline API error: {klines.get("msg", klines)}')
                return []

            if not isinstance(klines, list):
                self.logger.error(f'Unexpected kline response: {klines}')
                return []

            return klines

        except Exception as e:
            self.logger.error(f'Error fetching klines: {e}')
            return []

    def _interval_to_seconds(self, interval: str) -> int:
        """Convert interval string to seconds"""
        multipliers = {
            'm': 60,
            'h': 3600,
            'd': 86400
        }
        unit = interval[-1]
        value = int(interval[:-1])
        return value * multipliers.get(unit, 60)

    def analyze_market(self) -> Optional[Dict]:
        """
        Analyze current market conditions

        Returns:
            Analysis result dictionary or None
        """
        try:
            self.logger.debug(f'Starting market analysis...')
            
            # Get current price and volume
            self.logger.debug(f'Fetching ticker for {self.symbol}...')
            ticker = self.client.get_ticker(self.symbol)

            if not isinstance(ticker, dict) or 'lastPrice' not in ticker:
                self.logger.error(f'Binance ticker API error: {ticker}')
                return None

            current_price = float(ticker['lastPrice'])
            current_volume = float(ticker['volume'])
            self.logger.debug(f'Ticker received: price={current_price}, volume={current_volume}')

            # Get historical data
            self.logger.debug(f'Fetching klines...')
            klines = self.get_klines()
            self.logger.debug(f'Klines received: {len(klines)} candles')

            if not klines:
                self.logger.warning('No kline data available')
                return None

            # Run strategy analysis
            self.logger.debug(f'Running strategy analysis...')
            analysis = self.strategy.analyze(klines, current_price, current_volume)
            self.logger.debug(f'Analysis complete')

            return analysis

        except Exception as e:
            self.logger.error(f'Market analysis error: {e}')
            self.logger.debug('Market analysis traceback', exc_info=True)
            return None

    def _prepare_entry_analysis(self, analysis: Dict, position_side: str) -> Dict:
        """Normalize entry, stop loss, and take profit for long or short entries."""
        prepared = analysis.copy()

        if position_side == 'LONG':
            prepared['entry_price'] = prepared.get('entry_price') or prepared['price']
            return prepared

        price = prepared['price']
        indicators = prepared.get('indicators', {})
        atr = indicators.get('atr', 0.0)
        middle = indicators.get('bb_middle', price)
        lower = indicators.get('bb_lower', price)

        prepared['entry_price'] = price
        if prepared.get('stop_loss', 0) > 0 and prepared.get('take_profit', 0) > 0:
            return prepared

        prepared['stop_loss'] = price + (atr * self.args.stop_loss_atr)

        if getattr(self.args, 'take_profit_strategy', 'legacy') == 'trailing' or self.args.take_profit == 'trailing':
            prepared['take_profit'] = 0.0
        elif getattr(self.args, 'take_profit_strategy', 'legacy') == 'percent':
            prepared['take_profit'] = price * (1 - float(self.args.take_profit_value) / 100)
        elif getattr(self.args, 'take_profit_strategy', 'legacy') == 'atr':
            prepared['take_profit'] = price - (atr * float(self.args.take_profit_value))
        elif getattr(self.args, 'take_profit_strategy', 'legacy') == 'risk_reward':
            risk = abs(prepared['stop_loss'] - price)
            prepared['take_profit'] = price - (risk * float(self.args.take_profit_value))
        elif getattr(self.args, 'take_profit_strategy', 'legacy') == 'band':
            prepared['take_profit'] = middle if self.args.take_profit_band == 'middle' else lower
        elif self.args.take_profit == 'middle':
            prepared['take_profit'] = middle
        elif self.args.take_profit == 'upper':
            prepared['take_profit'] = lower
        else:
            prepared['take_profit'] = price * (1 - float(self.args.take_profit) / 100)

        return prepared

    def execute_buy(self, analysis: Dict) -> bool:
        """Open a long position."""
        return self.execute_entry(analysis, 'LONG')

    def execute_short(self, analysis: Dict) -> bool:
        """Open a short futures position."""
        if self.market_type != 'futures':
            self.logger.warning('Short entries are only supported in futures mode')
            return False
        return self.execute_entry(analysis, 'SHORT')

    def execute_entry(self, analysis: Dict, position_side: str) -> bool:
        """
        Open a position. LONG is supported for spot/futures; SHORT requires futures.
        """
        if position_side == 'SHORT' and self.market_type != 'futures':
            return False

        analysis = self._prepare_entry_analysis(analysis, position_side)

        try:
            quantity = self._calculate_quantity(analysis)

            if quantity <= 0:
                self.logger.warning('[PAPER] Quantity is zero; set --amount or --quantity')
                return False

            if quantity < self.min_qty:
                self.logger.warning(f'Quantity {quantity} below minimum {self.min_qty}')
                return False

            entry_price = self.format_price(analysis['entry_price'])
            notional = entry_price * quantity

            if self.min_notional and notional < self.min_notional:
                self.logger.warning(f'Notional {notional:.8f} below minimum {self.min_notional}')
                return False

            if self.args.test_mode:
                self.position = {
                    'order_id': f'PAPER-{int(time.time() * 1000)}',
                    'side': position_side,
                    'quantity': quantity,
                    'price': entry_price,
                    'timestamp': datetime.now(),
                    'stop_loss': analysis['stop_loss'],
                    'take_profit': analysis['take_profit'],
                    'entry_reason': analysis.get('reason', '')
                }

                self.logger.info(f'[PAPER] {position_side} opened: {quantity} @ {entry_price:.8f}')
                self.logger.info(f'[PAPER] Notional: {notional:.8f}, Leverage: {self.leverage}x')
                self.logger.info(f'[PAPER] Stop Loss: {analysis["stop_loss"]:.8f}, Take Profit: {analysis["take_profit"]:.8f}')
                return True

            if self.market_type == 'futures':
                order_side = 'BUY' if position_side == 'LONG' else 'SELL'
                order = self.client.market_order(self.symbol, order_side, quantity, reduce_only=False)

                if not order or 'orderId' not in order:
                    self.logger.error(f'Futures entry order failed: {order}')
                    return False

                self.position = {
                    'order_id': order['orderId'],
                    'side': position_side,
                    'quantity': quantity,
                    'price': entry_price,
                    'timestamp': datetime.now(),
                    'stop_loss': analysis['stop_loss'],
                    'take_profit': analysis['take_profit']
                }

                self.logger.info(f'✅ Futures {position_side} opened: ID {order["orderId"]}')
                self.logger.info(f'   Quantity: {quantity}, Reference Price: {entry_price:.8f}, Leverage: {self.leverage}x')
                return True

            # Spot live trading remains long-only and uses the existing limit-order flow.
            bid_price, ask_price = Orders.get_order_book(self.symbol)
            buy_price = self.format_price(bid_price + self.tick_size)
            self.logger.info(f'🔵 Placing BUY order: {quantity} @ {buy_price}')
            order_id = Orders.buy_limit(self.symbol, quantity, buy_price)

            if order_id:
                self.position = {
                    'order_id': order_id,
                    'side': 'LONG',
                    'quantity': quantity,
                    'price': buy_price,
                    'timestamp': datetime.now(),
                    'stop_loss': analysis['stop_loss'],
                    'take_profit': analysis['take_profit']
                }

                Database.write([
                    order_id,
                    self.symbol,
                    0,
                    buy_price,
                    'BUY',
                    quantity,
                    self.args.risk_per_trade
                ])

                self.logger.info(f'✅ Buy order placed: ID {order_id}')
                return True

        except Exception as e:
            self.logger.error(f'Entry order error: {e}', exc_info=True)

        return False

    def execute_sell(self, analysis: Dict, reason: str = 'Signal') -> bool:
        """Close the current position."""
        if not self.position:
            return False

        try:
            quantity = self.position['quantity']
            entry_price = self.position['price']
            exit_price = self.format_price(analysis['price'])
            position_side = self.position.get('side', 'LONG')

            if self.args.test_mode:
                return self._close_paper_position(quantity, entry_price, exit_price, position_side, reason)

            if self.market_type == 'futures':
                order_side = 'SELL' if position_side == 'LONG' else 'BUY'
                order = self.client.market_order(self.symbol, order_side, quantity, reduce_only=True)

                if not order or 'orderId' not in order:
                    self.logger.error(f'Futures close order failed: {order}')
                    return False

                self._record_closed_trade(quantity, entry_price, exit_price, position_side)
                self.logger.info(f'✅ Futures {position_side} closed: ID {order["orderId"]} ({reason})')
                self.logger.info(f'   Entry: {entry_price:.8f}, Exit Reference: {exit_price:.8f}')
                self._log_trade_stats()
                self.position = None
                return True

            bid_price, ask_price = Orders.get_order_book(self.symbol)
            sell_price = self.format_price(ask_price - self.tick_size)
            sell_order = Orders.sell_limit(self.symbol, quantity, sell_price)

            if sell_order and 'orderId' in sell_order:
                self._record_closed_trade(quantity, entry_price, sell_price, 'LONG')
                self.logger.info(f'✅ Sell order placed: ID {sell_order["orderId"]}')
                self.logger.info(f'   Buy Price: {entry_price:.8f}, Sell Price: {sell_price:.8f}')
                self._log_trade_stats()
                self.position = None
                return True

        except Exception as e:
            self.logger.error(f'Close order error: {e}', exc_info=True)

        return False

    def _calculate_profit(self, quantity: float, entry_price: float, exit_price: float, position_side: str) -> float:
        if position_side == 'SHORT':
            return (entry_price - exit_price) * quantity
        return (exit_price - entry_price) * quantity

    def _record_closed_trade(self, quantity: float, entry_price: float, exit_price: float, position_side: str):
        gross_profit = self._calculate_profit(quantity, entry_price, exit_price, position_side)
        fees = ((entry_price * quantity) + (exit_price * quantity)) * self.commission
        net_profit = gross_profit - fees

        self.trades_executed += 1
        self.total_profit += net_profit
        self.total_fees += fees

        if net_profit > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1

        return net_profit, fees

    def _close_paper_position(self, quantity: float, entry_price: float, exit_price: float, position_side: str, reason: str) -> bool:
        net_profit, fees = self._record_closed_trade(quantity, entry_price, exit_price, position_side)
        notional = entry_price * quantity
        margin = notional / self.leverage if self.market_type == 'futures' and self.leverage else notional
        profit_pct = (net_profit / margin) * 100 if margin else 0
        held_seconds = (datetime.now() - self.position['timestamp']).total_seconds()

        self.logger.info(f'[PAPER] {position_side} closed: {quantity} @ {exit_price:.8f} ({reason})')
        self.logger.info(f'[PAPER] Net Profit: {net_profit:.8f} ({profit_pct:.2f}% on margin), Fees: {fees:.8f}')
        self.logger.info(f'[PAPER] Entry: {entry_price:.8f}, Exit: {exit_price:.8f}, Held: {held_seconds:.0f}s')
        self._log_trade_stats('Paper Stats')

        self.position = None
        return True

    def _get_balance(self) -> float:
        """Get available balance for base asset"""
        try:
            if self.market_type == 'futures':
                balances = self.client.get_balance()
                if isinstance(balances, dict):
                    self.logger.error(f'Futures balance API error: {balances.get("msg", balances)}')
                    return 0.0

                for item in balances:
                    if item.get('asset') == 'USDT':
                        return float(item.get('availableBalance', item.get('balance', 0)))

                return 0.0

            # Extract base asset from symbol (e.g., USDT from BTCUSDT)
            # This is simplified - you may need to adjust based on your symbol
            if 'USDT' in self.symbol:
                asset = 'USDT'
            elif 'BTC' in self.symbol:
                asset = 'BTC'
            elif 'ETH' in self.symbol:
                asset = 'ETH'
            elif 'BNB' in self.symbol:
                asset = 'BNB'
            else:
                asset = 'USDT'  # Default

            account = self.client.get_account()
            balances = {item['asset']: item for item in account['balances']}

            if asset in balances:
                return float(balances[asset]['free'])

        except Exception as e:
            self.logger.error(f'Error getting balance: {e}')

        return 0.0

    def run(self):
        """Main bot loop"""
        self.logger.info('Starting Bollinger Bands Trading Bot...')

        # Validate symbol
        if not self.validate_symbol():
            self.logger.error('Symbol validation failed. Exiting.')
            return

        self.logger.info('Bot started successfully. Running...')
        cycle = 0

        try:
            while True:
                cycle += 1
                self.logger.debug(f'=== Cycle {cycle} starting ===')

                # Check max trades limit
                if self.args.max_trades > 0 and self.trades_executed >= self.args.max_trades:
                    self.logger.info(f'Max trades limit reached ({self.args.max_trades}). Stopping.')
                    break

                # Analyze market
                self.logger.debug(f'Cycle {cycle}: Calling analyze_market()...')
                analysis = self.analyze_market()
                self.logger.debug(f'Cycle {cycle}: analyze_market() returned')

                if not analysis:
                    self.logger.warning('Analysis failed, skipping cycle')
                    time.sleep(self.args.wait_time)
                    continue

                # Log current state (always visible, not just debug)
                self.logger.info(f'Cycle {cycle}: Price={analysis["price"]:.8f}, Signal={analysis["signal"]}, Confidence={analysis["confidence"]:.0f}%')

                # Trading logic
                if self.position is None:
                    # No position - look for entry signals
                    if analysis['signal'] == 'BUY' and analysis['confidence'] >= self.args.min_confidence:
                        if self.futures_side in ['LONG', 'BOTH']:
                            self.logger.info(f'📊 LONG Signal: {analysis["reason"]} (Confidence: {analysis["confidence"]:.0f}%)')
                            self.execute_buy(analysis)

                    elif (
                        self.market_type == 'futures'
                        and self.futures_side in ['SHORT', 'BOTH']
                        and analysis['signal'] == 'SELL'
                        and analysis['confidence'] >= self.args.min_confidence
                    ):
                        self.logger.info(f'📊 SHORT Signal: {analysis["reason"]} (Confidence: {analysis["confidence"]:.0f}%)')
                        self.execute_short(analysis)

                else:
                    self.update_position_exits(analysis)
                    position_side = self.position.get('side', 'LONG')

                    if position_side == 'SHORT':
                        if analysis['price'] >= self.position['stop_loss']:
                            self.logger.warning(f'⚠️  SHORT Stop Loss triggered at {analysis["price"]:.8f}')
                            self.execute_sell(analysis, 'Stop Loss')

                        elif self.position['take_profit'] > 0 and analysis['price'] <= self.position['take_profit']:
                            self.logger.info(f'🎯 SHORT Take Profit target reached at {analysis["price"]:.8f}')
                            self.execute_sell(analysis, 'Take Profit')

                        elif analysis['signal'] == 'BUY' and analysis['confidence'] >= self.args.min_confidence:
                            self.logger.info(f'📊 SHORT close signal: {analysis["reason"]} (Confidence: {analysis["confidence"]:.0f}%)')
                            self.execute_sell(analysis, 'Signal')

                    else:
                        if analysis['price'] <= self.position['stop_loss']:
                            self.logger.warning(f'⚠️  LONG Stop Loss triggered at {analysis["price"]:.8f}')
                            self.execute_sell(analysis, 'Stop Loss')

                        elif self.position['take_profit'] > 0 and analysis['price'] >= self.position['take_profit']:
                            self.logger.info(f'🎯 LONG Take Profit target reached at {analysis["price"]:.8f}')
                            self.execute_sell(analysis, 'Take Profit')

                        elif analysis['signal'] in ['SELL', 'TAKE_PROFIT'] and analysis['confidence'] >= self.args.min_confidence:
                            self.logger.info(f'📊 LONG close signal: {analysis["reason"]} (Confidence: {analysis["confidence"]:.0f}%)')
                            self.execute_sell(analysis, 'Signal')

                # Wait for next cycle
                self.logger.debug(f'Cycle {cycle}: Waiting {self.args.wait_time}s before next cycle...')
                time.sleep(self.args.wait_time)
                self.logger.debug(f'Cycle {cycle}: Resuming after wait')

        except KeyboardInterrupt:
            self.logger.info('Bot stopped by user')

        except Exception as e:
            self.logger.error(f'Runtime error: {e}', exc_info=True)

        finally:
            self.logger.info('Bot shutdown complete')
