# BTC Race Bot — Deep-Dip Mean Reversion

Bot for make.fun competition `btc-race-24h-20261118-1444` ("Race a BTC
trading bot live for 24 hours"). It trades Coinbase Wrapped BTC (CBBTC)
against USDC on 1-minute bars, starting with $1,000 of paper money,
long only, at most one position at a time.

## How it trades

One setup only — a deep dip below the recent mean, bought with full cash:

- **Reference:** the integer mean of the last 60 closes.
- **Entry:** when the latest close is 130 bps or more below that mean
  (`close * 10000 <= mean * 9870`), buy with all available cash.
  No entry before 60 closes exist, and no new entry after bar 1320.
- **Exit — sell the whole position when any of these fires:**
  - take profit: close 180 bps above the buy's fill price;
  - stop loss: close 60 bps below the buy's fill price;
  - time stop: the position has been held 480 bars or more.
- **Orders:** `max_slippage_bps = 100` on every order.

The entry price is the fill price the replay reports for the buy, and
the entry bar is the batch that reports that fill. All arithmetic is
integer (no floats); the bot is a pure function of the bars and fills it
has already seen — no clock, no network, no files, no randomness — so
two runs on the same data produce identical orders.

## Files

- `main.py` — the bot (entrypoint).
- `vendor/makefun_bars.py` — the kit's protocol shim, copied byte-for-byte.
- `.makefun/owner.json` — owner wallet for the submission.

## Run locally

```sh
python3 main.py
```

The bot speaks `agent-fun/bars-replay/v1` over stdin/stdout (NDJSON: a
`hello` line, then one `batch` per minute, one `reply` per batch). The
vendored shim owns the wire; `main.py` only decides the orders.
