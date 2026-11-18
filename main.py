"""Deep-dip mean-reversion bot for the make.fun BTC race (bars-replay/v1).

The race window is a single asset, CBBTC against USDC, one 1-minute bar per
batch. This bot does exactly one thing: it waits until the latest close has
fallen well below its recent average, buys with all of its cash, and then
sells the whole position when the price bounces back, when it keeps falling,
or when the trade has simply been held too long.

Why that shape: on a day that drifts down with only small minute-to-minute
moves, chasing the trend bleeds fees on every whipsaw. A deep dip below the
60-bar average is the one place where the price has stretched far enough
from where it has been that a snap back is worth paying the round-trip
cost for. Everything else -- the take-profit, the stop, the hold cap, the
late-window cutoff -- exists to keep a single bad idea from eating the
account while it waits for that snap back.

All arithmetic is integer. Prices arrive at price_scale 5 (one unit is
0.00001 USDC) and cash at quote_scale 6 (one unit is 0.000001 USDC), so a
comparison like "close is 130 bps below the mean" is done by multiplying
both sides out instead of dividing into a float. The bot reads no clock,
no files and no network; its orders are a pure function of the bars and
fills it has already been handed.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# --- strategy parameters, in basis points unless noted --------------------
LOOKBACK_BARS = 60        # bars averaged for the dip reference
DIP_BPS = 130             # buy when close is this far below the average
TAKE_PROFIT_BPS = 180     # sell when close is this far above the fill price
STOP_LOSS_BPS = 60        # sell when close is this far below the fill price
MAX_HOLD_BARS = 480       # sell once the position is this many bars old
LAST_ENTRY_BAR = 1320     # no new buys once the bar index passes this
MAX_SLIPPAGE_BPS = 100    # slippage bound on every order
MIN_NOTIONAL = 1_000_000  # 1 USDC, in micro-USDC quote units

BPS = 10_000


class DipBot:
    """Keeps the closes seen so far and the open trade, if any."""

    def __init__(self):
        self.closes = []
        self.entry_price = None  # fill price of the open position, or None
        self.entry_bar = None    # bar index (batch seq) the buy filled on

    def note_fills(self, state, batch):
        """Learn from the fills this batch reports.

        A buy decided on the previous bar fills at this bar's open, so the
        position only exists from the batch that carries its fill. That
        fill's price is the entry price every exit is measured against, and
        its bar is the clock the hold cap counts from. A sell fill closes
        the trade and clears both.
        """
        for fill in batch.get("fills", []):
            if fill.get("symbol") != SYMBOL or fill.get("status") != "filled":
                continue
            if fill.get("side") == "buy":
                self.entry_price = int(fill["price"])
                self.entry_bar = state.seq
            elif fill.get("side") == "sell":
                self.entry_price = None
                self.entry_bar = None

    def mean_of_recent(self):
        """Integer mean of the last LOOKBACK_BARS closes."""
        window = self.closes[-LOOKBACK_BARS:]
        return sum(window) // len(window)

    def exit_order(self, state):
        """A sell of the whole position if any exit rule fires, else None."""
        holding = state.positions.get(SYMBOL)
        if holding is None or holding.qty <= 0:
            return None
        if self.entry_price is None:
            # Position exists but its fill was never seen (should not
            # happen); without an entry price there is nothing to measure
            # against, so hold rather than guess.
            return None
        close = state.close(SYMBOL)
        if close is None:
            return None
        took_profit = close * BPS >= self.entry_price * (BPS + TAKE_PROFIT_BPS)
        stopped_out = close * BPS <= self.entry_price * (BPS - STOP_LOSS_BPS)
        held_too_long = (
            self.entry_bar is not None
            and (state.seq - self.entry_bar) >= MAX_HOLD_BARS
        )
        if took_profit or stopped_out or held_too_long:
            return {
                "side": "sell",
                "symbol": SYMBOL,
                "qty": holding.qty,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }
        return None

    def entry_order(self, state):
        """A buy of all cash when the close dips far below its average."""
        if state.warming_up or state.seq > LAST_ENTRY_BAR:
            return None
        if len(self.closes) < LOOKBACK_BARS:
            return None
        if state.positions.get(SYMBOL) is not None:
            return None
        if state.cash < MIN_NOTIONAL:
            return None
        close = state.close(SYMBOL)
        if close is None:
            return None
        average = self.mean_of_recent()
        dipped = close * BPS <= average * (BPS - DIP_BPS)
        if not dipped:
            return None
        return {
            "side": "buy",
            "symbol": SYMBOL,
            "notional_quote_units": state.cash,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }

    def on_batch(self, state, batch):
        """One reply per batch: record the bar, learn fills, then decide."""
        close = state.close(SYMBOL)
        if close is not None:
            self.closes.append(close)
        self.note_fills(state, batch)
        orders = []
        sell = self.exit_order(state)
        if sell is not None:
            orders.append(sell)
        else:
            buy = self.entry_order(state)
            if buy is not None:
                orders.append(buy)
        return orders


def main():
    bot = DipBot()
    makefun_bars.run(bot.on_batch)


if __name__ == "__main__":
    main()
