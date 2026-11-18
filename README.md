# BTC Race Bot — Deep-Dip Mean Reversion

[![make.fun](https://make.fun/badge/btc-race-24h-20261118-1444)](https://make.fun/competitions/btc-race-24h-20261118-1444)

A bot for the [make.fun](https://make.fun) competition
`btc-race-24h-20261118-1444`: race a BTC trading bot live for 24 hours.
It trades Coinbase Wrapped BTC (CBBTC) against USDC on 1-minute bars,
starting with $1,000 of paper money, long only, one position at a time.

## Strategy

Single-tier deep-dip mean reversion, full cash on entry:

- **Entry:** when the latest close falls 130 bps or more below the mean of
  the last 60 closes, buy with all cash.
- **Exit (sell everything):** take profit at +180 bps above the fill price,
  stop loss at −60 bps below it, or a hold cap of 480 bars — whichever
  comes first.
- **Cutoff:** no new entries after bar 1320, so no trade is forced to close
  in the final minutes of the window.

All arithmetic is integer (micro-USDC and 1e-8 BTC units, no floats), and
the bot is a pure function of the bars and fills it has already seen: no
clock, no network, no files, no randomness.

## Run locally

```sh
python3 main.py
```

The bot speaks `agent-fun/bars-replay/v1` on stdin/stdout (NDJSON: a
`hello` line, then one `batch` per minute, one `reply` per batch). The
vendored `vendor/makefun_bars.py` shim owns the wire protocol; `main.py`
only decides orders.

## Files

- `main.py` — the bot
- `vendor/makefun_bars.py` — the kit's protocol shim, copied byte-for-byte
- `.makefun/owner.json` — owner wallet for the submission
