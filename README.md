# Binance RSI Sentinel

Real-time Binance Spot RSI(6) monitoring for USDT-quoted trading pairs, with automated Gmail alerts.

> **Status:** Milestones 1–5 implemented. Local testing and cloud deployment remain.

## Project goals

- Discover eligible, active Binance Spot symbols quoted in USDT.
- Monitor each symbol's **1-hour** candlestick stream.
- Calculate **RSI(6)** using Wilder's smoothing, updating with the still-forming candle.
- Email an alert when RSI crosses from **20 or above to below 20**.
- Avoid repeated emails while a symbol remains below the threshold; re-arm after RSI returns to 20 or above.
- Run continuously in Docker on a cloud VM, with reconnect and recovery handling.

This is an indicator-notification tool, not a trading bot. It does not place orders and does not provide investment advice.

## Planned architecture

```text
Binance Spot exchange information
             |
             v
   Eligible USDT symbol discovery
             |
             v
  1h candlestick WebSocket streams
             |
             v
  Wilder RSI(6) calculation engine
             |
             v
  Per-symbol threshold/alert state
             |
             v
          Gmail
```

SQLite persists per-symbol alert arming and a durable email outbox. Pending notifications are retried on startup and periodically while the service is running. Docker will package the service for deployment.

## Repository layout

```text
app/          Application source code
config/       Runtime configuration
data/         Runtime database (not committed)
logs/         Runtime logs (not committed)
tests/        Automated tests
```



## Requirements (planned)

- Python 3.12+
- Docker Engine and Docker Compose for deployment
- A Gmail account with 2-Step Verification and a Gmail App Password
- An Oracle Cloud VM or another always-on Linux host

Binance public market-data endpoints do not require an API key. The application should not request trading permissions.

## Configuration

Copy `.env.example` to `.env` for local development and fill in your own values. Never commit `.env`, Gmail App Passwords, SSH keys, or runtime database files.

The sender and recipient can be the same Gmail address. For SMTP, the application will use `smtp.gmail.com` with STARTTLS on port `587` and a Gmail App Password (not your normal account password).

## Signal semantics

- Market: Binance Spot, active symbols with quote asset `USDT`.
- Interval: `1h`.
- RSI length: `6`.
- Threshold: strictly less than `20`.
- Candle: current, still-forming candle is included; the RSI can move back above 20 before candle close.
- Alert: trigger on the transition from RSI `>= 20` to RSI `< 20`; re-arm when RSI returns to `>= 20`.

RSI values can differ slightly from charting platforms if their candle history, initialization, or smoothing conventions differ. The implementation will be tested against known Wilder RSI examples and checked against Binance chart data.

## Security

- Keep credentials in environment variables or a secret manager.
- Never put secrets in source code, screenshots, issues, logs, or commits.
- Use a read-only/public market-data connection; no Binance trading API key is needed.
- Rotate a Gmail App Password immediately if it is accidentally exposed.

## Run the Milestone 2 market-data smoke test

Create your local environment file and install the dependencies:

```bash
cp .env.example .env
pip install -r requirements.txt
python -m app.main
```

On Windows PowerShell, use `Copy-Item .env.example .env` instead of `cp`.

The runner discovers active Spot USDT symbols, downloads recent 1-hour candles, calculates Wilder RSI(6) on live updates, and queues Gmail alerts when RSI crosses below the configured threshold. SQLite persists each symbol's armed/disarmed state and pending email outbox across restarts. Pending emails are retried at startup and every 30 seconds. Press `Ctrl+C` to stop it. Symbols are split across WebSocket connections when needed to respect Binance's 1,024-stream-per-connection limit.

## Development milestones

1. Repository foundation and secure configuration template.
2. Binance Spot USDT symbol discovery and market-data client.
3. Wilder RSI(6) calculation and tests. (implemented; live forming-candle RSI is logged locally)
4. Gmail notification delivery. (implemented)
5. Alert state, SQLite persistence, and duplicate prevention. (implemented)
6. Docker packaging, reliability tests, and observability. (next)
7. Cloud deployment and 24/7 operation.

## Disclaimer

Cryptocurrency markets are volatile. An RSI reading below 20 does not guarantee a price reversal or profitable trade. Use alerts as information only and make independent decisions.
