<p align="center"><img src="custom_components/domo/brand/logo@2x.png" alt="DOMO" height="64"></p>

**English** | [Русский](README.ru.md) | [Oʻzbekcha](README.uz.md)

# DOMO for Home Assistant

Balances and usage for every utility account in the [DOMO](https://domo.uz) app (Hududgaz): natural gas, electricity, water, garbage collection, "Mening uyim" and the rest.

This is an unofficial integration and is not affiliated with DOMO or Hududgaz.

## How it logs in

DOMO has no password. You enter the phone number registered in the app, and DOMO sends you an SMS code. You enter the code once, and after that the integration keeps itself logged in:

- The access token lives 7 days. It is refreshed a day before it expires.
- The refresh token lives 365 days. Every refresh renews it, so the session doesn't run out while Home Assistant keeps running.
- If DOMO ever ends the session, Home Assistant shows a reauthentication notice. Submit it to get a new SMS code.

Home Assistant appears as **Home Assistant** in the app's list of active sessions. Your phone stays logged in.

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/dilshodm/ha-domo`, category **Integration**.
2. Install **DOMO** and restart Home Assistant.

### Manual

Copy `custom_components/domo` into your `config/custom_components` folder and restart Home Assistant.

### Setup

**Settings → Devices & services → Add integration → DOMO**. Enter your phone number, then the SMS code.

## Entities

Each utility account becomes a device named after the service and the account number, e.g. "Газ 1007090145". The device's model field shows the home's name or address.

| Sensor | Accounts | Notes |
|---|---|---|
| Balance | all | UZS, as DOMO reports it (positive = credit) |
| Meter reading | gas, electricity | m³ / kWh, `total_increasing`, works in the Energy dashboard |
| Reading date | metered | time of the latest meter reading |
| Usage this month | gas, electricity | m³ / kWh |
| Charge this month | accounts DOMO analyses | UZS; `previous_month` attribute |
| Last day usage / charge | gas, electricity | most recent day from DOMO's daily stats; `date` attribute |
| Updated | all | diagnostic: when DOMO last synced the account |

The login itself is a device too (**DOMO +998…**) with a **Refresh data** button. Pressing it asks DOMO to re-sync every account with its provider (like pull-to-refresh in the app) and then fetches the result, without waiting for the next poll. After a successful refresh, the button can be pressed again after one minute.

### New accounts

When you add a service or a home in the DOMO app, its devices and sensors appear in Home Assistant at the next poll. Press **Refresh data** to pick them up right away. If an account is removed in DOMO, its sensors become unavailable, and you can delete the device from its device page.

## Options

**Settings → Devices & services → DOMO → Configure**:

- **Polling interval**: 1–24 hours, default 3. DOMO itself updates usage about once a day.
- **Language**: Русский, Oʻzbekcha or English. It sets the language DOMO answers in and the device names ("Газ / Gaz / Gas 1007090145"). It is also asked during setup, where it defaults to Home Assistant's language. Sensor names follow Home Assistant's own language, as usual.

## Privacy

Your phone number and the DOMO tokens are stored only in Home Assistant's config entry. They are used to talk to `domo-gw.uz` and are sent nowhere else.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

The API notes below come from the DOMO Android app 2.2.8.

- **Base URL:** `https://domo-gw.uz/api/v1/`.
- **Device headers on every call:** `Device-Id`, `Platform`, `Device-OS`, `Device-Model`, `App-Version`, `User-Agent`, `Accept-Language`.
- **Login:**
  1. `verification/RequestOTP` `{purpose: "login", address, client_secret}`
  2. `verification/SubmitOTP` `{session, otp, client_secret}`
  3. `accounts/Login` `{session_data, verification_data}` returns `{access, refresh}`
- **Refresh:** `accounts/RefreshToken` `{refresh}` returns a new pair.
- **Data:** `home/HomeList` (all homes with every service account), `{service}/DailyUsageStats?account=&year=&month=` and `{service}/MonthlyUsageStats?account=&year=`.
