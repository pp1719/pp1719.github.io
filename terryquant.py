# main.py - FastAPI Backend for Quant Engine Pro
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import asyncio
import json
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from enum import Enum
import aiohttp
import pandas as pd
import talib
from collections import deque
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== ENUMS & DATA CLASSES ====================

class SignalType(Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"

class MarketRegime(Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    BREAKOUT = "breakout"
    REVERSAL = "reversal"

class Session(Enum):
    ASIAN = "asian"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP = "overlap"
    CLOSED = "closed"

@dataclass
class OHLCV:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class TechnicalIndicators:
    ema_20: float
    ema_50: float
    rsi: float
    macd: float
    macd_signal: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    atr: float
    adx: float
    volume_sma: float
    vwap: float

@dataclass
class Signal:
    type: str
    score: int  # -100 to 100
    confidence: int  # 0 to 100
    label: str
    timestamp: datetime

@dataclass
class Factor:
    name: str
    impact: int  # -50 to 50
    description: str
    direction: str  # "bullish" or "bearish"

@dataclass
class RiskProfile:
    volatility_state: str  # "low", "normal", "high", "extreme"
    atr_percent: float
    recommended_position_size: float  # 0.0 to 1.0
    stop_loss_distance: float  # in price terms

@dataclass
class EntryPoint:
    price: float
    type: str  # "primary", "secondary", "aggressive"
    reason: str  # เหตุผลเทคนิคal
    risk_reward_ratio: float
    strength: int  # 0-100 ความแข็งแกร่งของจุดเข้า
    order_type: str  # "BUY" or "SELL"
    win_rate: int  # 0-100 อัตราสำเร็จของจุดเข้านี้
    tp_price: float  # Take Profit price
    sl_price: float  # Stop Loss price

@dataclass
class MarketData:
    symbol: str
    price: float
    change_24h: float
    change_percent_24h: float
    high_24h: float
    low_24h: float
    volume_24h: float

@dataclass
class QuantOutput:
    symbol: str
    market_data: MarketData
    signal: Signal
    factors: List[Factor]
    risk: RiskProfile
    entry_points: List[EntryPoint]
    regime: str
    active_session: str
    next_event: Optional[str]
    recommendation: str
    timestamp: datetime

# ==================== CORE ENGINE ====================

class DataFeed:
    """Real-time data feed from Binance/Bybit"""
    
    def __init__(self):
        self.base_urls = {
            "binance": "https://api.binance.com/api/v3",
            "bybit": "https://api.bybit.com/v5"
        }
        self.symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        self.ohlcv_history: Dict[str, deque] = {
            sym: deque(maxlen=500) for sym in self.symbols
        }
        self.latest_prices: Dict[str, float] = {}
        self.session = None
    
    async def start(self):
        self.session = aiohttp.ClientSession()
        # Initialize with historical data
        await self._load_historical_data()
        logger.info("DataFeed started and historical data loaded")
    
    async def stop(self):
        if self.session:
            await self.session.close()
    
    async def _load_historical_data(self):
        """Load initial historical data for all symbols"""
        logger.info("Loading historical data...")
        tasks = [
            self._fetch_binance_klines(sym, "1h", 500)
            for sym in self.symbols
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error loading {self.symbols[i]}: {result}")
            else:
                logger.info(f"Successfully loaded {self.symbols[i]}")
        logger.info("Historical data loading complete")
    
    async def _fetch_binance_klines(self, symbol: str, interval: str, limit: int = 100):
        """Fetch candlestick data from Binance"""
        try:
            url = f"{self.base_urls['binance']}/klines"
            params = {"symbol": symbol, "interval": interval, "limit": limit}
            
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Clear old data first to avoid stale caches
                    self.ohlcv_history[symbol].clear()
                    for candle in data:
                        ohlcv = OHLCV(
                            timestamp=datetime.fromtimestamp(candle[0] / 1000),
                            open=float(candle[1]),
                            high=float(candle[2]),
                            low=float(candle[3]),
                            close=float(candle[4]),
                            volume=float(candle[5])
                        )
                        self.ohlcv_history[symbol].append(ohlcv)
                    logger.info(f"Loaded {len(data)} candles for {symbol}")
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
    
    async def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get real-time price"""
        try:
            url = f"{self.base_urls['binance']}/ticker/24hr"
            params = {"symbol": symbol}
            
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data['lastPrice'])
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return None
    
    def get_ohlcv_array(self, symbol: str) -> pd.DataFrame:
        """Convert deque to pandas DataFrame for TA-Lib"""
        if not self.ohlcv_history[symbol]:
            return pd.DataFrame()
        
        data = list(self.ohlcv_history[symbol])
        return pd.DataFrame([
            {
                'open': d.open,
                'high': d.high,
                'low': d.low,
                'close': d.close,
                'volume': d.volume,
                'timestamp': d.timestamp
            }
            for d in data
        ])

class TechnicalAnalyzer:
    """Calculate technical indicators using TA-Lib"""
    
    def calculate(self, df: pd.DataFrame) -> Optional[TechnicalIndicators]:
        if len(df) < 50:
            return None
        
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values
        
        # Trend Indicators
        ema_20 = talib.EMA(close, timeperiod=20)[-1]
        ema_50 = talib.EMA(close, timeperiod=50)[-1]
        ema_100 = talib.EMA(close, timeperiod=100)[-1] if len(close) >= 100 else ema_50
        ema_200 = talib.EMA(close, timeperiod=200)[-1] if len(close) >= 200 else ema_50
        
        # Momentum
        rsi = talib.RSI(close, timeperiod=14)[-1]
        rsi_7 = talib.RSI(close, timeperiod=7)[-1]
        rsi_21 = talib.RSI(close, timeperiod=21)[-1]
        macd, macd_signal, macd_hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
        
        # Volatility
        bb_upper, bb_middle, bb_lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
        atr = talib.ATR(high, low, close, timeperiod=14)[-1]
        adx = talib.ADX(high, low, close, timeperiod=14)[-1]
        
        # Additional trend strength metrics
        plus_di = talib.PLUS_DI(high, low, close, timeperiod=14)[-1] if len(close) >= 14 else 0
        minus_di = talib.MINUS_DI(high, low, close, timeperiod=14)[-1] if len(close) >= 14 else 0
        
        # Volume
        volume_sma = talib.SMA(volume, timeperiod=20)[-1]
        obv = talib.OBV(close, volume)[-1] if len(close) > 1 else 0
        
        # VWAP calculation
        typical_price = (high + low + close) / 3
        vwap = np.sum(typical_price * volume) / np.sum(volume) if np.sum(volume) > 0 else close[-1]
        
        # Store as dict for easier access to all indicators
        self.last_indicators = {
            'ema_20': ema_20, 'ema_50': ema_50, 'ema_100': ema_100, 'ema_200': ema_200,
            'rsi': rsi, 'rsi_7': rsi_7, 'rsi_21': rsi_21,
            'macd': macd[-1], 'macd_signal': macd_signal[-1], 'macd_hist': macd_hist[-1],
            'bb_upper': bb_upper[-1], 'bb_middle': bb_middle[-1], 'bb_lower': bb_lower[-1],
            'atr': atr, 'adx': adx, 'plus_di': plus_di, 'minus_di': minus_di,
            'volume_sma': volume_sma, 'obv': obv, 'vwap': vwap,
            'close': close[-1], 'high': high[-1], 'low': low[-1]
        }
        
        return TechnicalIndicators(
            ema_20=ema_20,
            ema_50=ema_50,
            rsi=rsi,
            macd=macd[-1],
            macd_signal=macd_signal[-1],
            bb_upper=bb_upper[-1],
            bb_middle=bb_middle[-1],
            bb_lower=bb_lower[-1],
            atr=atr,
            adx=adx,
            volume_sma=volume_sma,
            vwap=vwap
        )

class SignalEngine:
    """Generate trading signals using weighted multi-factor model with enhanced analysis"""
    
    def __init__(self):
        self.weights = {
            'trend': 0.30,
            'momentum': 0.25,
            'volatility': 0.15,
            'volume': 0.15,
            'structure': 0.15
        }
    
    def analyze(self, df: pd.DataFrame, indicators: TechnicalIndicators) -> tuple:
        """Return signal, factors, and regime with enhanced scoring"""
        close = df['close'].iloc[-1]
        prev_close = df['close'].iloc[-2]
        
        factors = []
        scores = {}
        
        # 1. ENHANCED TREND ANALYSIS (Multi-level EMA + ADX + Directional Movement)
        trend_score = 0
        trend_desc = ""
        
        # Strong trend signals
        if indicators.ema_20 > indicators.ema_50 > indicators.ema_50:
            trend_score = 40
            trend_desc = "Strong uptrend: EMA20 > EMA50"
            if indicators.adx > 30:
                trend_score += 20
                trend_desc += ", ADX confirms strength"
        elif indicators.ema_20 < indicators.ema_50:
            trend_score = -40
            trend_desc = "Strong downtrend: EMA20 < EMA50"
            if indicators.adx > 30:
                trend_score -= 20
                trend_desc += ", ADX confirms strength"
        elif indicators.adx > 25:
            trend_score = 20 if close > indicators.ema_50 else -20
            trend_desc = "Moderate trend with ADX confirmation"
        else:
            trend_score = 10 if close > indicators.ema_50 else -10
            trend_desc = "Weak trend signal"
        
        scores['trend'] = trend_score
        factors.append(Factor(
            name="Trend Strength",
            impact=trend_score,
            description=trend_desc + f" (ADX: {indicators.adx:.1f})",
            direction="bullish" if trend_score > 0 else "bearish"
        ))
        
        # 2. ENHANCED MOMENTUM (RSI Multi-timeframe + MACD + Extremes)
        momentum_score = 0
        momentum_desc = ""
        
        # RSI strength indicators
        if indicators.rsi > 70:
            momentum_score -= 20
            momentum_desc = "RSI overbought (>70)"
        elif indicators.rsi > 60:
            momentum_score += 15
            momentum_desc = "RSI bullish momentum (60-70)"
        elif indicators.rsi > 50:
            momentum_score += 25
            momentum_desc = "RSI strong bullish (50-60)"
        elif indicators.rsi > 40:
            momentum_score -= 15
            momentum_desc = "RSI weak bearish (40-50)"
        elif indicators.rsi < 30:
            momentum_score += 20
            momentum_desc = "RSI oversold (<30)"
        else:
            momentum_score -= 25
            momentum_desc = "RSI strong bearish (<40)"
        
        # MACD confirmation
        if indicators.macd > indicators.macd_signal:
            momentum_score += 20
            momentum_desc += ", MACD bullish"
        else:
            momentum_score -= 20
            momentum_desc += ", MACD bearish"
        
        scores['momentum'] = momentum_score
        factors.append(Factor(
            name="Momentum",
            impact=momentum_score,
            description=momentum_desc + f" (RSI: {indicators.rsi:.1f})",
            direction="bullish" if momentum_score > 0 else "bearish"
        ))
        
        # 3. ENHANCED VOLATILITY (BB Position + ATR Expansion)
        bb_range = indicators.bb_upper - indicators.bb_lower
        bb_position = (close - indicators.bb_lower) / bb_range if bb_range > 0 else 0.5
        atr_pct = (indicators.atr / close) * 100 if close > 0 else 0
        
        volatility_score = 0
        volatility_desc = ""
        
        if bb_position > 0.85:
            volatility_score = -25
            volatility_desc = "Price at upper BB, exhaustion likely"
        elif bb_position > 0.7:
            volatility_score = -10
            volatility_desc = "Price in upper BB zone"
        elif bb_position < 0.15:
            volatility_score = 25
            volatility_desc = "Price at lower BB, bounce potential"
        elif bb_position < 0.3:
            volatility_score = 10
            volatility_desc = "Price in lower BB zone"
        else:
            volatility_score = 5
            volatility_desc = "Price in BB midzone"
        
        scores['volatility'] = volatility_score
        factors.append(Factor(
            name="Volatility Position",
            impact=volatility_score,
            description=volatility_desc + f" ({bb_position*100:.0f}%), ATR: {atr_pct:.2f}%",
            direction="bullish" if volatility_score > 0 else "bearish"
        ))
        
        # 4. ENHANCED VOLUME ANALYSIS
        current_volume = df['volume'].iloc[-1]
        volume_ratio = current_volume / indicators.volume_sma if indicators.volume_sma > 0 else 1
        price_direction_strength = abs(close - prev_close) / indicators.atr if indicators.atr > 0 else 0
        
        volume_score = 0
        volume_desc = ""
        
        if volume_ratio > 1.8:
            volume_score = 30 if close > prev_close else -30
            volume_desc = f"Explosive volume {volume_ratio:.2f}x"
        elif volume_ratio > 1.5:
            volume_score = 20 if close > prev_close else -20
            volume_desc = f"Strong volume {volume_ratio:.2f}x"
        elif volume_ratio > 1.1:
            volume_score = 10 if close > prev_close else -10
            volume_desc = f"Above average volume {volume_ratio:.2f}x"
        else:
            volume_score = -5
            volume_desc = f"Low volume {volume_ratio:.2f}x"
        
        scores['volume'] = volume_score
        factors.append(Factor(
            name="Volume Confirmation",
            impact=volume_score,
            description=volume_desc + (", strong move confirmation" if price_direction_strength > 1 else ""),
            direction="bullish" if volume_score > 0 else "bearish"
        ))
        
        # 5. ENHANCED MARKET STRUCTURE (VWAP + Support/Resistance)
        structure_score = 0
        structure_desc = ""
        
        price_to_vwap = ((close - indicators.vwap) / indicators.vwap) * 100 if indicators.vwap > 0 else 0
        
        if close > indicators.vwap and close > indicators.bb_middle:
            structure_score = 30
            structure_desc = f"Above VWAP and BB middle, strong structure"
        elif close > indicators.vwap:
            structure_score = 15
            structure_desc = f"Above VWAP (+{price_to_vwap:.2f}%)"
        elif close < indicators.vwap and close < indicators.bb_middle:
            structure_score = -30
            structure_desc = f"Below VWAP and BB middle, weak structure"
        else:
            structure_score = -15
            structure_desc = f"Below VWAP ({price_to_vwap:.2f}%)"
        
        scores['structure'] = structure_score
        factors.append(Factor(
            name="Market Structure",
            impact=structure_score,
            description=structure_desc,
            direction="bullish" if structure_score > 0 else "bearish"
        ))
        
        # Calculate weighted final score
        final_score = sum(scores[k] * self.weights[k] for k in scores)
        final_score = max(-100, min(100, int(final_score)))
        
        # Determine signal type with enhanced logic
        if final_score > 65:
            signal_type = SignalType.STRONG_BUY
        elif final_score > 25:
            signal_type = SignalType.BUY
        elif final_score > -25:
            signal_type = SignalType.NEUTRAL
        elif final_score > -65:
            signal_type = SignalType.SELL
        else:
            signal_type = SignalType.STRONG_SELL
        
        # Calculate confidence based on factor agreement and indicator confluence
        bullish_factors = sum(1 for f in factors if f.impact > 0)
        bearish_factors = sum(1 for f in factors if f.impact < 0)
        agreement = max(bullish_factors, bearish_factors) / len(factors)
        
        # Extra confidence boost for strong signals with high agreement
        base_confidence = int(50 + (agreement * 50))
        if abs(final_score) > 60:  # Strong signals get confidence boost
            base_confidence = min(100, base_confidence + 15)
        
        confidence = base_confidence
        
        signal = Signal(
            type=signal_type.value,
            score=final_score,
            confidence=confidence,
            label=signal_type.name.replace("_", " "),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Determine regime
        regime = self._detect_regime(indicators, scores)
        
        return signal, factors, regime
    
    def _detect_regime(self, ind: TechnicalIndicators, scores: dict) -> str:
        """Detect market regime with enhanced logic"""
        # High ADX = Trending
        if ind.adx > 35:
            if scores['trend'] > 30:
                return MarketRegime.TRENDING_UP.value
            elif scores['trend'] < -30:
                return MarketRegime.TRENDING_DOWN.value
        elif ind.adx > 25:
            # Medium ADX = Breakout potential
            if abs(scores['trend']) > 20:
                return MarketRegime.BREAKOUT.value
        
        # Low ADX = Ranging
        if ind.adx < 20:
            return MarketRegime.RANGING.value
        
        # Extreme RSI = Reversal potential
        if abs(ind.rsi - 50) > 35:
            return MarketRegime.REVERSAL.value
        
        return MarketRegime.BREAKOUT.value

class RiskManager:
    """Risk management and position sizing"""
    
    def calculate_risk(self, df: pd.DataFrame, indicators: TechnicalIndicators, 
                      signal: Signal) -> RiskProfile:
        close = df['close'].iloc[-1]
        
        # ATR as percentage of price
        atr_percent = (indicators.atr / close) * 100
        
        # Volatility state
        if atr_percent < 1.0:
            vol_state = "low"
            position_size = 1.0
        elif atr_percent < 2.5:
            vol_state = "normal"
            position_size = 0.8
        elif atr_percent < 4.0:
            vol_state = "high"
            position_size = 0.5
        else:
            vol_state = "extreme"
            position_size = 0.25
        
        # Adjust for signal confidence
        position_size *= (signal.confidence / 100)
        
        # Kelly Criterion adjustment
        # Simplified: reduce size on low confidence
        if signal.confidence < 60:
            position_size *= 0.5
        
        stop_distance = indicators.atr * 2  # 2x ATR stop
        
        return RiskProfile(
            volatility_state=vol_state,
            atr_percent=atr_percent,
            recommended_position_size=round(position_size, 2),
            stop_loss_distance=round(stop_distance, 2)
        )

class EntryPointFinder:
    """Find best entry points with advanced pattern recognition and win rate calculation"""
    
    def find_entries(self, df: pd.DataFrame, indicators: TechnicalIndicators, 
                    signal: Signal, current_price: float) -> List[EntryPoint]:
        """Find optimal entry points with smart filtering"""
        entries = []
        close = df['close'].iloc[-1]
        
        if signal.type in [SignalType.STRONG_BUY.value, SignalType.BUY.value]:
            # FOR BUYING - look for support levels
            entries = self._find_buy_entries(close, current_price, indicators, df, signal)
        elif signal.type in [SignalType.STRONG_SELL.value, SignalType.SELL.value]:
            # FOR SELLING - look for resistance levels
            entries = self._find_sell_entries(close, current_price, indicators, df, signal)
        else:
            # NEUTRAL - show both potential buy and sell levels (reduced strength)
            buy_entries = self._find_buy_entries(close, current_price, indicators, df, signal)
            sell_entries = self._find_sell_entries(close, current_price, indicators, df, signal)
            for ep in buy_entries + sell_entries:
                ep.strength = max(30, int(ep.strength * 0.5))
            entries = (buy_entries + sell_entries)
        
        # Sort by win_rate and strength (best first)
        entries.sort(key=lambda x: (x.win_rate, x.strength), reverse=True)
        return entries[:3]  # Return top 3 entry points
    
    def _calculate_win_rate(self, entry_type: str, entry_price: float, tp_price: float, 
                           sl_price: float, indicators: TechnicalIndicators, 
                           df: pd.DataFrame, signal: Signal) -> int:
        """Calculate realistic win rate based on multiple factors"""
        base_rate = 50  # Base 50% win rate
        
        # Factor 1: Signal confidence (±15%)
        confidence_bonus = (signal.confidence - 50) * 0.15
        base_rate += confidence_bonus
        
        # Factor 2: RRR quality (Risk/Reward Ratio)
        if entry_type == "BUY":
            risk = entry_price - sl_price
            reward = tp_price - entry_price
        else:
            risk = sl_price - entry_price
            reward = entry_price - tp_price
        
        if risk > 0:
            rrr = reward / risk
            if rrr > 2.5:
                base_rate += 12
            elif rrr > 2.0:
                base_rate += 10
            elif rrr > 1.5:
                base_rate += 8
            elif rrr > 1.0:
                base_rate += 5
        
        # Factor 3: Market regime bonus
        # Trending markets are easier to profit from
        if indicators.adx > 30:
            base_rate += 8
        elif indicators.adx < 20:
            base_rate -= 5  # Ranging is harder
        
        # Factor 4: Volume confirmation
        if len(df) > 0:
            current_vol = df['volume'].iloc[-1]
            avg_vol = df['volume'].tail(20).mean()
            if current_vol > avg_vol * 1.5:
                base_rate += 8
        
        # Factor 5: Entry type quality
        # Primary entries are more reliable
        if entry_type == "primary":
            base_rate += 5
        elif entry_type == "aggressive":
            base_rate -= 3  # More risk, slightly lower rate
        
        # Factor 6: Pattern strength (RSI extremes are good reversal points)
        if indicators.rsi < 30 or indicators.rsi > 70:
            base_rate += 10
        elif indicators.rsi < 40 or indicators.rsi > 60:
            base_rate += 5
        
        # Clamp to 0-95 range (unrealistic to claim 100% win rate)
        return int(min(95, max(20, base_rate)))
    
    def _find_buy_entries(self, close: float, current_price: float, 
                         indicators: TechnicalIndicators, df: pd.DataFrame, 
                         signal: Signal) -> List[EntryPoint]:
        """Find buy entry points with intelligent TP/SL and win rate"""
        entries = []
        atr = indicators.atr
        
        # ===== ENTRY 1: LOWER BOLLINGER BAND (Aggressive support bounce) =====
        entry_1_price = round(indicators.bb_lower, 2)
        
        # Conservative TP with risk management
        entry_1_tp = round(entry_1_price + (atr * 3), 2)
        entry_1_sl = round(entry_1_price - (atr * 1.2), 2)
        
        # Calculate gain/loss
        entry_1_gain = ((entry_1_tp - entry_1_price) / entry_1_price) * 100
        entry_1_risk = ((entry_1_price - entry_1_sl) / entry_1_price) * 100
        
        entry_1_rrr = entry_1_gain / entry_1_risk if entry_1_risk > 0 else 0
        entry_1_win_rate = self._calculate_win_rate(
            "aggressive", entry_1_price, entry_1_tp, entry_1_sl, 
            indicators, df, signal
        )
        
        # Boost strength if entry is near strong support
        entry_1_strength = 90 if signal.confidence > 75 else 80
        if abs(entry_1_price - indicators.vwap) < atr:
            entry_1_strength = min(98, entry_1_strength + 5)
        
        entry_1 = EntryPoint(
            price=entry_1_price,
            type="aggressive",
            reason=f"Lower BB support - Strong bounce setup (RRR {entry_1_rrr:.2f}:1)",
            risk_reward_ratio=round(entry_1_rrr, 2),
            strength=entry_1_strength,
            order_type="BUY",
            win_rate=entry_1_win_rate,
            tp_price=entry_1_tp,
            sl_price=entry_1_sl
        )
        entries.append(entry_1)
        
        # ===== ENTRY 2: EMA-20 (Dynamic support level) =====
        entry_2_price = round(indicators.ema_20, 2)
        entry_2_tp = round(entry_2_price + (atr * 2.8), 2)
        entry_2_sl = round(entry_2_price - (atr * 1.0), 2)
        
        entry_2_gain = ((entry_2_tp - entry_2_price) / entry_2_price) * 100
        entry_2_risk = ((entry_2_price - entry_2_sl) / entry_2_price) * 100
        entry_2_rrr = entry_2_gain / entry_2_risk if entry_2_risk > 0 else 0
        entry_2_win_rate = self._calculate_win_rate(
            "secondary", entry_2_price, entry_2_tp, entry_2_sl, 
            indicators, df, signal
        )
        
        entry_2_strength = 85 if signal.confidence > 75 else 70
        entry_2 = EntryPoint(
            price=entry_2_price,
            type="secondary",
            reason=f"EMA-20 dynamic support - Trend confirmation (RRR {entry_2_rrr:.2f}:1)",
            risk_reward_ratio=round(entry_2_rrr, 2),
            strength=entry_2_strength,
            order_type="BUY",
            win_rate=entry_2_win_rate,
            tp_price=entry_2_tp,
            sl_price=entry_2_sl
        )
        entries.append(entry_2)
        
        # ===== ENTRY 3: VWAP (Volume-weighted entry point) =====
        entry_3_price = round(indicators.vwap, 2)
        entry_3_tp = round(entry_3_price + (atr * 3.0), 2)
        entry_3_sl = round(entry_3_price - (atr * 1.1), 2)
        
        entry_3_gain = ((entry_3_tp - entry_3_price) / entry_3_price) * 100
        entry_3_risk = ((entry_3_price - entry_3_sl) / entry_3_price) * 100
        entry_3_rrr = entry_3_gain / entry_3_risk if entry_3_risk > 0 else 0
        entry_3_win_rate = self._calculate_win_rate(
            "primary", entry_3_price, entry_3_tp, entry_3_sl, 
            indicators, df, signal
        )
        
        entry_3_strength = 88 if signal.confidence > 70 else 75
        # If VWAP is aligned with price, boost strength
        if abs(entry_3_price - indicators.bb_middle) < atr * 0.5:
            entry_3_strength = min(98, entry_3_strength + 3)
        
        entry_3 = EntryPoint(
            price=entry_3_price,
            type="primary",
            reason=f"VWAP fair value - Volume weighted (RRR {entry_3_rrr:.2f}:1)",
            risk_reward_ratio=round(entry_3_rrr, 2),
            strength=entry_3_strength,
            order_type="BUY",
            win_rate=entry_3_win_rate,
            tp_price=entry_3_tp,
            sl_price=entry_3_sl
        )
        entries.append(entry_3)
        
        # ===== ENTRY 4: CONSERVATIVE DIP ENTRY =====
        entry_4_price = round(current_price - (atr * 0.6), 2)
        entry_4_tp = round(entry_4_price + (atr * 2.5), 2)
        entry_4_sl = round(entry_4_price - (atr * 0.8), 2)
        
        entry_4_gain = ((entry_4_tp - entry_4_price) / entry_4_price) * 100
        entry_4_risk = ((entry_4_price - entry_4_sl) / entry_4_price) * 100
        entry_4_rrr = entry_4_gain / entry_4_risk if entry_4_risk > 0 else 0
        entry_4_win_rate = self._calculate_win_rate(
            "primary", entry_4_price, entry_4_tp, entry_4_sl, 
            indicators, df, signal
        )
        
        entry_4_strength = 75 if signal.confidence > 65 else 60
        entry_4 = EntryPoint(
            price=entry_4_price,
            type="primary",
            reason=f"Current - 0.6 ATR (Conservative limit order, RRR {entry_4_rrr:.2f}:1)",
            risk_reward_ratio=round(entry_4_rrr, 2),
            strength=entry_4_strength,
            order_type="BUY",
            win_rate=entry_4_win_rate,
            tp_price=entry_4_tp,
            sl_price=entry_4_sl
        )
        entries.append(entry_4)
        
        return entries
    
    def _find_sell_entries(self, close: float, current_price: float, 
                          indicators: TechnicalIndicators, df: pd.DataFrame, 
                          signal: Signal) -> List[EntryPoint]:
        """Find sell entry points with intelligent TP/SL and win rate"""
        entries = []
        atr = indicators.atr
        
        # ===== ENTRY 1: UPPER BOLLINGER BAND (Aggressive resistance) =====
        entry_1_price = round(indicators.bb_upper, 2)
        entry_1_tp = round(entry_1_price - (atr * 3), 2)
        entry_1_sl = round(entry_1_price + (atr * 1.2), 2)
        
        entry_1_gain = ((entry_1_price - entry_1_tp) / entry_1_price) * 100
        entry_1_risk = ((entry_1_sl - entry_1_price) / entry_1_price) * 100
        entry_1_rrr = entry_1_gain / entry_1_risk if entry_1_risk > 0 else 0
        entry_1_win_rate = self._calculate_win_rate(
            "aggressive", entry_1_price, entry_1_tp, entry_1_sl, 
            indicators, df, signal
        )
        
        entry_1_strength = 90 if signal.confidence > 75 else 80
        if abs(entry_1_price - indicators.vwap) < atr:
            entry_1_strength = min(98, entry_1_strength + 5)
        
        entry_1 = EntryPoint(
            price=entry_1_price,
            type="aggressive",
            reason=f"Upper BB resistance - Strong pullback setup (RRR {entry_1_rrr:.2f}:1)",
            risk_reward_ratio=round(entry_1_rrr, 2),
            strength=entry_1_strength,
            order_type="SELL",
            win_rate=entry_1_win_rate,
            tp_price=entry_1_tp,
            sl_price=entry_1_sl
        )
        entries.append(entry_1)
        
        # ===== ENTRY 2: EMA-20 (Dynamic resistance) =====
        entry_2_price = round(indicators.ema_20, 2)
        entry_2_tp = round(entry_2_price - (atr * 2.8), 2)
        entry_2_sl = round(entry_2_price + (atr * 1.0), 2)
        
        entry_2_gain = ((entry_2_price - entry_2_tp) / entry_2_price) * 100
        entry_2_risk = ((entry_2_sl - entry_2_price) / entry_2_price) * 100
        entry_2_rrr = entry_2_gain / entry_2_risk if entry_2_risk > 0 else 0
        entry_2_win_rate = self._calculate_win_rate(
            "secondary", entry_2_price, entry_2_tp, entry_2_sl, 
            indicators, df, signal
        )
        
        entry_2_strength = 85 if signal.confidence > 75 else 70
        entry_2 = EntryPoint(
            price=entry_2_price,
            type="secondary",
            reason=f"EMA-20 dynamic resistance - Trend confirmation (RRR {entry_2_rrr:.2f}:1)",
            risk_reward_ratio=round(entry_2_rrr, 2),
            strength=entry_2_strength,
            order_type="SELL",
            win_rate=entry_2_win_rate,
            tp_price=entry_2_tp,
            sl_price=entry_2_sl
        )
        entries.append(entry_2)
        
        # ===== ENTRY 3: VWAP (Volume-weighted entry point) =====
        entry_3_price = round(indicators.vwap, 2)
        entry_3_tp = round(entry_3_price - (atr * 3.0), 2)
        entry_3_sl = round(entry_3_price + (atr * 1.1), 2)
        
        entry_3_gain = ((entry_3_price - entry_3_tp) / entry_3_price) * 100
        entry_3_risk = ((entry_3_sl - entry_3_price) / entry_3_price) * 100
        entry_3_rrr = entry_3_gain / entry_3_risk if entry_3_risk > 0 else 0
        entry_3_win_rate = self._calculate_win_rate(
            "primary", entry_3_price, entry_3_tp, entry_3_sl, 
            indicators, df, signal
        )
        
        entry_3_strength = 88 if signal.confidence > 70 else 75
        if abs(entry_3_price - indicators.bb_middle) < atr * 0.5:
            entry_3_strength = min(98, entry_3_strength + 3)
        
        entry_3 = EntryPoint(
            price=entry_3_price,
            type="primary",
            reason=f"VWAP fair value - Volume weighted (RRR {entry_3_rrr:.2f}:1)",
            risk_reward_ratio=round(entry_3_rrr, 2),
            strength=entry_3_strength,
            order_type="SELL",
            win_rate=entry_3_win_rate,
            tp_price=entry_3_tp,
            sl_price=entry_3_sl
        )
        entries.append(entry_3)
        
        # ===== ENTRY 4: CONSERVATIVE RALLY ENTRY =====
        entry_4_price = round(current_price + (atr * 0.6), 2)
        entry_4_tp = round(entry_4_price - (atr * 2.5), 2)
        entry_4_sl = round(entry_4_price + (atr * 0.8), 2)
        
        entry_4_gain = ((entry_4_price - entry_4_tp) / entry_4_price) * 100
        entry_4_risk = ((entry_4_sl - entry_4_price) / entry_4_price) * 100
        entry_4_rrr = entry_4_gain / entry_4_risk if entry_4_risk > 0 else 0
        entry_4_win_rate = self._calculate_win_rate(
            "primary", entry_4_price, entry_4_tp, entry_4_sl, 
            indicators, df, signal
        )
        
        entry_4_strength = 75 if signal.confidence > 65 else 60
        entry_4 = EntryPoint(
            price=entry_4_price,
            type="primary",
            reason=f"Current + 0.6 ATR (Conservative limit order, RRR {entry_4_rrr:.2f}:1)",
            risk_reward_ratio=round(entry_4_rrr, 2),
            strength=entry_4_strength,
            order_type="SELL",
            win_rate=entry_4_win_rate,
            tp_price=entry_4_tp,
            sl_price=entry_4_sl
        )
        entries.append(entry_4)
        
        return entries

class SessionDetector:
    """Detect active trading session"""
    
    def get_current_session(self) -> Session:
        utc_now = datetime.now(timezone.utc)
        hour = utc_now.hour
        
        # Asian: 00:00 - 08:00 UTC
        # London: 08:00 - 16:00 UTC
        # NY: 13:00 - 21:00 UTC
        # Overlap London-NY: 13:00 - 16:00 UTC
        
        if 13 <= hour < 16:
            return Session.OVERLAP
        elif 8 <= hour < 16:
            return Session.LONDON
        elif 13 <= hour < 21:
            return Session.NEW_YORK
        elif 0 <= hour < 8:
            return Session.ASIAN
        else:
            return Session.CLOSED
    
    def get_next_event(self) -> str:
        utc_now = datetime.now(timezone.utc)
        hour = utc_now.hour
        
        events = {
            8: "London Open",
            13: "NY Open / London-NY Overlap",
            16: "London Close",
            21: "NY Close",
            0: "Asian Open"
        }
        
        for h in sorted(events.keys()):
            if hour < h:
                remaining = h - hour
                return f"{events[h]} in {remaining}h"
        
        return "Asian Open in {}h".format(24 - hour)

class RecommendationEngine:
    """Generate human-readable recommendations"""
    
    def generate(self, signal: Signal, risk: RiskProfile, 
                 indicators: TechnicalIndicators, df: pd.DataFrame, current_price: float) -> str:
        
        if signal.type in [SignalType.STRONG_BUY.value, SignalType.BUY.value]:
            entry = current_price - (indicators.atr * 0.5)
            stop = entry - (risk.stop_loss_distance)
            target = entry + (risk.stop_loss_distance * 2)
            
            return (f"Consider LONG at ${entry:,.2f} (limit order). "
                   f"Stop loss ${stop:,.2f} ({risk.stop_loss_distance:,.2f} below). "
                   f"Target ${target:,.2f} (1:2 RRR). "
                   f"Use {int(risk.recommended_position_size*100)}% of normal size due to {risk.volatility_state} volatility.")
        
        elif signal.type in [SignalType.STRONG_SELL.value, SignalType.SELL.value]:
            entry = current_price + (indicators.atr * 0.5)
            stop = entry + (risk.stop_loss_distance)
            target = entry - (risk.stop_loss_distance * 2)
            
            return (f"Consider SHORT at ${entry:,.2f} (limit order). "
                   f"Stop loss ${stop:,.2f} ({risk.stop_loss_distance:,.2f} above). "
                   f"Target ${target:,.2f} (1:2 RRR). "
                   f"Use {int(risk.recommended_position_size*100)}% of normal size due to {risk.volatility_state} volatility.")
        
        else:
            return ("Market in consolidation phase. "
                   "Best to wait for clear breakout above ${:,.2f} or below ${:,.2f}.".format(
                       indicators.bb_upper, indicators.bb_lower))

class QuantEngine:
    """Main engine orchestrating all components"""
    
    def __init__(self):
        self.data_feed = DataFeed()
        self.technical_analyzer = TechnicalAnalyzer()
        self.signal_engine = SignalEngine()
        self.risk_manager = RiskManager()
        self.entry_point_finder = EntryPointFinder()
        self.session_detector = SessionDetector()
        self.recommendation_engine = RecommendationEngine()
        self.active_connections: Set[WebSocket] = set()
        self.running = False
    
    async def start(self):
        await self.data_feed.start()
        self.running = True
        asyncio.create_task(self._analysis_loop())
        logger.info("Quant Engine started")
    
    async def stop(self):
        self.running = False
        await self.data_feed.stop()
    
    async def _analysis_loop(self):
        """Main loop updating analysis every 5 seconds"""
        while self.running:
            try:
                await self._update_all_symbols()
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error in analysis loop: {e}")
                await asyncio.sleep(5)
    
    async def _update_all_symbols(self):
        """Update analysis for all symbols and broadcast"""
        # Refresh latest historical data before analysis
        await asyncio.gather(*[
            self.data_feed._fetch_binance_klines(sym, "1h", 500)
            for sym in self.data_feed.symbols
        ], return_exceptions=True)
        
        for symbol in self.data_feed.symbols:
            try:
                result = await self._analyze_symbol(symbol)
                if result:
                    await self._broadcast(result)
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")
    
    async def _analyze_symbol(self, symbol: str) -> Optional[QuantOutput]:
        """Perform full analysis on a symbol"""
        # Get latest price (current real-time price)
        current_price = await self.data_feed.get_latest_price(symbol)
        if not current_price:
            logger.warning(f"Could not fetch current price for {symbol}")
            return None
        
        # Get OHLCV historical data
        df = self.data_feed.get_ohlcv_array(symbol)
        if len(df) < 50:
            logger.warning(f"Not enough historical data for {symbol}: {len(df)} candles")
            return None
        
        # Calculate indicators
        indicators = self.technical_analyzer.calculate(df)
        if not indicators:
            return None
        
        # Generate signal
        signal, factors, regime = self.signal_engine.analyze(df, indicators)
        
        # Calculate risk
        risk = self.risk_manager.calculate_risk(df, indicators, signal)
        
        # Get session info
        session = self.session_detector.get_current_session()
        next_event = self.session_detector.get_next_event()
        
        # Generate recommendation
        recommendation = self.recommendation_engine.generate(
            signal, risk, indicators, df, current_price
        )
        
        # Find best entry points
        entry_points = self.entry_point_finder.find_entries(
            df, indicators, signal, current_price
        )
        
        # Market data summary
        market_data = MarketData(
            symbol=symbol,
            price=current_price,
            change_24h=current_price - df['close'].iloc[-24] if len(df) >= 24 else 0,
            change_percent_24h=((current_price / df['close'].iloc[-24]) - 1) * 100 if len(df) >= 24 else 0,
            high_24h=df['high'].tail(24).max() if len(df) >= 24 else df['high'].max(),
            low_24h=df['low'].tail(24).min() if len(df) >= 24 else df['low'].min(),
            volume_24h=df['volume'].tail(24).sum() if len(df) >= 24 else df['volume'].sum()
        )
        
        return QuantOutput(
            symbol=symbol,
            market_data=market_data,
            signal=signal,
            factors=factors,
            risk=risk,
            entry_points=entry_points,
            regime=regime,
            active_session=session.value,
            next_event=next_event,
            recommendation=recommendation,
            timestamp=datetime.now(timezone.utc)
        )
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"Client disconnected. Total: {len(self.active_connections)}")
    
    async def _broadcast(self, data: QuantOutput):
        """Broadcast to all connected clients"""
        if not self.active_connections:
            return
        
        message = self._serialize_output(data)
        disconnected = set()
        
        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.add(ws)
        
        # Clean up disconnected clients
        for ws in disconnected:
            self.active_connections.discard(ws)
    
    def _serialize_output(self, data: QuantOutput) -> dict:
        """Convert dataclass to dict for JSON serialization"""
        return {
            "symbol": data.symbol,
            "timestamp": data.timestamp.isoformat(),
            "market_data": {
                "price": round(data.market_data.price, 2),
                "change_24h": round(data.market_data.change_24h, 2),
                "change_percent_24h": round(data.market_data.change_percent_24h, 2),
                "high_24h": round(data.market_data.high_24h, 2),
                "low_24h": round(data.market_data.low_24h, 2),
                "volume_24h": round(data.market_data.volume_24h, 2)
            },
            "signal": {
                "type": data.signal.type,
                "score": data.signal.score,
                "confidence": data.signal.confidence,
                "label": data.signal.label
            },
            "factors": [
                {
                    "name": f.name,
                    "impact": f.impact,
                    "description": f.description,
                    "direction": f.direction
                }
                for f in data.factors
            ],
            "risk": {
                "volatility_state": data.risk.volatility_state,
                "atr_percent": round(data.risk.atr_percent, 2),
                "recommended_position_size": data.risk.recommended_position_size,
                "stop_loss_distance": data.risk.stop_loss_distance
            },
            "entry_points": [
                {
                    "price": ep.price,
                    "type": ep.type,
                    "reason": ep.reason,
                    "risk_reward_ratio": ep.risk_reward_ratio,
                    "strength": ep.strength,
                    "order_type": ep.order_type,
                    "win_rate": ep.win_rate,
                    "tp_price": ep.tp_price,
                    "sl_price": ep.sl_price
                }
                for ep in data.entry_points
            ],
            "regime": data.regime,
            "active_session": data.active_session,
            "next_event": data.next_event,
            "recommendation": data.recommendation
        }

# ==================== FASTAPI APP ====================

# Global engine instance
engine = QuantEngine()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await engine.start()
    yield
    # Shutdown
    await engine.stop()

app = FastAPI(
    title="Quant Engine Pro API",
    description="Real-time quantitative analysis engine for crypto and forex",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "service": "Quant Engine Pro",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "websocket": "/ws",
            "health": "/health",
            "snapshot": "/snapshot/{symbol}"
        }
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "active_connections": len(engine.active_connections),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": "Quant Engine Pro v2.0.0"
    }

@app.get("/snapshot/{symbol}")
async def get_snapshot(symbol: str = "BTCUSDT"):
    """Get current analysis snapshot for a symbol"""
    symbol = symbol.upper()
    if symbol not in engine.data_feed.symbols:
        return {"error": f"Symbol {symbol} not supported. Available: {', '.join(engine.data_feed.symbols)}"}
    
    result = await engine._analyze_symbol(symbol)
    if result:
        return engine._serialize_output(result)
    return {"error": f"Unable to analyze {symbol}. Not enough data or API error."}

@app.get("/symbols")
async def get_symbols():
    """Get list of available symbols"""
    return {
        "symbols": engine.data_feed.symbols,
        "count": len(engine.data_feed.symbols)
    }

@app.get("/snapshot")
async def get_all_snapshots():
    """Get analysis snapshots for all symbols"""
    results = []
    for symbol in engine.data_feed.symbols:
        try:
            result = await engine._analyze_symbol(symbol)
            if result:
                results.append(engine._serialize_output(result))
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
    
    return {
        "count": len(results),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": results
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await engine.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle client messages
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "subscribe":
                    # Client can subscribe to specific symbols
                    pass
                elif msg.get("action") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await engine.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await engine.disconnect(websocket)

# ==================== DASHBOARD HTML ====================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Quant Engine Pro - Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a;
            color: #fff;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
        }
        .container { max-width: 400px; width: 100%; }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .header h1 {
            font-size: 24px;
            font-weight: 800;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }
        .connection-status {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            color: #666;
        }
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #ef4444;
            transition: background 0.3s;
        }
        .status-dot.connected { background: #10b981; box-shadow: 0 0 10px #10b981; }
        
        .panel {
            background: #111;
            border: 1px solid #222;
            border-radius: 16px;
            overflow: hidden;
            margin-bottom: 20px;
        }
        
        .price-header {
            padding: 20px;
            background: #0d0d0d;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .symbol { font-size: 14px; color: #888; font-weight: 600; }
        .price { font-size: 28px; font-weight: 700; font-family: 'SF Mono', monospace; }
        .change { font-size: 12px; margin-top: 4px; }
        .change.positive { color: #10b981; }
        .change.negative { color: #ef4444; }
        
        .signal-section {
            padding: 30px 20px;
            text-align: center;
        }
        .gauge-container {
            width: 200px;
            height: 100px;
            margin: 0 auto 20px;
            position: relative;
        }
        .gauge-bg {
            width: 200px;
            height: 100px;
            background: conic-gradient(from 180deg at 50% 100%, 
                #ef4444 0deg, #f59e0b 60deg, #10b981 120deg, 
                #10b981 180deg, #f59e0b 240deg, #ef4444 300deg, #ef4444 360deg);
            border-radius: 100px 100px 0 0;
            mask: radial-gradient(at 50% 100%, transparent 60%, black 61%);
            opacity: 0.3;
        }
        .gauge-needle {
            position: absolute;
            bottom: 0;
            left: 50%;
            width: 4px;
            height: 90px;
            background: #fff;
            transform-origin: bottom center;
            transform: translateX(-50%) rotate(0deg);
            border-radius: 2px;
            transition: transform 0.8s cubic-bezier(0.34, 1.56, 0.64, 1);
            box-shadow: 0 0 20px rgba(255,255,255,0.3);
        }
        .gauge-center {
            position: absolute;
            bottom: -10px;
            left: 50%;
            transform: translateX(-50%);
            width: 20px;
            height: 20px;
            background: #fff;
            border-radius: 50%;
            box-shadow: 0 0 20px rgba(255,255,255,0.5);
        }
        
        .signal-label {
            font-size: 24px;
            font-weight: 800;
            margin-bottom: 8px;
            transition: color 0.3s;
        }
        .signal-label.strong_buy, .signal-label.buy { color: #10b981; }
        .signal-label.strong_sell, .signal-label.sell { color: #ef4444; }
        .signal-label.neutral { color: #f59e0b; }
        
        .signal-meta {
            display: flex;
            justify-content: center;
            gap: 20px;
            font-size: 13px;
            color: #888;
        }
        .confidence-badge {
            background: rgba(16, 185, 129, 0.1);
            color: #10b981;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: 600;
        }
        
        .factors-section { padding: 0 20px 20px; }
        .section-title {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #555;
            margin-bottom: 12px;
        }
        .factor-list { display: flex; flex-direction: column; gap: 8px; }
        .factor-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            border-left: 3px solid transparent;
            transition: all 0.3s;
        }
        .factor-item.bullish { border-left-color: #10b981; }
        .factor-item.bearish { border-left-color: #ef4444; }
        .factor-name { font-size: 13px; color: #aaa; }
        .factor-value { font-size: 13px; font-weight: 600; }
        .factor-value.positive { color: #10b981; }
        .factor-value.negative { color: #ef4444; }
        .factor-desc { font-size: 11px; color: #666; margin-top: 4px; }
        
        .entries-section {
            padding: 0 20px 20px;
            background: #0d0d0d;
            border-top: 1px solid #222;
        }
        .entry-list { display: flex; flex-direction: column; gap: 10px; }
        .entry-item {
            display: grid;
            grid-template-columns: 1fr auto;
            padding: 14px;
            background: rgba(16, 185, 129, 0.08);
            border: 1px solid rgba(16, 185, 129, 0.2);
            border-radius: 8px;
            transition: all 0.3s;
        }
        .entry-item:hover {
            background: rgba(16, 185, 129, 0.12);
            border-color: rgba(16, 185, 129, 0.4);
        }
        .entry-item.sell {
            background: rgba(239, 68, 68, 0.08);
            border-color: rgba(239, 68, 68, 0.2);
        }
        .entry-item.sell:hover {
            background: rgba(239, 68, 68, 0.12);
            border-color: rgba(239, 68, 68, 0.4);
        }
        .entry-left { display: flex; flex-direction: column; gap: 6px; }
        .entry-header {
            display: flex;
            align-items: center;
            gap: 12px;
            justify-content: space-between;
        }
        .entry-price {
            font-size: 16px;
            font-weight: 700;
            font-family: 'SF Mono', monospace;
            color: #fff;
        }
        .order-badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            white-space: nowrap;
        }
        .order-badge.buy {
            background: rgba(16, 185, 129, 0.2);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        .order-badge.sell {
            background: rgba(239, 68, 68, 0.2);
            color: #ef4444;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }
        .entry-type {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #888;
        }
        .entry-reason {
            font-size: 12px;
            color: #aaa;
            margin-top: 4px;
        }
        .entry-right {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            justify-content: space-between;
        }
        .entry-strength {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            color: #888;
        }
        .strength-bar {
            width: 60px;
            height: 4px;
            background: rgba(255,255,255,0.1);
            border-radius: 2px;
            overflow: hidden;
        }
        .strength-fill {
            height: 100%;
            background: linear-gradient(90deg, #10b981, #30d158);
            border-radius: 2px;
            transition: width 0.3s;
        }
        .entry-rrr {
            font-size: 11px;
            color: #10b981;
            font-weight: 600;
        }
        
        .action-section {
            padding: 20px;
            background: #0d0d0d;
            border-top: 1px solid #222;
        }
        .action-card {
            border-radius: 12px;
            padding: 16px;
            transition: all 0.3s;
        }
        .action-card.buy {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }
        .action-card.sell {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }
        .action-card.neutral {
            background: rgba(245, 158, 11, 0.1);
            border: 1px solid rgba(245, 158, 11, 0.2);
        }
        .action-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 12px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .action-card.buy .action-header { color: #10b981; }
        .action-card.sell .action-header { color: #ef4444; }
        .action-card.neutral .action-header { color: #f59e0b; }
        .action-text {
            font-size: 14px;
            line-height: 1.6;
            color: #ccc;
            margin-bottom: 12px;
        }
        .risk-pills {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        .risk-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            padding: 6px 12px;
            background: rgba(255,255,255,0.05);
            border-radius: 20px;
            color: #888;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1px;
            background: #222;
            margin-top: 16px;
        }
        .stat-box {
            background: #111;
            padding: 12px;
            text-align: center;
        }
        .stat-label {
            font-size: 10px;
            color: #555;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }
        .stat-value {
            font-size: 13px;
            font-weight: 600;
            color: #fff;
        }
        
        .last-update {
            text-align: center;
            font-size: 11px;
            color: #444;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ QUANT ENGINE PRO</h1>
            <div class="connection-status">
                <span class="status-dot" id="statusDot"></span>
                <span id="statusText">Connecting...</span>
            </div>
        </div>

        <div class="panel">
            <div class="price-header">
                <div>
                    <div class="symbol" id="symbol">BTCUSDT</div>
                    <div class="price" id="price">--</div>
                    <div class="change" id="change">--</div>
                </div>
            </div>

            <div class="signal-section">
                <div class="gauge-container">
                    <div class="gauge-bg"></div>
                    <div class="gauge-needle" id="gaugeNeedle"></div>
                    <div class="gauge-center"></div>
                </div>
                
                <div class="signal-label" id="signalLabel">--</div>
                
                <div class="signal-meta">
                    <span>Score: <strong id="scoreValue">--</strong></span>
                    <span class="confidence-badge" id="confidenceBadge">--</span>
                </div>
            </div>

            <div class="factors-section">
                <div class="section-title">Driving Factors</div>
                <div class="factor-list" id="factorList">
                    <!-- Dynamic content -->
                </div>
            </div>

            <div class="entries-section">
                <div class="section-title">Best Entry Points</div>
                <div class="entry-list" id="entryList">
                    <!-- Dynamic content -->
                </div>
            </div>

            <div class="action-section">
                <div class="action-card" id="actionCard">
                    <div class="action-header">
                        <span>⚡</span>
                        <span>Recommended Action</span>
                    </div>
                    <div class="action-text" id="actionText">
                        Waiting for data...
                    </div>
                    <div class="risk-pills" id="riskPills">
                        <!-- Dynamic content -->
                    </div>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-box">
                        <div class="stat-label">Regime</div>
                        <div class="stat-value" id="regimeValue">--</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Session</div>
                        <div class="stat-value" id="sessionValue">--</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Volatility</div>
                        <div class="stat-value" id="volValue">--</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Next Event</div>
                        <div class="stat-value" id="eventValue">--</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="last-update" id="lastUpdate">Last update: --</div>
    </div>

    <script>
        let ws = null;
        const statusDot = document.getElementById('statusDot');
        const statusText = document.getElementById('statusText');
        
        // Initialize with REST API data
        async function initializeData() {
            try {
                const response = await fetch('/snapshot/BTCUSDT');
                if (!response.ok) throw new Error('Failed to fetch data');
                const data = await response.json();
                updateDashboard(data);
                console.log('Initial data loaded from API');
            } catch (error) {
                console.error('Error loading initial data:', error);
                statusText.textContent = 'No data (API error)';
            }
        }
        
        // Connect to WebSocket
        function connectWebSocket() {
            try {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws`;
                console.log('Connecting to WebSocket:', wsUrl);
                
                ws = new WebSocket(wsUrl);
                
                ws.onopen = () => {
                    console.log('WebSocket connected');
                    statusDot.classList.add('connected');
                    statusText.textContent = 'Live';
                };
                
                ws.onclose = () => {
                    console.log('WebSocket disconnected');
                    statusDot.classList.remove('connected');
                    statusText.textContent = 'Disconnected';
                    // Try to reconnect after 3 seconds
                    setTimeout(connectWebSocket, 3000);
                };
                
                ws.onerror = (error) => {
                    console.error('WebSocket error:', error);
                    statusText.textContent = 'Connection error';
                };
                
                ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        // Only update dashboard for BTCUSDT - filter out other symbols
                        if (data.symbol === 'BTCUSDT') {
                            updateDashboard(data);
                        }
                    } catch (error) {
                        console.error('Error parsing message:', error);
                    }
                };
            } catch (error) {
                console.error('Error connecting to WebSocket:', error);
                statusText.textContent = 'Connection failed';
            }
        }
        
        function updateDashboard(data) {
            // Price
            document.getElementById('price').textContent = 
                '$' + data.market_data.price.toLocaleString();
            
            const changeEl = document.getElementById('change');
            const change = data.market_data.change_percent_24h;
            changeEl.textContent = (change >= 0 ? '+' : '') + change.toFixed(2) + '% (24h)';
            changeEl.className = 'change ' + (change >= 0 ? 'positive' : 'negative');
            
            // Signal Gauge
            const score = data.signal.score;
            const angle = (score / 100) * 90;
            document.getElementById('gaugeNeedle').style.transform = 
                `translateX(-50%) rotate(${angle}deg)`;
            
            // Signal Label
            const labelEl = document.getElementById('signalLabel');
            labelEl.textContent = data.signal.label;
            labelEl.className = 'signal-label ' + data.signal.type;
            
            // Meta
            document.getElementById('scoreValue').textContent = 
                (score > 0 ? '+' : '') + score;
            document.getElementById('confidenceBadge').textContent = 
                data.signal.confidence + '% Confidence';
            
            // Factors
            const factorList = document.getElementById('factorList');
            factorList.innerHTML = data.factors.map(f => `
                <div class="factor-item ${f.direction}">
                    <div>
                        <div class="factor-name">${f.name}</div>
                        <div class="factor-desc">${f.description}</div>
                    </div>
                    <div class="factor-value ${f.impact > 0 ? 'positive' : 'negative'}">
                        ${f.impact > 0 ? '+' : ''}${f.impact}
                    </div>
                </div>
            `).join('');
            
            // Entry Points
            const entryList = document.getElementById('entryList');
            if (data.entry_points && data.entry_points.length > 0) {
                entryList.innerHTML = data.entry_points.map(ep => `
                    <div class="entry-item ${ep.order_type === 'SELL' ? 'sell' : 'buy'}">
                        <div class="entry-left">
                            <div class="entry-header">
                                <div class="entry-price">$${ep.price.toLocaleString()}</div>
                                <span class="order-badge ${ep.order_type.toLowerCase()}">${ep.order_type}</span>
                            </div>
                            <div class="entry-type">${ep.type}</div>
                            <div class="entry-reason">${ep.reason}</div>
                        </div>
                        <div class="entry-right">
                            <div class="entry-strength">
                                <span>Strength</span>
                                <div class="strength-bar">
                                    <div class="strength-fill" style="width: ${ep.strength}%"></div>
                                </div>
                                <span>${ep.strength}%</span>
                            </div>
                            <div class="entry-rrr">RRR: ${ep.risk_reward_ratio.toFixed(1)}:1</div>
                        </div>
                    </div>
                `).join('');
            } else {
                entryList.innerHTML = '<div style="color: #666; font-size: 13px;">No entry points available for this signal</div>';
            }
            
            // Action Card
            const actionCard = document.getElementById('actionCard');
            actionCard.className = 'action-card ' + data.signal.type;
            document.getElementById('actionText').textContent = data.recommendation;
            
            // Risk Pills
            const riskPills = document.getElementById('riskPills');
            riskPills.innerHTML = `
                <div class="risk-pill">🛡️ ${data.risk.volatility_state} volatility</div>
                <div class="risk-pill">📊 ATR ${data.risk.atr_percent.toFixed(2)}%</div>
                <div class="risk-pill">💰 Size ${Math.round(data.risk.recommended_position_size * 100)}%</div>
            `;
            
            // Stats
            document.getElementById('regimeValue').textContent = 
                data.regime.replace(/_/g, ' ');
            document.getElementById('sessionValue').textContent = data.active_session;
            document.getElementById('volValue').textContent = data.risk.volatility_state;
            document.getElementById('eventValue').textContent = data.next_event;
            
            // Last update
            document.getElementById('lastUpdate').textContent = 
                'Last update: ' + new Date().toLocaleTimeString();
        }
        
        // Load initial data and connect to WebSocket
        window.addEventListener('DOMContentLoaded', () => {
            console.log('Dashboard loading...');
            initializeData();
            connectWebSocket();
        });
        
        // Keep connection alive with periodic pings
        setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                try {
                    ws.send(JSON.stringify({action: 'ping'}));
                } catch (error) {
                    console.error('Error sending ping:', error);
                }
            }
        }, 30000);
    </script>
</body>
</html>
"""

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML

if __name__ == "__main__":
    import uvicorn
    
    # Get port from environment or use default
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    reload = os.getenv("RELOAD", "false").lower() == "true"
    
    logger.info(f"Starting Quant Engine Pro on {host}:{port}")
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )