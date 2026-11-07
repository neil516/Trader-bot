# iq_signal_telegram_bot.py
# IQ Option Elite Signal Bot — Telegram Interface
# Runs free on Replit | Philippines optimized

import time
import logging
import threading
import requests
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
from dataclasses import dataclass

try:
    from iqoptionapi.stable_api import IQ_Option
    import pandas as pd
    import pandas_ta as ta
except ImportError:
    print("pip install iqoptionapi pandas pandas-ta requests")
    raise

# ─── YOUR CONFIG ──────────────────────────────────────────────────────────────
IQ_EMAIL       = "neilandrei02242011@gmail.com"
IQ_PASSWORD    = "neil201124"
TELEGRAM_TOKEN = "Y9037023238:AAER6_yeeEPC1IAn0AuruH5B0P54fChx6Z8"      # from @BotFather on Telegram
TELEGRAM_CHAT  = "7562965318"        # from @userinfobot on Telegram
ACCOUNT_TYPE   = "PRACTICE"            # PRACTICE or REAL
TRADE_AMOUNT   = 1.0
EXPIRY_MINUTES = 1
CONFIDENCE_MIN = 80
TIMEZONE       = ZoneInfo("Asia/Manila")

# ─── ASSETS ───────────────────────────────────────────────────────────────────
ASSETS = {
    "digital": [
        "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC",
        "AUDCAD-OTC", "EURJPY-OTC", "EURGBP-OTC",
        "USDCHF-OTC", "GBPJPY-OTC",
    ],
    "forex": [
        "EURUSD", "GBPUSD", "USDJPY",
        "AUDUSD", "USDCAD", "NZDUSD",
    ],
    "stocks": [
        "AAPL", "TSLA", "GOOGL",
        "AMZN", "MSFT", "NFLX",
    ],
}

# ─── LOGGER ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("IQBot")

def ph_now() -> str:
    return datetime.now(TIMEZONE).strftime("%H:%M:%S PHT")

