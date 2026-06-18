# ALGOPACK Access and Troubleshooting

## Subscription and Key Setup

- Register and sign in at DataShop: `https://data.moex.com`.
- Choose the currently available access level on Data MOEX/DataShop. `Стартовый / Starter` is the free API-token tier; `Promo` is paid/subscribed access. Entitlement, delay, and field coverage depend on the selected plan.
- Subscribe to ALGOPACK from the product page when paid or expanded entitlement is needed: `https://data.moex.com/products/algopack`.
- Generate the API key in the personal account: `https://data.moex.com/personal-account`.
- Treat commercial terms, prices, key lifetime, and current entitlement as account-facing details that can change.
- Never paste real API keys into source files, notebooks, shell history, logs, screenshots, or chat replies.

Direct REST pattern:

```bash
curl -L "https://apim.moex.com/iss/datashop/algopack/eq/obstats.json?date=2025-01-10" \
  -H "Authorization: Bearer ${APIKEY}"
```

Python library pattern:

```bash
python -m pip install "moexalgo[dataframe]" python-dotenv
```

```python
import os
from dotenv import load_dotenv
from moexalgo import session, Market

load_dotenv()
session.TOKEN = os.environ["APIKEY"]

eq = Market("EQ")
data = eq.obstats(date="2025-01-10")
```

Set `APIKEY=...` in a local `.env` file and keep that file out of source control. Setting `session.TOKEN` switches the library base URL to `https://apim.moex.com/iss` and adds `Authorization: Bearer ...`.

## Access Levels

Use this compact tier summary when users ask what access a token or subscription provides. Point users to Data MOEX/DataShop for current commercial terms, current entitlement, and price-sensitive details.

| Tier | Guidance |
| --- | --- |
| `Стартовый / Starter` free API-token tier | Includes 15-minute delayed candles and trades, FUTOI at `T - 15 days`, market map, website visualizations, API access, and the Python library. |
| `Стартовый / Starter` planned/upcoming | SuperCandles, Mega Alerts, and HI2 at `T - 1 day` are planned for the free token tier. Verify current availability before promising access. |
| `Promo` paid/subscribed tier | Includes FUTOI, online order books, online candles, online trades, SuperCandles, Mega Alerts, HI2, market map, website visualizations, API access, the Python library, and a machine-readable calendar. |

Real-time, online, or fully up-to-date data requires a valid bearer token and the relevant entitlement. Public ISS data can be delayed, limited by fields, or unavailable for subscriber-only datasets. Do not promise planned Starter/free-token features as currently available until the user's account or current DataShop terms confirm access.

## Error Diagnosis

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `401` | Missing, malformed, expired, or rejected bearer token | Check `APIKEY`, bearer header, key renewal, and account status |
| `403` on subscription datasets | No valid subscription, no token, wrong host, or endpoint outside plan | Use `apim.moex.com`, set token/header, verify subscription and endpoint coverage |
| `403` with "Too Many Requests" or sudden blocks | Rate or network-protection limit | Slow requests, add backoff, batch by date/ticker, avoid high concurrency |
| `429` | Rate limit | Retry with exponential backoff and reduce concurrency |
| Non-JSON response in library code | Often auth, entitlement, or route mismatch | Inspect status code and headers with a direct request |
| Empty data | No data for date, closed market, unsupported instrument/date, delayed publication, or no entitlement | Check calendar, try a known liquid ticker/date, inspect raw endpoint |

Local wiki notes mention possible blocking around very high request rates, with normal low-rate usage usually fine. Recommend conservative throttling instead of relying on upper limits.

## Product Boundaries

ALGOPACK provides:

- Historical data for research, hypotheses, and backtests.
- Online market data for algorithmic decision systems.
- Analytics such as SuperCandles, FUTOI, HI2, and Mega Alerts.

ALGOPACK does not send exchange orders. For buy, sell, place, cancel, or route-order tasks, direct the user to their broker API or another authorized trading interface.

## Support Escalation

For account-specific subscription checks, payment issues, or key generation failures, direct users to the DataShop personal account and support channels. Local docs list `algopack@moex.com`, `@moex_algopack`, and `@moex_algopack_news` for product/community questions.
