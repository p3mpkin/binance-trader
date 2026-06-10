# -*- coding: UTF-8 -*-
# Advanced Bollinger Bands Trading Strategy
# Combines BB with RSI, Volume Analysis, and Risk Management

import logging
from typing import Dict, List, Tuple, Optional
from Indicators import Indicators


class BollingerStrategy:
    """
    Advanced Bollinger Bands Trading Strategy with MACD Confirmation

    Strategy Rules:
    - BUY: Price touches lower band + RSI < 30 + High volume + MACD bullish cross/momentum
    - SELL: Price touches upper band + RSI > 70 + MACD bearish cross/momentum
    - Alternative: Reach middle band (take profit)
    - Uses dynamic stop-loss based on ATR
    
    MACD Integration:
    - Bullish signals confirmed when MACD shows bullish momentum
    - Bearish signals confirmed when MACD shows bearish momentum
    - Increases confidence score when MACD crosses signal line
    """

    def __init__(self, config: Dict = None):
        """
        Initialize Bollinger Bands Strategy with MACD

        Args:
            config: Strategy configuration parameters
        """
        self.config = config or {}
        self.strategy_mode = self.config.get('strategy_mode', 'mean_reversion')

        # Bollinger Bands parameters
        self.bb_period = self.config.get('bb_period', 20)
        self.bb_std_dev = self.config.get('bb_std_dev', 2.0)

        # RSI parameters
        self.rsi_period = self.config.get('rsi_period', 14)
        self.rsi_oversold = self.config.get('rsi_oversold', 30)
        self.rsi_overbought = self.config.get('rsi_overbought', 70)

        # Volume parameters
        self.volume_period = self.config.get('volume_period', 20)
        self.volume_threshold = self.config.get('volume_threshold', 1.2)

        # Risk management
        self.stop_loss_atr_multiplier = self.config.get('stop_loss_atr', 2.0)
        self.take_profit_target = self.config.get('take_profit', 'middle')  # 'middle', 'upper', or percentage
        self.take_profit_strategy = self.config.get('take_profit_strategy', 'legacy')
        self.take_profit_value = self.config.get('take_profit_value', 2.0)
        self.take_profit_band = self.config.get('take_profit_band', 'middle')

        # Additional filters
        self.min_bb_width = self.config.get('min_bb_width', 1.0)  # Minimum volatility
        self.max_bb_width = self.config.get('max_bb_width', 10.0)  # Maximum volatility

        # MACD parameters
        self.macd_fast = self.config.get('macd_fast', 12)
        self.macd_slow = self.config.get('macd_slow', 26)
        self.macd_signal = self.config.get('macd_signal', 9)
        self.use_macd = self.config.get('use_macd', True)  # Enable/disable MACD confirmation

        # Scalping parameters
        self.scalping_ema_fast = self.config.get('scalping_ema_fast', 9)
        self.scalping_ema_slow = self.config.get('scalping_ema_slow', 21)
        self.scalping_take_profit_pct = self.config.get('scalping_take_profit_pct', 0.4)
        self.scalping_stop_loss_pct = self.config.get('scalping_stop_loss_pct', 0.25)
        self.scalping_pullback_pct = self.config.get('scalping_pullback_pct', 0.15)

        self.logger = logging.getLogger('BollingerStrategy')

    def _calculate_take_profit(
        self,
        side: str,
        price: float,
        stop_loss: float,
        middle: float,
        upper: float,
        lower: float,
        atr: float
    ) -> float:
        """Calculate take profit using the configured strategy."""
        strategy = self.take_profit_strategy

        if strategy == 'legacy':
            if self.take_profit_target == 'middle':
                return middle
            if self.take_profit_target == 'upper':
                return upper if side == 'LONG' else lower
            if self.take_profit_target == 'trailing':
                return 0.0

            value = float(self.take_profit_target)
            return price * (1 + value / 100) if side == 'LONG' else price * (1 - value / 100)

        if strategy == 'band':
            return middle if self.take_profit_band == 'middle' else (upper if side == 'LONG' else lower)

        if strategy == 'percent':
            value = float(self.take_profit_value)
            return price * (1 + value / 100) if side == 'LONG' else price * (1 - value / 100)

        if strategy == 'atr':
            value = float(self.take_profit_value)
            return price + (atr * value) if side == 'LONG' else price - (atr * value)

        if strategy == 'risk_reward':
            value = float(self.take_profit_value)
            risk = abs(price - stop_loss)
            return price + (risk * value) if side == 'LONG' else price - (risk * value)

        if strategy == 'trailing':
            return 0.0

        return middle

    def analyze(self, klines: List[List], current_price: float, current_volume: float = 0) -> Dict:
        """
        Analyze market conditions using Bollinger Bands + RSI + Volume + MACD strategy

        Args:
            klines: List of kline data [timestamp, open, high, low, close, volume, ...]
            current_price: Current market price
            current_volume: Current trading volume

        Returns:
            Dictionary containing analysis results and trading signals
        """
        if not klines or len(klines) < self.bb_period:
            return {
                'price': current_price,
                'indicators': {},
                'signal': 'WAIT',
                'confidence': 0.0,
                'reason': 'Insufficient data for analysis',
                'entry_price': 0.0,
                'stop_loss': 0.0,
                'take_profit': 0.0
            }

        # Extract price and volume data
        closes = [float(k[4]) for k in klines]  # Close prices
        highs = [float(k[2]) for k in klines]   # High prices
        lows = [float(k[3]) for k in klines]    # Low prices
        volumes = [float(k[5]) for k in klines] # Volumes

        # Calculate indicators
        upper_band, middle_band, lower_band = Indicators.bollinger_bands(
            closes, self.bb_period, self.bb_std_dev
        )

        if upper_band is None:
            return {
                'price': current_price,
                'indicators': {},
                'signal': 'WAIT',
                'confidence': 0.0,
                'reason': 'Unable to calculate Bollinger Bands',
                'entry_price': 0.0,
                'stop_loss': 0.0,
                'take_profit': 0.0
            }

        rsi = Indicators.rsi(closes, self.rsi_period)
        bb_width = Indicators.bb_width(upper_band, lower_band, middle_band)
        bb_percent = Indicators.bb_percent(current_price, upper_band, lower_band)
        volume_data = Indicators.volume_analysis(volumes, self.volume_period)
        atr = Indicators.atr(highs, lows, closes, 14)
        ema_fast = Indicators.ema(closes, self.scalping_ema_fast)
        ema_slow = Indicators.ema(closes, self.scalping_ema_slow)
        previous_close = closes[-2] if len(closes) >= 2 else closes[-1]
        
        # Calculate MACD indicators
        macd_line, signal_line, histogram = Indicators.macd(closes, self.macd_fast, self.macd_slow, self.macd_signal)
        macd_signal_cross = Indicators.macd_signal_cross(closes, self.macd_fast, self.macd_slow, self.macd_signal) if self.use_macd else 'none'

        # Build analysis result
        analysis = {
            'price': current_price,
            'indicators': {
                'bb_upper': upper_band,
                'bb_middle': middle_band,
                'bb_lower': lower_band,
                'bb_width': bb_width,
                'bb_percent': bb_percent,
                'rsi': rsi,
                'volume_ratio': volume_data['volume_ratio'],
                'atr': atr,
                'ema_fast': ema_fast,
                'ema_slow': ema_slow,
                'previous_close': previous_close,
                'macd_line': macd_line,
                'macd_signal': signal_line,
                'macd_histogram': histogram,
                'macd_signal_cross': macd_signal_cross
            },
            'signal': 'WAIT',
            'confidence': 0.0,
            'reason': '',
            'entry_price': 0.0,
            'stop_loss': 0.0,
            'take_profit': 0.0
        }

        # Check volatility conditions
        if bb_width < self.min_bb_width:
            analysis['reason'] = f'Low volatility (BB Width: {bb_width:.2f}%)'
            return analysis

        if bb_width > self.max_bb_width:
            analysis['reason'] = f'Excessive volatility (BB Width: {bb_width:.2f}%)'
            return analysis

        # Determine trading signal
        signal_result = self._generate_signal(
            current_price, upper_band, middle_band, lower_band,
            rsi, volume_data, bb_percent, atr, macd_line, signal_line, histogram, macd_signal_cross,
            ema_fast, ema_slow, previous_close
        )

        analysis.update(signal_result)
        return analysis

    def _generate_signal(
        self,
        price: float,
        upper: float,
        middle: float,
        lower: float,
        rsi: float,
        volume_data: Dict,
        bb_percent: float,
        atr: float,
        macd_line: float,
        macd_signal: float,
        macd_histogram: float,
        macd_signal_cross: str,
        ema_fast: float,
        ema_slow: float,
        previous_close: float
    ) -> Dict:
        """
        Generate trading signal based on strategy rules + MACD confirmation

        MACD Integration:
        - BUY: Confirmation when MACD shows bullish_cross or bullish_momentum
        - SELL: Confirmation when MACD shows bearish_cross or bearish_momentum
        - Bollinger: Primary signal from price position and bands
        - RSI: Secondary confirmation for momentum
        - Volume: Tertiary confirmation for strength

        Returns:
            Dictionary with signal, confidence, and trade parameters
        """
        if self.strategy_mode == 'breakout':
            return self._generate_breakout_signal(
                price, upper, middle, lower, rsi, volume_data, bb_percent,
                atr, macd_histogram, macd_signal_cross
            )

        if self.strategy_mode == 'scalping':
            return self._generate_scalping_signal(
                price, rsi, volume_data, atr, macd_histogram, macd_signal_cross,
                ema_fast, ema_slow, previous_close
            )

        return self._generate_mean_reversion_signal(
            price, upper, middle, lower, rsi, volume_data, bb_percent,
            atr, macd_histogram, macd_signal_cross
        )

    def _generate_scalping_signal(
        self,
        price: float,
        rsi: float,
        volume_data: Dict,
        atr: float,
        macd_histogram: float,
        macd_signal_cross: str,
        ema_fast: float,
        ema_slow: float,
        previous_close: float
    ) -> Dict:
        """Generate short-term scalping signals using EMA trend and momentum confirmation."""
        confidence = 0.0
        reasons = []
        pullback = self.scalping_pullback_pct / 100

        trend_up = ema_fast > ema_slow
        trend_down = ema_fast < ema_slow

        if trend_up:
            confidence += 25
            reasons.append(f'EMA trend up ({self.scalping_ema_fast}>{self.scalping_ema_slow})')

            near_fast_ema = price <= ema_fast * (1 + pullback)
            reclaimed_fast_ema = previous_close <= ema_fast and price > ema_fast
            if near_fast_ema or reclaimed_fast_ema:
                confidence += 25
                reasons.append('Pullback/reclaim near fast EMA')

            if 45 <= rsi <= 75:
                confidence += 15
                reasons.append(f'RSI scalping-friendly ({rsi:.1f})')
            elif rsi > 80:
                confidence -= 15
                reasons.append(f'RSI overheated ({rsi:.1f})')

            if volume_data['volume_ratio'] > self.volume_threshold:
                confidence += 20
                reasons.append(f'High volume ({volume_data["volume_ratio"]:.2f}x)')
            elif volume_data['volume_ratio'] > 1.0:
                confidence += 10
                reasons.append(f'Above avg volume ({volume_data["volume_ratio"]:.2f}x)')

            if self.use_macd:
                if macd_signal_cross in ['bullish_cross', 'bullish_momentum'] or macd_histogram > 0:
                    confidence += 15
                    reasons.append('MACD short-term bullish')
                elif macd_histogram < 0:
                    confidence -= 10
                    reasons.append('MACD bearish warning')

            if confidence >= 60:
                stop_loss = price * (1 - self.scalping_stop_loss_pct / 100)
                take_profit = price * (1 + self.scalping_take_profit_pct / 100)
                return {
                    'signal': 'BUY',
                    'confidence': min(confidence, 100),
                    'reason': ' | '.join(reasons),
                    'entry_price': price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'risk_reward': (take_profit - price) / (price - stop_loss) if price > stop_loss else 0
                }

        elif trend_down:
            confidence += 25
            reasons.append(f'EMA trend down ({self.scalping_ema_fast}<{self.scalping_ema_slow})')

            near_fast_ema = price >= ema_fast * (1 - pullback)
            rejected_fast_ema = previous_close >= ema_fast and price < ema_fast
            if near_fast_ema or rejected_fast_ema:
                confidence += 25
                reasons.append('Pullback/rejection near fast EMA')

            if 25 <= rsi <= 55:
                confidence += 15
                reasons.append(f'RSI scalping-friendly ({rsi:.1f})')
            elif rsi < 20:
                confidence -= 15
                reasons.append(f'RSI oversold ({rsi:.1f})')

            if volume_data['volume_ratio'] > self.volume_threshold:
                confidence += 20
                reasons.append(f'High volume ({volume_data["volume_ratio"]:.2f}x)')
            elif volume_data['volume_ratio'] > 1.0:
                confidence += 10
                reasons.append(f'Above avg volume ({volume_data["volume_ratio"]:.2f}x)')

            if self.use_macd:
                if macd_signal_cross in ['bearish_cross', 'bearish_momentum'] or macd_histogram < 0:
                    confidence += 15
                    reasons.append('MACD short-term bearish')
                elif macd_histogram > 0:
                    confidence -= 10
                    reasons.append('MACD bullish warning')

            if confidence >= 60:
                stop_loss = price * (1 + self.scalping_stop_loss_pct / 100)
                take_profit = price * (1 - self.scalping_take_profit_pct / 100)
                return {
                    'signal': 'SELL',
                    'confidence': min(confidence, 100),
                    'reason': ' | '.join(reasons),
                    'entry_price': price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'risk_reward': (price - take_profit) / (stop_loss - price) if stop_loss > price else 0
                }

        return {
            'signal': 'WAIT',
            'confidence': confidence,
            'reason': 'No scalping setup | ' + ' | '.join(reasons) if reasons else 'Waiting for EMA scalping setup',
            'entry_price': 0.0,
            'stop_loss': 0.0,
            'take_profit': 0.0
        }

    def _generate_mean_reversion_signal(
        self,
        price: float,
        upper: float,
        middle: float,
        lower: float,
        rsi: float,
        volume_data: Dict,
        bb_percent: float,
        atr: float,
        macd_histogram: float,
        macd_signal_cross: str
    ) -> Dict:
        """Generate mean-reversion signals around Bollinger Bands."""
        confidence = 0.0
        reasons = []

        # === BUY SIGNAL CONDITIONS ===
        if price <= lower * 1.005:  # Price at or below lower band (0.5% tolerance)
            confidence += 30
            reasons.append('Price at lower BB')

            # RSI confirmation
            if rsi < self.rsi_oversold:
                confidence += 25
                reasons.append(f'RSI oversold ({rsi:.1f})')
            elif rsi < 40:
                confidence += 15
                reasons.append(f'RSI favorable ({rsi:.1f})')

            # Volume confirmation
            if volume_data['volume_ratio'] > self.volume_threshold:
                confidence += 20
                reasons.append(f'High volume ({volume_data["volume_ratio"]:.2f}x)')
            elif volume_data['volume_ratio'] > 1.0:
                confidence += 10
                reasons.append(f'Above avg volume ({volume_data["volume_ratio"]:.2f}x)')

            # BB position
            if bb_percent < 0.1:
                confidence += 15
                reasons.append('Price well below lower band')

            # MACD confirmation - bullish momentum or cross
            if self.use_macd:
                if macd_signal_cross == 'bullish_cross':
                    confidence += 25
                    reasons.append('MACD bullish cross ↑')
                elif macd_signal_cross == 'bullish_momentum':
                    confidence += 15
                    reasons.append('MACD bullish momentum')
                elif macd_histogram < 0:
                    confidence -= 10  # Bearish divergence
                    reasons.append('MACD bearish (divergence warning)')

            if confidence >= 50:
                # Calculate trade parameters
                stop_loss = price - (atr * self.stop_loss_atr_multiplier)

                take_profit = self._calculate_take_profit(
                    'LONG', price, stop_loss, middle, upper, lower, atr
                )

                return {
                    'signal': 'BUY',
                    'confidence': min(confidence, 100),
                    'reason': ' | '.join(reasons),
                    'entry_price': price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'risk_reward': (take_profit - price) / (price - stop_loss) if price > stop_loss else 0
                }

        # === SELL SIGNAL CONDITIONS ===
        elif price >= upper * 0.995:  # Price at or above upper band (0.5% tolerance)
            confidence += 30
            reasons.append('Price at upper BB')

            # RSI confirmation
            if rsi > self.rsi_overbought:
                confidence += 25
                reasons.append(f'RSI overbought ({rsi:.1f})')
            elif rsi > 60:
                confidence += 15
                reasons.append(f'RSI favorable ({rsi:.1f})')

            # Volume confirmation
            if volume_data['volume_ratio'] > self.volume_threshold:
                confidence += 20
                reasons.append(f'High volume ({volume_data["volume_ratio"]:.2f}x)')

            # BB position
            if bb_percent > 0.9:
                confidence += 15
                reasons.append('Price well above upper band')

            # MACD confirmation - bearish momentum or cross
            if self.use_macd:
                if macd_signal_cross == 'bearish_cross':
                    confidence += 25
                    reasons.append('MACD bearish cross ↓')
                elif macd_signal_cross == 'bearish_momentum':
                    confidence += 15
                    reasons.append('MACD bearish momentum')
                elif macd_histogram > 0:
                    confidence -= 10  # Bullish divergence
                    reasons.append('MACD bullish (divergence warning)')

            if confidence >= 50:
                return {
                    'signal': 'SELL',
                    'confidence': min(confidence, 100),
                    'reason': ' | '.join(reasons),
                    'entry_price': 0.0,
                    'stop_loss': 0.0,
                    'take_profit': 0.0
                }

        # === TAKE PROFIT at MIDDLE BAND (if holding) ===
        if middle * 0.99 <= price <= middle * 1.01:
            return {
                'signal': 'TAKE_PROFIT',
                'confidence': 70,
                'reason': 'Price reached middle band (take profit target)',
                'entry_price': 0.0,
                'stop_loss': 0.0,
                'take_profit': middle
            }

        # No clear signal
        return {
            'signal': 'WAIT',
            'confidence': confidence,
            'reason': 'No clear signal | ' + ' | '.join(reasons) if reasons else 'Waiting for setup',
            'entry_price': 0.0,
            'stop_loss': 0.0,
            'take_profit': 0.0
        }

    def _generate_breakout_signal(
        self,
        price: float,
        upper: float,
        middle: float,
        lower: float,
        rsi: float,
        volume_data: Dict,
        bb_percent: float,
        atr: float,
        macd_histogram: float,
        macd_signal_cross: str
    ) -> Dict:
        """Generate trend-following breakout signals."""
        confidence = 0.0
        reasons = []

        # === LONG BREAKOUT ===
        if price > upper:
            confidence += 35
            reasons.append('Price broke upper BB')

            if volume_data['volume_ratio'] > self.volume_threshold:
                confidence += 25
                reasons.append(f'High volume ({volume_data["volume_ratio"]:.2f}x)')
            elif volume_data['volume_ratio'] > 1.0:
                confidence += 10
                reasons.append(f'Above avg volume ({volume_data["volume_ratio"]:.2f}x)')

            if 50 <= rsi <= self.rsi_overbought + 10:
                confidence += 15
                reasons.append(f'RSI trend-friendly ({rsi:.1f})')
            elif rsi > self.rsi_overbought + 10:
                confidence -= 10
                reasons.append(f'RSI overheated ({rsi:.1f})')

            if bb_percent > 1.0:
                confidence += 10
                reasons.append('Price outside upper band')

            if self.use_macd:
                if macd_signal_cross == 'bullish_cross':
                    confidence += 20
                    reasons.append('MACD bullish cross')
                elif macd_signal_cross == 'bullish_momentum':
                    confidence += 12
                    reasons.append('MACD bullish momentum')
                elif macd_histogram < 0:
                    confidence -= 10
                    reasons.append('MACD bearish warning')

            if confidence >= 50:
                stop_loss = price - (atr * self.stop_loss_atr_multiplier)

                take_profit = self._calculate_take_profit(
                    'LONG', price, stop_loss, middle, upper, lower, atr
                )

                return {
                    'signal': 'BUY',
                    'confidence': min(confidence, 100),
                    'reason': ' | '.join(reasons),
                    'entry_price': price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'risk_reward': (take_profit - price) / (price - stop_loss) if price > stop_loss else 0
                }

        # === SHORT BREAKDOWN ===
        elif price < lower:
            confidence += 35
            reasons.append('Price broke lower BB')

            if volume_data['volume_ratio'] > self.volume_threshold:
                confidence += 25
                reasons.append(f'High volume ({volume_data["volume_ratio"]:.2f}x)')
            elif volume_data['volume_ratio'] > 1.0:
                confidence += 10
                reasons.append(f'Above avg volume ({volume_data["volume_ratio"]:.2f}x)')

            if self.rsi_oversold - 10 <= rsi <= 50:
                confidence += 15
                reasons.append(f'RSI trend-friendly ({rsi:.1f})')
            elif rsi < self.rsi_oversold - 10:
                confidence -= 10
                reasons.append(f'RSI oversold warning ({rsi:.1f})')

            if bb_percent < 0:
                confidence += 10
                reasons.append('Price outside lower band')

            if self.use_macd:
                if macd_signal_cross == 'bearish_cross':
                    confidence += 20
                    reasons.append('MACD bearish cross')
                elif macd_signal_cross == 'bearish_momentum':
                    confidence += 12
                    reasons.append('MACD bearish momentum')
                elif macd_histogram > 0:
                    confidence -= 10
                    reasons.append('MACD bullish warning')

            if confidence >= 50:
                stop_loss = price + (atr * self.stop_loss_atr_multiplier)

                take_profit = self._calculate_take_profit(
                    'SHORT', price, stop_loss, middle, upper, lower, atr
                )

                return {
                    'signal': 'SELL',
                    'confidence': min(confidence, 100),
                    'reason': ' | '.join(reasons),
                    'entry_price': price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'risk_reward': (price - take_profit) / (stop_loss - price) if stop_loss > price else 0
                }

        # Trend exit hint: price returns to middle band area.
        if middle * 0.99 <= price <= middle * 1.01:
            return {
                'signal': 'TAKE_PROFIT',
                'confidence': 60,
                'reason': 'Price returned to middle band after trend move',
                'entry_price': 0.0,
                'stop_loss': 0.0,
                'take_profit': middle
            }

        return {
            'signal': 'WAIT',
            'confidence': confidence,
            'reason': 'No breakout signal | ' + ' | '.join(reasons) if reasons else 'Waiting for breakout',
            'entry_price': 0.0,
            'stop_loss': 0.0,
            'take_profit': 0.0
        }

    def should_buy(self, analysis: Dict) -> bool:
        """
        Determine if should execute buy order

        Args:
            analysis: Analysis result from analyze()

        Returns:
            True if should buy
        """
        return analysis['signal'] == 'BUY' and analysis['confidence'] >= 50

    def should_sell(self, analysis: Dict, position_price: float = 0) -> bool:
        """
        Determine if should execute sell order

        Args:
            analysis: Analysis result from analyze()
            position_price: Price at which position was entered (for profit calculation)

        Returns:
            True if should sell
        """
        if analysis['signal'] in ['SELL', 'TAKE_PROFIT']:
            return analysis['confidence'] >= 50

        # Check stop loss
        if position_price > 0 and analysis['stop_loss'] > 0:
            if analysis['price'] <= analysis['stop_loss']:
                return True

        return False

    def calculate_position_size(
        self,
        balance: float,
        price: float,
        risk_percentage: float = 2.0,
        stop_loss: float = 0
    ) -> float:
        """
        Calculate position size based on risk management

        Args:
            balance: Available balance
            price: Entry price
            risk_percentage: Percentage of balance to risk (default: 2%)
            stop_loss: Stop loss price

        Returns:
            Position size (quantity to buy)
        """
        if stop_loss == 0 or price <= stop_loss:
            # Default position size (no stop loss provided)
            return (balance * (risk_percentage / 100)) / price

        # Risk-based position sizing
        risk_amount = balance * (risk_percentage / 100)
        price_risk = price - stop_loss
        position_size = risk_amount / price_risk

        # Don't use more than available balance
        max_quantity = balance / price
        return min(position_size, max_quantity)
