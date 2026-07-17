[简体中文](README.zh-CN.md)

# sub2API Subscription for Home Assistant

Sync subscription quotas from a [sub2API](https://github.com/Wei-Shaw/sub2api)
account to Home Assistant and use the data in sensors, Lovelace cards, history,
and automations.

This integration exposes:

- Daily usage and daily quota
- Weekly usage and weekly quota
- The next daily and weekly reset times
- Remaining quota and usage percentage
- Today's and cumulative token usage
- Separate devices and sensors for multiple active subscriptions

> [!IMPORTANT]
> This integration supports email/password login and manually supplied web
> session tokens. An API key intended for model requests cannot access these
> endpoints. Never commit passwords or tokens to GitHub, send them in chat, or
> include them in public logs.

## Table of contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Authentication methods](#authentication-methods)
- [Adding the integration](#adding-the-integration)
- [Entities](#entities)
- [Creating a Lovelace dashboard card](#creating-a-lovelace-dashboard-card)
- [Quota reset notifications](#quota-reset-notifications)
- [Token refresh and reauthentication](#token-refresh-and-reauthentication)
- [Updating and uninstalling](#updating-and-uninstalling)
- [Troubleshooting](#troubleshooting)
- [Repository structure](#repository-structure)
- [Development](#development)

## How it works

Every five minutes, the integration calls the authenticated sub2API
subscription and dashboard endpoints:

```text
GET /api/v1/subscriptions/progress
GET /api/v1/usage/dashboard/stats
```

The data flow is:

```text
sub2API subscription endpoint
              |
              v
sub2API Subscription integration
              |
              v
Daily, weekly, and token sensors
              |
              v
Lovelace cards, history, and automations
```

The integration discovers every active subscription belonging to the
configured account. Each subscription becomes a Home Assistant device, with
sensors created for the quota windows available on that subscription. New
subscriptions are discovered automatically. If a subscription expires or
disappears, its registered entities remain in Home Assistant but become
unavailable.

## Requirements

Before installing, make sure that:

- Home Assistant is **2025.1.0 or newer**
- The Home Assistant host can reach the sub2API site over HTTPS
- You can sign in to the target sub2API account in a browser
- You can access the Home Assistant `/config` directory, or HACS is installed

If Home Assistant and sub2API run on different machines, test DNS resolution
and HTTPS access from the Home Assistant host. A reverse proxy, firewall, or
DNS configuration can allow browser access while still blocking Home
Assistant.

## Installation

Choose either HACS or manual installation.

### Option 1: HACS

Add this GitHub repository as a HACS custom repository:

1. Open **HACS** in Home Assistant.
2. Open **Integrations**.
3. Open the menu in the upper-right corner and select **Custom repositories**.
4. Enter this repository's GitHub URL.
5. Select **Integration** as the category and add the repository.
6. Find and download **sub2API Subscription**.
7. Fully restart Home Assistant.

HACS installs from GitHub. It cannot install directly from a local directory
on another computer.

### Option 2: Manual installation

Copy the entire `custom_components/sub2api` directory from this repository to
the Home Assistant configuration directory. The final layout must be:

```text
/config/
└── custom_components/
    └── sub2api/
        ├── __init__.py
        ├── api.py
        ├── config_flow.py
        ├── const.py
        ├── coordinator.py
        ├── manifest.json
        ├── models.py
        ├── sensor.py
        ├── strings.json
        └── translations/
```

#### Home Assistant OS or Supervised

Use the Samba share, Studio Code Server, or Terminal & SSH add-on to copy the
directory to:

```text
/config/custom_components/sub2api
```

#### Home Assistant Container

Find the host directory mounted as `/config`. For example, if the container
was started with:

```text
-v /opt/homeassistant/config:/config
```

copy the integration to:

```text
/opt/homeassistant/config/custom_components/sub2api
```

Do not copy it only into the container's temporary filesystem. It would be
lost when the container is recreated.

#### Home Assistant Core

Copy the integration to `custom_components/sub2api` under the directory that
contains `configuration.yaml`.

After copying the files, fully restart Home Assistant. Reloading YAML alone
does not load a new custom integration.

> [!WARNING]
> A common installation mistake is adding an extra directory level. The
> correct path is `/config/custom_components/sub2api/manifest.json`, not
> `/config/custom_components/sub2api/custom_components/sub2api/manifest.json`.

## Authentication methods

### Email and password

This is the recommended method for a normal local sub2API account. Home
Assistant signs in through `POST /api/v1/auth/login`, stores the email,
password, and returned token pair, then uses token refresh for routine
operation.

If the account has TOTP two-factor authentication enabled, setup asks for the
current six-digit authenticator code. The code and temporary 2FA session are
used once and are never stored. When a future login requires TOTP again, Home
Assistant opens a reauthentication flow for a new code.

The password is stored in Home Assistant's config entry storage so the
integration can recover automatically when a refresh token is rejected.
Home Assistant config storage is not a dedicated encrypted password vault.
Use this mode only when the Home Assistant host and its backups are trusted.

Password login cannot complete Cloudflare Turnstile, OAuth, CAPTCHA, or other
interactive browser challenges. Use manual tokens for those sites.

### Manual tokens

Manual tokens support sites that use Turnstile, OAuth, CAPTCHA, or another
complex login flow. In Chrome or Edge:

1. Sign in to the target sub2API site.
2. Press `F12` to open Developer Tools.
3. Open **Application**.
4. Expand **Local Storage**.
5. Select the current sub2API site.
6. Copy the value of `auth_token`.
7. Copy the value of `refresh_token`.

In Firefox, use **Storage** > **Local Storage**.

- Copy only the values, without the field names.
- Do not use a model API key.
- Both tokens must come from the same site and account.
- Prefer a dedicated private browsing session, then close it without signing
  out after Home Assistant has been configured.
- Do not keep another browser using the same refresh token active. sub2API
  rotates refresh tokens, so the first client to refresh invalidates the
  other client's copy.

> [!WARNING]
> Current sub2API versions enable IP and User-Agent session binding by default.
> A browser token may be rejected when Home Assistant on another machine
> refreshes it. Email/password mode avoids this mismatch by creating the
> session directly from Home Assistant. For manual tokens, the site
> administrator may need to disable session IP/UA binding.

## Adding the integration

After installation and a full Home Assistant restart:

1. Open **Settings** > **Devices & services**.
2. Select **Add integration**.
3. Search for **sub2API Subscription**.
4. Enter the base URL of the sub2API site.
5. Choose **Email and password** or **Manual access and refresh tokens**.
6. Enter the requested credentials or tokens.
7. If prompted, enter the current six-digit TOTP code.
8. Submit the form.

Use the site root as the base URL:

```text
https://sub2api.example.com
```

The following form also works; the integration removes the trailing
`/api/v1` automatically:

```text
https://sub2api.example.com/api/v1
```

For token security, only HTTPS URLs are accepted.

After setup, the integration page displays the account and every discovered
subscription device. Different users on the same site and accounts on
different sub2API sites can be added separately. The same user on the same
site cannot be added twice.

To switch authentication methods later, open **Settings** >
**Devices & services**, open the menu for the sub2API config entry, and select
**Reconfigure**. Replacement credentials or tokens must resolve to the same
user ID.

## Entities

Each subscription creates up to six quota sensors. A group is omitted when
that subscription has no corresponding quota window. The integration also
creates an account device containing two token sensors.

| Sensor | State | Unit | Main attributes |
|---|---|---|---|
| Daily used | Amount used in the current daily window | USD | `remaining_usd`, `percentage`, `window_start` |
| Daily limit | Daily quota limit | USD | Subscription and group information |
| Daily reset | Next daily reset | Timestamp | `resets_in_seconds` |
| Weekly used | Amount used in the current weekly window | USD | `remaining_usd`, `percentage`, `window_start` |
| Weekly limit | Weekly quota limit | USD | Subscription and group information |
| Weekly reset | Next weekly reset | Timestamp | `resets_in_seconds` |
| Today tokens | Tokens used today | tokens | Input, output, cache creation, and cache read tokens |
| Total tokens | Cumulative tokens used by the account | tokens | Input, output, cache creation, and cache read tokens |

Home Assistant generates entity IDs from subscription names, so IDs differ
between installations. The `sensor.codex_subscription_*` IDs in this
repository are placeholders.

To find the actual IDs:

1. Open **Developer tools** > **States**.
2. Search for `daily_used`, `daily_limit`, `daily_reset`,
   `weekly_used`, `weekly_limit`, `weekly_reset`, `today_tokens`, or
   `total_tokens`.
3. Alternatively, open the subscription device under **Settings** >
   **Devices & services** > **sub2API Subscription**.

If a quota exists but its window has not started, the used and limit sensors
can still have values while the reset sensor is temporarily unavailable.

The main state of each token sensor is the unformatted integer returned by
sub2API. Home Assistant can display large values in a compact form such as
`3.0M`. The following attributes are also available:

```text
input_tokens
output_tokens
cache_creation_tokens
cache_read_tokens
```

## Creating a Lovelace dashboard card

Lovelace is the traditional name for Home Assistant's dashboard system. The
integration provides entities; Lovelace cards display them.

### Built-in Entities card

No frontend extension is required for an Entities card. Edit a dashboard, add
a **Manual** card, and replace the placeholder entity IDs:

```yaml
type: entities
title: sub2API Quota
entities:
  - entity: sensor.codex_subscription_daily_used
    name: Daily used
  - entity: sensor.codex_subscription_daily_limit
    name: Daily limit
  - entity: sensor.codex_subscription_daily_reset
    name: Daily reset
  - entity: sensor.codex_subscription_weekly_used
    name: Weekly used
  - entity: sensor.codex_subscription_weekly_limit
    name: Weekly limit
  - entity: sensor.codex_subscription_weekly_reset
    name: Weekly reset
  - entity: sensor.sub2api_account_today_tokens
    name: Today tokens
  - entity: sensor.sub2api_account_total_tokens
    name: Total tokens
```

### sub2API-style progress card

This repository includes a card styled after the sub2API quota display:

[`lovelace/sub2api-quota-card.yaml`](lovelace/sub2api-quota-card.yaml)

It displays:

- Subscription name, platform, and availability
- Daily and weekly usage and limits
- Progress bar colors based on usage percentage
- Live countdowns to the next resets
- Home Assistant light and dark theme support

The card requires the HACS frontend extension
[`button-card`](https://github.com/custom-cards/button-card):

1. Open **HACS** > **Frontend**.
2. Find and install **button-card**.
3. Reload the browser or restart Home Assistant as instructed by HACS.
4. Open `lovelace/sub2api-quota-card.yaml`.
5. Replace the six entity IDs at the top of the file.
6. Optionally change `fallback_title`.
7. Add a **Manual** dashboard card and paste the entire YAML file.

The values that need editing are grouped at the top:

```yaml
variables:
  daily_used: sensor.codex_subscription_daily_used
  daily_limit: sensor.codex_subscription_daily_limit
  daily_reset: sensor.codex_subscription_daily_reset
  weekly_used: sensor.codex_subscription_weekly_used
  weekly_limit: sensor.codex_subscription_weekly_limit
  weekly_reset: sensor.codex_subscription_weekly_reset
  fallback_title: Codex Subscription
```

For multiple subscriptions, create one copy of the card per subscription and
use the matching entity IDs in each card.

If the dashboard reports `Custom element doesn't exist: button-card`, verify
that button-card is installed, that its HACS resource is loaded, and then
force-refresh the browser.

## Quota reset notifications

The repository includes a mobile notification automation:

[`automations/sub2api-quota-reset-notification.yaml`](automations/sub2api-quota-reset-notification.yaml)

It monitors daily and weekly usage. When usage changes directly from a value
greater than zero to zero while the recorded reset time is still in the
future or temporarily unavailable, it sends a mobile notification. It ignores
`unknown`, `unavailable`, and invalid transitions during Home Assistant
startup.

### Prepare the mobile notification action

1. Install the Home Assistant Companion App on the phone.
2. Connect the app to this Home Assistant instance.
3. Open **Developer tools** > **Actions**.
4. Search for `notify.mobile_app_`.
5. Note the complete action name, for example:

```text
notify.mobile_app_your_phone
```

### Add the automation

1. Open **Settings** > **Automations & scenes**.
2. Create an empty automation.
3. Open the menu and select **Edit in YAML**.
4. Paste the complete notification YAML file.
5. Replace the six `sensor.codex_subscription_*` entity IDs.
6. Replace `notify.mobile_app_your_phone` with the phone's notification
   action.
7. Save and enable the automation.

The automation uses `queued` mode. If daily and weekly usage both reset in
one update, both notifications are queued instead of one being discarded.

Do not test it with **Run actions**. Its message depends on
`trigger.from_state` and `trigger.to_state`, which are not present when the
actions are run manually.

## Token refresh and reauthentication

Default sub2API settings typically use:

- An access token valid for about 24 hours
- A refresh token valid for about 30 days

Third-party sites can change these values. An access token lifetime of two
hours, for example, is a valid server-side configuration.

When an access token receives HTTP 401, the integration uses the refresh token
to obtain and persist a rotated token pair, then retries the original request.

In email/password mode, a refresh token explicitly rejected by sub2API causes
one password login attempt:

- Without TOTP, the new token pair is saved automatically.
- With TOTP, Home Assistant requests a current six-digit code.
- Invalid credentials or an interactive browser challenge starts
  reauthentication, where manual tokens can be selected instead.

Network failures, rate limits, and server errors never trigger password login.

Home Assistant starts a reauthentication flow when the refresh token cannot
be used. Common causes include:

- The refresh token expired or was revoked
- A browser already used and rotated the same refresh token
- sub2API session IP/User-Agent binding rejected the Home Assistant request
- The password changed or the site revoked the session
- The site runs in backend mode and blocks refresh for non-admin users
- The refresh-token cache was cleared during a server restart
- The site changed its authentication or security policy

During reauthentication or a user-initiated **Reconfigure** flow, the
authentication method can be changed. Home Assistant verifies that the new
credentials or tokens still belong to the same sub2API user before replacing
the saved configuration.

## Updating and uninstalling

### Update through HACS

Install the update in HACS, then restart Home Assistant when prompted.

### Manual update

Replace the complete `/config/custom_components/sub2api` directory with the
new version. Do not update only one Python file. Restart Home Assistant after
copying.

### Uninstall

1. Remove the **sub2API Subscription** config entry under **Settings** >
   **Devices & services**.
2. Uninstall it through HACS, or delete
   `/config/custom_components/sub2api`.
3. Restart Home Assistant.
4. Remove any Lovelace cards and automations that are no longer needed.

## Troubleshooting

### The integration does not appear in the Add Integration dialog

- Verify that `manifest.json` is located at
  `/config/custom_components/sub2api/manifest.json`.
- Make sure there is no extra directory level.
- Fully restart Home Assistant.
- Check **Settings** > **System** > **Logs** for custom integration errors.

### Home Assistant cannot connect to the sub2API site

- Make sure the URL uses HTTPS.
- Test access from the Home Assistant host, not only from a desktop browser.
- Check DNS, firewall, reverse proxy, and TLS certificate settings.
- Do not append unrelated login-page paths to the base URL.

### The access or refresh token is rejected

- Sign in again and obtain a new matching token pair.
- Check for copied quotes, spaces, or field names.
- Confirm that both tokens belong to the same site and account.
- Do not use a model API key.
- Check whether session IP/User-Agent binding is enabled on the sub2API site.
- Do not use one rotating refresh token in both a browser and Home Assistant.

### Email/password login is rejected

- Confirm that the login uses the account email address, not the display name.
- Verify the password by signing in to the sub2API site.
- If the site shows Turnstile, CAPTCHA, OAuth, or another interactive
  challenge, choose manual tokens instead.
- If TOTP is enabled, enter the current six-digit code when prompted.

### The integration worked until the access token expired

This usually means that normal API requests succeeded but token refresh was
rejected. Check the sub2API server logs for:

```text
SESSION_BINDING_MISMATCH
REFRESH_TOKEN_INVALID
Refresh token not found
possible reuse attack
```

If session binding is enabled, a token copied from a browser may not be
refreshable by Home Assistant on another machine. If the same browser page
remained active, it may also have rotated the refresh token before Home
Assistant.

### Setup succeeds but no subscription device appears

- Verify that the account has an active subscription.
- Verify that the subscription is not expired.
- Open the sub2API subscription page and confirm that it displays quota data.

### Only daily or only weekly entities appear

This is expected. The integration creates sensors only for quota windows
configured on that subscription.

### A reset-time sensor is unavailable

The quota window may not have started. sub2API normally sets the window start
and reset time after the subscription first records usage.

### The Lovelace card does not update

- Check all six entity IDs at the top of the YAML.
- Verify in Developer Tools that the entities themselves are updating.
- Confirm that button-card is installed and loaded.
- Force-refresh the browser or clear the Home Assistant frontend cache.

### The phone does not receive notifications

- Confirm that the Companion App is signed in and has notification permission.
- Test the `notify.mobile_app_*` action in Developer Tools.
- Check that the automation is enabled and inspect its traces.
- Confirm that usage changed directly from a value greater than zero to zero.

### Are monthly quotas or subscription-expiration entities supported?

Version `0.3.0` creates daily and weekly quota entities plus today's and
cumulative token entities. Monthly quota, subscription status, and
expiration-time entities are not currently exposed as separate sensors.

### Can multiple accounts or sites be added?

Yes. Different users on one site and accounts on different sub2API sites can
be configured separately. The site, user, and subscription IDs are combined
into stable unique IDs to avoid entity collisions.

## Data and security

- Access and refresh tokens are stored in the Home Assistant config entry.
- Email and password are also stored when credential mode is selected.
- Password, token, and TOTP fields use password inputs and are never
  intentionally logged.
- TOTP codes, TOTP secrets, and temporary 2FA sessions are never stored.
- Home Assistant config entries are not a dedicated encrypted secret vault;
  protect the host and all backups that contain `/config/.storage`.
- Only HTTPS endpoints are accepted.
- Monetary values retain the USD unit returned by sub2API.
- Repository URLs, entity IDs, usernames, and notification actions are
  placeholders.
- No example YAML contains real tokens.

## Repository structure

```text
.
├── custom_components/
│   └── sub2api/                       # Home Assistant custom integration
├── lovelace/
│   └── sub2api-quota-card.yaml        # Optional quota progress card
├── automations/
│   └── sub2api-quota-reset-notification.yaml
│                                       # Optional reset notification
├── tests/                              # Automated tests
├── hacs.json                           # HACS metadata
├── pyproject.toml                      # Development and test configuration
├── README.md                           # English documentation
└── README.zh-CN.md                     # Simplified Chinese documentation
```

Only `custom_components/sub2api` is required to install the integration. The
`lovelace` and `automations` directories contain optional examples and are
not loaded automatically.

## Development

Create a Python 3.12 virtual environment, then run:

```bash
python -m pip install -e ".[test]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

The tests cover:

- API parsing and malformed responses
- Access-token expiration and refresh-token rotation
- Password login, manual tokens, TOTP, and refresh fallback
- Configuration migration, duplicate accounts, and reauthentication
- Daily and weekly sensor creation
- Today and cumulative token sensors and component attributes
- Dynamic discovery of subscriptions and quota windows
- Unavailable entities for removed subscriptions
- Home Assistant reauthentication after authentication failure

GitHub Actions also run the unit tests, Ruff, HACS validation, and hassfest.

## Upstream project

This integration depends on the user subscription endpoints provided by
sub2API:

- [Wei-Shaw/sub2api](https://github.com/Wei-Shaw/sub2api)

This repository is not an official sub2API Home Assistant integration.

---

[![Buy Me a Coffee](https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png)](https://www.buymeacoffee.com/dreamxiaohai)
