# ISS+ WebSocket and STOMP Concepts

Use this reference for conceptual guidance. Do not promise WebSocket credentials or coverage without checking the user's subscription and current MOEX access process.

## Endpoint and Protocol

Local docs identify ISS+ as a real-time distribution service over WebSocket with STOMP frames:

```text
wss://iss.moex.com/infocx/v3/websocket
```

STOMP client commands:

- `CONNECT`
- `DISCONNECT`
- `SUBSCRIBE`
- `UNSUBSCRIBE`
- `REQUEST`
- `SEND`

Server commands:

- `CONNECTED`
- `ERROR`
- `RECEIPT`
- `MESSAGE`
- `REPLY`
- `CLOSED`

## Authentication Concepts

CONNECT headers include:

- `domain`: local docs mention `DEMO` for guest and `passport` for subscribed users.
- `login`: guest or account login.
- `passcode`: guest or account password.
- `language`: optional, such as `ru` or `en`.

Local community notes in the repo say API keys may not work directly for WebSocket and manual access can be needed. Treat this as account-specific and direct the user to current MOEX/DataShop instructions.

## Subscription and Selector Caveats

- Local Q&A says ISS+ WebSocket access can require a separate manual application or account-linking step; a DataShop API key alone may not authenticate.
- For FORTS selectors, use `FORTS.RFUD.{ticker}` style values after verifying the destination/resource in the `CONNECTED` structure.
- Local notes suggest FORTS WebSocket coverage may expose `candles` and `securities`, while stock coverage may expose `candles`, `securities`, and `orderbook`. Do not promise FORTS orderbook over ISS+ without checking current structure and entitlement.

## Local Python Shape

The repo has `moexalgo.beta.issplus` with:

- `Credentials(domain, login, passcode)`
- `connect(url, credentials)` async context manager
- `ISSPlusSTOMP.request(destination, selector)`
- `ISSPlusSTOMP.subscribe(destination, selector)`
- `ISSPlusSTOMP.unsubscribe(id)`

Skeleton:

```python
import asyncio
from moexalgo.beta.issplus import Credentials, connect

async def main():
    credentials = Credentials(domain="DEMO", login="guest", passcode="guest")
    async with connect("wss://iss.moex.com/infocx/v3/websocket", credentials) as iss:
        print(iss.structure.keys())

asyncio.run(main())
```

## Operational Notes

- Expect binary WebSocket messages containing STOMP frame data.
- Track sequence/order when implementing a low-level client.
- Add small delays between many subscriptions.
- Prefer REST for bulk historical pulls and WebSocket for low-latency current streams.
- Verify available destinations/selectors from the `CONNECTED` structure before subscribing.