def ph_date() -> str:
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M PHT")

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────
class Telegram:
    BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

    @staticmethod
    def send(text: str):
        try:
            requests.post(
                f"{Telegram.BASE}/sendMessage",
                json={
                    "chat_id":    TELEGRAM_CHAT,
                    "text":       text,
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
        except Exception as e:
            log.warning(f"Telegram send failed: {e}")

    @staticmethod
    def get_updates(offset: int = 0) -> list:
        try:
            r = requests.get(
                f"{Telegram.BASE}/getUpdates",
                params={"offset": offset, "timeout": 10},
                timeout=15,
            )
            return r.json().get("result", [])
        except Exception:
            return []

# ─── CANDLE PATTERN ENGINE ────────────────────────────────────────────────────
class CandlePatterns:
    """
    Full encyclopedia of candlestick patterns.
    Returns: +1 (bullish), -1 (bearish), 0 (neutral)
    with pattern name for the signal message.
    """

    @staticmethod
    def _body(o, c):       return abs(c - o)
    @staticmethod
    def _upper(o, c, h):   return h - max(o, c)
    @staticmethod
    def _lower(o, c, l):   return min(o, c) - l
    @staticmethod
    def _range(h, l):      return h - l
    @staticmethod
    def _bullish(o, c):    return c > o
    @staticmethod
    def _bearish(o, c):    return c < o

    def analyze(self, df: pd.DataFrame) -> tuple[int, list[str]]:
        """Returns (vote, [pattern_names_detected])"""
        if len(df) < 5:
            return 0, []

        patterns = []
        total_vote = 0

        # extract last 5 candles
        candles = []
        for i in range(-5, 0):
            o = df["open"].iloc[i]
            c = df["close"].iloc[i]
            h = df["high"].iloc[i]
            l = df["low"].iloc[i]
            candles.append((o, c, h, l))

        o1,c1,h1,l1 = candles[-1]  # current
        o2,c2,h2,l2 = candles[-2]  # prev 1
        o3,c3,h3,l3 = candles[-3]  # prev 2
        o4,c4,h4,l4 = candles[-4]
        o5,c5,h5,l5 = candles[-5]

        body1 = self._body(o1,c1)
        body2 = self._body(o2,c2)
        body3 = self._body(o3,c3)
        rng1  = self._range(h1,l1)
        rng2  = self._range(h2,l2)

        # ── SINGLE CANDLE PATTERNS ──────────────────────────────────────

        # Doji — tiny body, long wicks
        if rng1 > 0 and body1 / rng1 < 0.1:
            patterns.append("🕯 Doji (Reversal Warning)")
            # neutral but counts as indecision — slight reversal signal
            total_vote += (1 if self._bearish(o2,c2) else -1)

        # Hammer — small body top, long lower wick, bullish
        lower1 = self._lower(o1,c1,l1)
        upper1 = self._upper(o1,c1,h1)
        if (lower1 > body1 * 2 and
                upper1 < body1 * 0.5 and
                self._bearish(o2,c2)):
            patterns.append("🔨 Hammer (Bullish Reversal)")
            total_vote += 2

        # Inverted Hammer — small body bottom, long upper wick, bullish
        if (upper1 > body1 * 2 and
                lower1 < body1 * 0.5 and
                self._bearish(o2,c2)):
            patterns.append("🔄 Inverted Hammer (Bullish)")
            total_vote += 1

        # Shooting Star — small body bottom, long upper wick, bearish
        if (upper1 > body1 * 2 and
                lower1 < body1 * 0.5 and
                self._bullish(o2,c2)):
            patterns.append("⭐ Shooting Star (Bearish Reversal)")
            total_vote -= 2

        # Hanging Man — hammer shape after uptrend, bearish
        if (lower1 > body1 * 2 and
                upper1 < body1 * 0.5 and
                self._bullish(o2,c2)):
            patterns.append("🪢 Hanging Man (Bearish)")
            total_vote -= 1

        # Spinning Top — small body, equal wicks
        if (rng1 > 0 and
                body1 / rng1 < 0.3 and
                upper1 > 0 and lower1 > 0 and
                abs(upper1 - lower1) < body1):
            patterns.append("🌀 Spinning Top (Indecision)")

        # Marubozu Bullish — full body, no wicks
        if (self._bullish(o1,c1) and
                upper1 < body1 * 0.05 and
                lower1 < body1 * 0.05):
            patterns.append("💚 Bullish Marubozu (Strong BUY)")
            total_vote += 3

        # Marubozu Bearish
        if (self._bearish(o1,c1) and
                upper1 < body1 * 0.05 and
                lower1 < body1 * 0.05):
            patterns.append("❤️ Bearish Marubozu (Strong SELL)")
            total_vote -= 3

        # ── TWO CANDLE PATTERNS ─────────────────────────────────────────

        # Bullish Engulfing
        if (self._bearish(o2,c2) and
                self._bullish(o1,c1) and
                o1 <= c2 and c1 >= o2 and
                body1 > body2):
            patterns.append("🟢 Bullish Engulfing (Strong BUY)")
            total_vote += 3

        # Bearish Engulfing
        if (self._bullish(o2,c2) and
                self._bearish(o1,c1) and
                o1 >= c2 and c1 <= o2 and
                body1 > body2):
            patterns.append("🔴 Bearish Engulfing (Strong SELL)")
            total_vote -= 3

        # Bullish Harami — small bullish inside big bearish
        if (self._bearish(o2,c2) and
                self._bullish(o1,c1) and
                o1 > c2 and c1 < o2 and
                body1 < body2 * 0.5):
            patterns.append("🫀 Bullish Harami (Reversal)")
            total_vote += 2

        # Bearish Harami
        if (self._bullish(o2,c2) and
                self._bearish(o1,c1) and
                o1 < c2 and c1 > o2 and
                body1 < body2 * 0.5):
            patterns.append("🫀 Bearish Harami (Reversal)")
            total_vote -= 2

        # Tweezer Tops — bearish reversal
        if (self._bullish(o2,c2) and
                self._bearish(o1,c1) and
                abs(h1 - h2) < rng1 * 0.05):
            patterns.append("🔝 Tweezer Tops (Bearish)")
            total_vote -= 2

        # Tweezer Bottoms — bullish reversal
        if (self._bearish(o2,c2) and
                self._bullish(o1,c1) and
                abs(l1 - l2) < rng1 * 0.05):
            patterns.append("🔽 Tweezer Bottoms (Bullish)")
            total_vote += 2

        # Dark Cloud Cover — bearish
        mid2 = (o2 + c2) / 2
        if (self._bullish(o2,c2) and
                self._bearish(o1,c1) and
                o1 > h2 and c1 < mid2):
            patterns.append("☁️ Dark Cloud Cover (Bearish)")
            total_vote -= 3

        # Piercing Line — bullish
        mid2 = (o2 + c2) / 2
        if (self._bearish(o2,c2) and
                self._bullish(o1,c1) and
                o1 < l2 and c1 > mid2):
            patterns.append("💡 Piercing Line (Bullish)")
            total_vote += 3

        # ── THREE CANDLE PATTERNS ───────────────────────────────────────

        # Morning Star — bullish reversal
        body_star = self._body(o2,c2)
        if (self._bearish(o3,c3) and
                body_star < self._body(o3,c3) * 0.3 and
                self._bullish(o1,c1) and
                c1 > (o3 + c3) / 2):
            patterns.append("🌅 Morning Star (Strong BUY)")
            total_vote += 4

        # Evening Star — bearish reversal
        if (self._bullish(o3,c3) and
                body_star < self._body(o3,c3) * 0.3 and
                self._bearish(o1,c1) and
                c1 < (o3 + c3) / 2):
            patterns.append("🌃 Evening Star (Strong SELL)")
            total_vote -= 4

        # Three White Soldiers — strong bullish
        if (self._bullish(o3,c3) and
                self._bullish(o2,c2) and
                self._bullish(o1,c1) and
                c3 < c2 < c1 and
                o2 > o3 and o1 > o2):
            patterns.append("💪 Three White Soldiers (Strong BUY)")
            total_vote += 4

        # Three Black Crows — strong bearish
        if (self._bearish(o3,c3) and
                self._bearish(o2,c2) and
                self._bearish(o1,c1) and
                c3 > c2 > c1 and
                o2 < o3 and o1 < o2):
            patterns.append("🦅 Three Black Crows (Strong SELL)")
            total_vote -= 4

        # Three Inside Up — bullish confirmation
        if (self._bearish(o3,c3) and
                self._bullish(o2,c2) and
                o2 > c3 and c2 < o3 and
                self._bullish(o1,c1) and
                c1 > o3):
            patterns.append("📈 Three Inside Up (Bullish Confirm)")
            total_vote += 3

        # Three Inside Down — bearish confirmation
        if (self._bullish(o3,c3) and
                self._bearish(o2,c2) and
                o2 < c3 and c2 > o3 and
                self._bearish(o1,c1) and
                c1 < o3):
            patterns.append("📉 Three Inside Down (Bearish Confirm)")
            total_vote -= 3

        # Rising Three Methods — bullish continuation
        if (self._bullish(o5,c5) and
                self._bearish(o4,c4) and
                self._bearish(o3,c3) and
                self._bearish(o2,c2) and
                self._bullish(o1,c1) and
                c1 > c5):
            patterns.append("📊 Rising Three Methods (BUY Continuation)")
            total_vote += 3

        # Falling Three Methods — bearish continuation
        if (self._bearish(o5,c5) and
                self._bullish(o4,c4) and
                self._bullish(o3,c3) and
                self._bullish(o2,c2) and
                self._bearish(o1,c1) and
                c1 < c5):
            patterns.append("📊 Falling Three Methods (SELL Continuation)")
            total_vote -= 3

        # normalize vote to -10..+10 range
        total_vote = max(-10, min(10, total_vote))
        return total_vote, patterns

# ─── INDICATOR ENGINE ─────────────────────────────────────────────────────────
class IndicatorEngine:
    """9 technical indicators with weighted confluence scoring."""

    def analyze(self, df: pd.DataFrame) -> dict:
        if len(df) < 30:
            return {"score": 0, "signals": {}}

        signals = {}

        # EMA cross
        ema9  = ta.ema(df["close"], length=9)
        ema21 = ta.ema(df["close"], length=21)
        if ema9 is not None and ema21 is not None:
            f, s = ema9.iloc[-1], ema21.iloc[-1]
            pf, ps = ema9.iloc[-2], ema21.iloc[-2]
            if pf < ps and f > s:   signals["EMA"] = (2, "BUY cross")
            elif pf > ps and f < s: signals["EMA"] = (-2, "SELL cross")
            else:                   signals["EMA"] = (1 if f > s else -1, "EMA trend")

        # RSI
        rsi = ta.rsi(df["close"], length=14)
        if rsi is not None:
            v = rsi.iloc[-1]
            if v < 25:    signals["RSI"] = (2, f"Oversold {v:.0f}")
            elif v > 75:  signals["RSI"] = (-2, f"Overbought {v:.0f}")
            elif v < 45:  signals["RSI"] = (1, f"Leaning BUY {v:.0f}")
            elif v > 55:  signals["RSI"] = (-1, f"Leaning SELL {v:.0f}")
            else:         signals["RSI"] = (0, f"Neutral {v:.0f}")

        # MACD
        macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            h_col = [c for c in macd.columns if "h" in c.lower()]
            if h_col:
                h = macd[h_col[0]]
                if h.iloc[-1] > 0 and h.iloc[-2] < 0:
                    signals["MACD"] = (2, "Bull cross")
                elif h.iloc[-1] < 0 and h.iloc[-2] > 0:
                    signals["MACD"] = (-2, "Bear cross")
                else:
                    signals["MACD"] = (1 if h.iloc[-1] > 0 else -1, "Trend")

        # Bollinger Bands
        bb = ta.bbands(df["close"], length=20)
        if bb is not None and not bb.empty:
            lc = [c for c in bb.columns if "l" in c.lower()]
            uc = [c for c in bb.columns if "u" in c.lower()]
            if lc and uc:
                price = df["close"].iloc[-1]
                if price <= bb[lc[0]].iloc[-1]:
                    signals["BB"] = (2, "At lower band")
                elif price >= bb[uc[0]].iloc[-1]:
                    signals["BB"] = (-2, "At upper band")
                else:
                    signals["BB"] = (0, "Inside bands")

        # Stochastic
        stoch = ta.stoch(df["high"], df["low"], df["close"])
        if stoch is not None and not stoch.empty:
            kc = [c for c in stoch.columns if "k" in c.lower()]
            dc = [c for c in stoch.columns if "d" in c.lower()]
            if kc and dc:
                k = stoch[kc[0]].iloc[-1]
                d = stoch[dc[0]].iloc[-1]
                pk = stoch[kc[0]].iloc[-2]
                pd_ = stoch[dc[0]].iloc[-2]
                if k < 20 and pk < pd_ and k > d:
                    signals["STOCH"] = (2, f"Oversold cross K:{k:.0f}")
                elif k > 80 and pk > pd_ and k < d:
                    signals["STOCH"] = (-2, f"Overbought cross K:{k:.0f}")
                else:
                    signals["STOCH"] = (1 if k < 50 else -1, f"K:{k:.0f}")

        # ADX
        adx_df = ta.adx(df["high"], df["low"], df["close"])
        if adx_df is not None and not adx_df.empty:
            ac = [c for c in adx_df.columns if "adx" in c.lower()]
            dpc = [c for c in adx_df.columns if "dmp" in c.lower()]
            dnc = [c for c in adx_df.columns if "dmn" in c.lower()]
            if ac:
                adx_v = adx_df[ac[0]].iloc[-1]
                if adx_v > 25 and dpc and dnc:
                    dmp = adx_df[dpc[0]].iloc[-1]
                    dmn = adx_df[dnc[0]].iloc[-1]
                    signals["ADX"] = (
                        2 if dmp > dmn else -2,
                        f"Strong trend ADX:{adx_v:.0f}"
                    )
                else:
                    signals["ADX"] = (0, f"Weak trend ADX:{adx_v:.0f}")

        # VWAP
        if "volume" in df.columns and df["volume"].sum() > 0:
            try:
                vwap = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
                if vwap is not None:
                    price = df["close"].iloc[-1]
                    v_val = vwap.iloc[-1]
                    signals["VWAP"] = (
                        1 if price > v_val else -1,
                        f"{'Above' if price > v_val else 'Below'} VWAP"
                    )
            except Exception:
                pass

        # ATR volatility filter
        atr = ta.atr(df["high"], df["low"], df["close"], length=14)
        if atr is not None:
            atr_pct = atr.iloc[-1] / df["close"].iloc[-1] * 100
            if atr_pct > 0.5:  # good volatility
                signals["VOLATILITY"] = (0, f"ATR {atr_pct:.2f}% ✅")
            else:
                signals["VOLATILITY"] = (0, f"Low ATR {atr_pct:.2f}% ⚠️")

        # weighted score
        weights = {
            "EMA": 2.5, "RSI": 2.0, "MACD": 2.5,
            "BB": 1.5, "STOCH": 2.0, "ADX": 2.5,
            "VWAP": 1.5, "VOLATILITY": 0
        }
        total_w = sum(w for k, w in weights.items() if k != "VOLATILITY")
        score = sum(
            signals[k][0] * weights.get(k, 1)
            for k in signals if k in weights
        )
        normalized = (score / (total_w * 2)) * 100  # -100 to +100

        return {"score": normalized, "signals": signals}

# ─── MAIN SIGNAL AGGREGATOR ───────────────────────────────────────────────────
@dataclass
class Signal:
    asset:       str
    direction:   str   # BUY / SELL / NEUTRAL
    confidence:  float
    patterns:    list[str]
    indicators:  dict
    mode:        str
    timestamp:   str

class SignalAggregator:
    def __init__(self):
        self.patterns   = CandlePatterns()
        self.indicators = IndicatorEngine()

    def analyze(self, df: pd.DataFrame, asset: str, mode: str) -> Signal:
        # candle pattern vote (-10 to +10)
        pattern_vote, found_patterns = self.patterns.analyze(df)

        # indicator score (-100 to +100)
        ind_result = self.indicators.analyze(df)
        ind_score  = ind_result["score"]

        # combine: patterns 40% weight, indicators 60%
        combined = (pattern_vote / 10 * 40) + (ind_score / 100 * 60)
        # combined is -100 to +100

        buy_conf  = max(0.0, combined)
        sell_conf = max(0.0, -combined)

        if buy_conf >= CONFIDENCE_MIN:
            direction  = "BUY"
            confidence = round(buy_conf, 1)
        elif sell_conf >= CONFIDENCE_MIN:
            direction  = "SELL"
            confidence = round(sell_conf, 1)
        else:
            direction  = "NEUTRAL"
            confidence = round(max(buy_conf, sell_conf), 1)

        return Signal(
            asset      = asset,
            direction  = direction,
            confidence = confidence,
            patterns   = found_patterns,
            indicators = ind_result["signals"],
            mode       = mode,
            timestamp  = ph_now(),
        )

# ─── BOT CORE ─────────────────────────────────────────────────────────────────
class IQTelegramBot:
    def __init__(self):
        self.api        = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
        self.aggregator = SignalAggregator()
        self.mode       = "digital"
        self.running    = False
        self.paused     = False
        self.last_update= 0
        self.stats      = {"signals": 0, "wins": 0, "losses": 0}

    def connect(self) -> bool:
        log.info("Connecting...")
        status, reason = self.api.connect()
        if not status:
            Telegram.send(f"❌ Connection failed: {reason}")
            return False
        self.api.change_balance(ACCOUNT_TYPE)
        bal = self.api.get_balance()
        Telegram.send(
            f"✅ <b>IQ Option Elite Bot Online</b>\n"
            f"💰 Balance: <b>${bal:.2f}</b>\n"
            f"📊 Mode: <b>{ACCOUNT_TYPE}</b>\n"
            f"🕐 {ph_date()}\n\n"
            f"Commands:\n"
            f"/mode digital — OTC pairs\n"
            f"/mode forex — live forex\n"
            f"/mode stocks — US stocks\n"
            f"/pause — pause trading\n"
            f"/re
