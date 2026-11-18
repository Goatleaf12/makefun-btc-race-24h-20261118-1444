"""Deep-dip mean-reversion bot for make.fun btc-race-24h-20261118-1444.

Protocol: agent-fun/bars-replay/v1, one JSON line per batch on stdin, one
reply per batch on stdout. The bot trades only CBBTC against USDC, long
only, starting from 1,000 USDC of paper money.

Strategy (deep-dip mean reversion, full cash, integer arithmetic only):
  - Keep the last 60 closes of CBBTC. Their integer mean is the reference.
  - Entry (only when flat, only while seq <= 1320, only with >= 60 closes):
    the latest close is at least 130 bps below the 60-bar mean, i.e.
    close * 10000 <= mean * 9870. Buy with ALL cash, max_slippage 100 bps.
  - Exit (sell the whole position) as soon as any of these holds:
    close >= entry fill price * (1 + 180 bps)   (take profit)
    close <= entry fill price * (1 - 60 bps)    (stop loss)
    the position has been held for >= 480 bars  (time stop)
  - The entry price is the fill price the harness reports for the buy, and
    the entry bar is the seq of the batch that reports that fill.

Everything is a pure function of the bars and fills seen so far: no clock,
no network, no files, no randomness. All comparisons are integer
multiplications, so two runs on the same data give identical replies.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars

SYMBOL = "CBBTC"

LOOKBACK = 60            # bars in the mean
ENTRY_DIP_BPS = 130      # buy when close is this far below the mean
TAKE_PROFIT_BPS = 180    # sell when close is this far above the entry fill
STOP_LOSS_BPS = 60       # sell when close is this far below the entry fill
MAX_HOLD_BARS = 480      # sell when the position is this old (in bars)
LAST_ENTRY_SEQ = 1320    # no new entry after this batch
MAX_SLIPPAGE_BPS = 100   # max slippage on every order
MIN_NOTIONAL = 1000000    # 1 USDC in micro-USDC; a buy below this is refused
BPS = 10000


class DeepDipBot:
    """State for one run: the close history and the open position's entry."""

    def __init__(self):
        self.closes = []
        self.entry_price = None  # fill price of the buy that opened the position
        self.entry_seq = None    # seq of the batch that reported that fill

    def absorb_fills(self, batch):
        """Fold this batch's fills into the entry record."""
        for fill in batch.get("fills", []):
            if fill.get("symbol") != SYMBOL:
                continue
            if fill.get("status") != "filled":
                continue
            if fill.get("side") == "buy":
                self.entry_price = int(fill["price"])
                self.entry_seq = batch["seq"]
            elif fill.get("side") == "sell":
                self.entry_price = None
                self.entry_seq = None

    def mean_close(self):
        """Integer mean of the last LOOKBACK closes (truncated)."""
        window = self.closes[-LOOKBACK:]
        return sum(window) // len(window)

    def decide(self, state, batch):
        """The orders decided on this batch's bar; [] for none."""
        self.absorb_fills(batch)
        bar = state.latest.get(SYMBOL)
        if bar is None:
            return []
        close = int(bar["c"])
        self.closes.append(close)

        holding = state.positions.get(SYMBOL)
        qty = holding.qty if holding is not None else 0

        if qty > 0:
            return self._maybe_exit(state, close, qty)

        if state.warming_up:
            return []
        if len(self.closes) < LOOKBACK:
            return []
        if state.seq > LAST_ENTRY_SEQ:
            return []
        if state.cash < MIN_NOTIONAL:
            return []
        mean = self.mean_close()
        if close * BPS <= mean * (BPS - ENTRY_DIP_BPS):
            return [{
                "side": "buy",
                "symbol": SYMBOL,
                "notional_quote_units": state.cash,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }]
        return []

    def _maybe_exit(self, state, close, qty):
        """Sell everything when take-profit, stop-loss or the time stop fires."""
        if self.entry_price is None or self.entry_seq is None:
            return []
        entry = self.entry_price
        took_profit = close * BPS >= entry * (BPS + TAKE_PROFIT_BPS)
        stopped_out = close * BPS <= entry * (BPS - STOP_LOSS_BPS)
        held_too_long = state.seq - self.entry_seq >= MAX_HOLD_BARS
        if not (took_profit or stopped_out or held_too_long):
            return []
        return [{
            "side": "sell",
            "symbol": SYMBOL,
            "qty": qty,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]


_BOT = DeepDipBot()


def on_batch(state, batch):
    return _BOT.decide(state, batch)


makefun_bars.run(on_batch)
