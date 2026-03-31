# Automation Plan: Daily Expenses Fetcher with Nordigen Auth Detection

## Context

This document captures the agreed-upon plan for automating the expenses_fetcher tool to run daily on a Zimaboard running CasaOS.

### Problem Statement

1. **Manual execution**: The tool requires manual triggering, leading to infrequent use
2. **Nordigen 90-day re-auth**: PSD2 regulations require bank re-authorization every 90 days via browser flow
3. **Mixed account types**: Some accounts (Nordigen) can be fully automated, others (xlsx-manual) require human intervention

### Agreed Solution

- **Split workflows**: Automate API-based accounts (Nordigen), keep manual accounts separate
- **Daily cron job**: Run at 8:00 AM on Zimaboard
- **Auth detection**: Detect when Nordigen authorization expires
- **Notifications via ntfy.sh**: Send push notifications when re-auth is needed
- **Skip-and-continue**: On auth failure, skip that account and process others
- **Local network only**: No Tailscale/Cloudflare needed; access onboarding wizard via local IP

### Target Environment

- **Hardware**: Zimaboard
- **OS**: CasaOS (Docker-based)
- **Network**: Home LAN only
- **Notification**: ntfy.sh (free, simple push notifications)

---

## Architecture Overview

```
Zimaboard (CasaOS)
├── Cron (daily 8:00 AM)
│   └── cron_runner.py
│       ├── Load config, filter Nordigen accounts
│       ├── For each account:
│       │   ├── Try: pull → sort → push
│       │   └── Except AuthExpired: notify via ntfy, continue
│       └── Send summary notification
│
├── nordigen_onboarding_web (Flask, port 8787)
│   └── Always running for re-auth when needed
│
└── Google Sheets (external)
    └── Receives transactions and balances
```

### Notification Flow

```
Account auth expired?
    │
    ├─ Yes → Generate bank re-auth link automatically
    │        └── ntfy.sh → Phone notification with clickable bank OAuth URL
    │            └── User taps link → completes bank auth → done!
    │
    └─ No  → Continue processing
```

**Key improvement:** When auth expires, the cron runner automatically generates a direct link to the bank's OAuth page. You can complete re-authorization from anywhere (not just home WiFi) by tapping the link in the notification.

---

## Implementation Steps

### Step 1: Add Nordigen Auth Expiration Exception

**File:** `src/infrastructure/bank_account_transactions_fetchers/exceptions.py`

Add new exception class to detect and handle auth expiration distinctly from other errors.

```python
class NordigenAuthExpiredException(Exception):
    """Raised when Nordigen authorization has expired and needs renewal."""
    def __init__(self, account_id: str, message: str = None):
        self.account_id = account_id
        super().__init__(message or f"Authorization expired for account {account_id}")
```

### Step 2: Detect Auth Expiration in NordigenFetcher

**File:** `src/infrastructure/bank_account_transactions_fetchers/nordigen_fetcher.py`

Modify `getTransactions()` and `get_balance()` to detect expired auth. Nordigen returns specific error patterns:

```json
{"summary": "EUA Expired", "detail": "...", "status_code": 400}
{"status_code": 401, "detail": "Authentication credentials were not provided"}
{"summary": "Account has been suspended", ...}
```

Check for these patterns and raise `NordigenAuthExpiredException` instead of generic errors.

### Step 3: Create Notifier Module

**New file:** `src/infrastructure/notifiers/ntfy_notifier.py`

ntfy.sh integration with timeout and error handling (notification failures should never break the cron job):

```python
import logging
import requests

log = logging.getLogger(__name__)

class NtfyNotifier:
    def __init__(self, topic: str, server: str = "https://ntfy.sh", timeout: int = 10):
        self.topic = topic
        self.server = server.rstrip("/")
        self.timeout = timeout

    def send(self, title: str, message: str, priority: str = "default", tags: list = None):
        url = f"{self.server}/{self.topic}"
        headers = {"Title": title, "Priority": priority}
        if tags:
            headers["Tags"] = ",".join(tags)
        try:
            requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=self.timeout)
        except requests.RequestException as e:
            log.warning(f"Failed to send ntfy notification: {e}")
            # Don't raise - notification failure shouldn't stop the job
```

**Key points:**
- 10 second timeout by default
- Catches all request exceptions (timeout, connection error, etc.)
- Logs warning but doesn't crash - core job (transactions) takes priority

### Step 4: Create Automation Runner Script

**New file:** `automation/cron_runner.py`

Main entry point for automated runs:

1. Parse command-line args (config file path, ntfy topic)
2. Configure logging (see Step 4b below)
3. Load YAML config
4. Filter accounts to `type == "nordigen-account"` only (runtime filter, reuses existing code)
5. For each Nordigen account:
   - Try to pull transactions
   - On `NordigenAuthExpiredException`: record auth failure, continue
   - On other exception: record error, continue
   - On success: stage transactions
6. Try to sort and push all staged transactions to repository
   - On failure: send error notification, abort
7. Send summary notification based on results

### Step 4a: Error Handling and Notifications

**Notification types:**

| Scenario | Priority | Title | Tags |
|----------|----------|-------|------|
| All accounts OK | default | "Daily sync complete" | `white_check_mark` |
| Some auth expired | high | "Sync partial - re-auth needed" | `warning` |
| Google Sheets error | urgent | "Sync failed - Sheets error" | `x` |
| Unexpected error | urgent | "Sync failed - check logs" | `x` |

**Implementation sketch:**

```python
def run_automation(config_path: str, notifier: NtfyNotifier):
    results = {
        "success": [],
        "auth_expired": [],
        "errors": []
    }

    # Pull from each Nordigen account
    for account_name, account in nordigen_accounts.items():
        try:
            transactions = pull_account(account_name, account)
            staged_transactions.extend(transactions)
            results["success"].append(account_name)
        except NordigenAuthExpiredException:
            log.warning(f"Auth expired for {account_name}")
            results["auth_expired"].append(account_name)
        except Exception as e:
            log.error(f"Error pulling {account_name}: {e}")
            results["errors"].append((account_name, str(e)))

    # Push to Google Sheets
    if staged_transactions:
        try:
            push_to_sheets(staged_transactions)
        except Exception as e:
            log.error(f"Failed to push to Google Sheets: {e}")
            notifier.send(
                title="Sync FAILED - Sheets error",
                message=f"Could not push transactions: {e}",
                priority="urgent",
                tags=["x", "rotating_light"]
            )
            return  # Abort, don't send success summary

    # Send summary notification
    send_summary_notification(notifier, results)


def send_summary_notification(notifier: NtfyNotifier, results: dict):
    success_count = len(results["success"])
    auth_count = len(results["auth_expired"])
    error_count = len(results["errors"])

    if auth_count > 0 or error_count > 0:
        # Partial success or failures
        title = "Sync partial" if success_count > 0 else "Sync FAILED"
        priority = "high" if auth_count > 0 else "urgent"
        tags = ["warning"] if auth_count > 0 else ["x"]

        lines = [f"{success_count} accounts OK"]
        if auth_count:
            lines.append(f"{auth_count} need re-auth: {', '.join(results['auth_expired'])}")
        if error_count:
            lines.append(f"{error_count} errors: {', '.join(e[0] for e in results['errors'])}")

        notifier.send(title=title, message="\n".join(lines), priority=priority, tags=tags)
    else:
        # All good
        notifier.send(
            title="Daily sync complete",
            message=f"{success_count} accounts synced",
            priority="default",
            tags=["white_check_mark"]
        )
```

**What you'll see on your phone:**

- All OK: "Daily sync complete - 3 accounts synced"
- Auth issue: "Sync partial - re-auth needed" → "2 accounts OK, 1 need re-auth: Revolut"
- Sheets error: "Sync FAILED - Sheets error" → "Could not push transactions: 403 Forbidden"

### Step 4b: Logging Strategy

**In `automation/cron_runner.py`:**

Log to both stdout (for `docker logs`) and a persistent file:

```python
import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logging(log_dir: str = "/app/logs"):
    os.makedirs(log_dir, exist_ok=True)

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Console handler (stdout - captured by docker logs)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    # File handler with rotation (10MB max, keep 5 backups)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "cron_runner.log"),
        maxBytes=10*1024*1024,
        backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(file_handler)
```

**Key points:**
- Logs to stdout → viewable via `docker logs expenses-fetcher-cron`
- Logs to file → persists in mounted volume for debugging
- Rotation prevents disk fill (10MB × 5 = 50MB max)
- Includes timestamps for correlating with auth failures

### Step 4c: Google Sheets Authentication

The existing `GoogleSheetRepository` uses OAuth with automatic token refresh. For automation:

**How it works:**
- First run requires interactive OAuth
- Token saved to `token.pickle` (contains access + refresh token)
- Subsequent runs auto-refresh the token - no interaction needed
- Google refresh tokens don't expire unless revoked
- A headless cron container cannot bootstrap a missing token by itself; it must receive a valid `token.pickle`

**Setup (one-time, before deploying to Zimaboard):**
1. Run the tool locally/interactively once:
   ```bash
   python main.py --config-file config/your_config.yaml
   ```
2. Complete OAuth flow in browser
3. Copy the generated `token.pickle` to your Zimaboard config directory

**Docker volume mapping:**
```yaml
volumes:
  - ./data:/app/data  # token.pickle lives here
```

**In config.yaml:**
```yaml
repositories:
  googlesheet:
    token_cache_path: "/app/data/token.pickle"
    credentials_path: "/app/config/credentials.json"
```

**Note:** If token ever gets revoked (e.g., you revoke access in Google Account settings), you'll need to re-run interactive auth and copy the new token.pickle.

### Step 4d: Automatic Re-Auth Link Generation

When Nordigen authorization expires, the cron runner automatically generates a direct link to the bank's OAuth page and sends it via ntfy. This allows you to complete re-authorization from anywhere (not just home WiFi).

**How it works:**

1. When `NordigenAuthExpiredException` is caught, the runner:
   - Gets `secret_id`, `secret_key`, and `account` from the account config
   - Resolves environment variables (e.g., `${NORDIGEN_SECRET_ID}`)
   - Fetches a fresh Nordigen access token
   - Gets the `institution_id` from the account details API
   - Creates a new end-user agreement (90 days)
   - Creates a requisition with redirect to `https://www.google.com`
   - Extracts the bank OAuth link from the requisition response

2. Sends an ntfy notification with the clickable bank link

**What you receive on your phone:**

```
Title: "Re-auth needed: RevolutAccount"
Message: "Tap to authorize:
https://ob.nordigen.com/psd2/start/xxx/REVOLUT_REVOLT21"
```

**Mobile workflow:**

1. Tap the notification
2. Bank OAuth page opens in browser
3. Complete authorization (login, approve access)
4. Redirected to google.com (you can close the tab)
5. Done! Next cron run will sync successfully

**Why redirect to google.com?**

- The account ID typically stays the same after re-auth (observed over 1+ year)
- We don't need to capture the callback - just completing the OAuth flow is enough
- This allows re-auth from anywhere, not just home WiFi where the Flask app runs

**If account ID changes (rare):**

You'll notice transactions aren't syncing. Manually update the `account` field in your config with the new ID from the Nordigen dashboard or by running the onboarding wizard.

### Step 5: Create Dockerfile

**New file:** `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# No default CMD - specified at runtime for different services
```

### Step 6: Create Docker Compose

**New file:** `docker-compose.yml`

```yaml
version: "3.8"
services:
  # Main cron job runner (triggered externally or via sleep loop)
  expenses-fetcher-cron:
    build: .
    environment:
      - CONFIG_FILE=/app/config/config.yaml
      - NTFY_TOPIC=${NTFY_TOPIC}
      - NORDIGEN_SECRET_ID=${NORDIGEN_SECRET_ID}
      - NORDIGEN_SECRET_KEY=${NORDIGEN_SECRET_KEY}
    volumes:
      - ./config:/app/config
      - ./data:/app/data
      - ./logs:/app/logs  # Persistent logs for debugging
    command: python automation/cron_runner.py --config-file /app/config/config.yaml

  # Onboarding wizard - always running
  nordigen-onboarding:
    build: .
    ports:
      - "8787:8787"
    environment:
      - CONFIG_FILE=/app/config/config.yaml
    volumes:
      - ./config:/app/config
    command: python tools/nordigen_onboarding_web/app.py --config-file /app/config/config.yaml --port 8787
    restart: unless-stopped
```

---

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `src/infrastructure/bank_account_transactions_fetchers/exceptions.py` | Modify | Add `NordigenAuthExpiredException` |
| `src/infrastructure/bank_account_transactions_fetchers/nordigen_fetcher.py` | Modify | Detect auth expiration, raise custom exception |
| `src/infrastructure/notifiers/__init__.py` | Create | Module init |
| `src/infrastructure/notifiers/ntfy_notifier.py` | Create | ntfy.sh integration |
| `automation/__init__.py` | Create | Module init |
| `automation/cron_runner.py` | Create | Main automation script |
| `Dockerfile` | Create | Container definition |
| `docker-compose.yml` | Create | Service orchestration |

---

## Deployment Instructions

### On Zimaboard (CasaOS)

1. **Clone/copy repo** to Zimaboard

2. **Create config directory** with your `config.yaml`

3. **Create `.env` file:**
   ```bash
   NORDIGEN_SECRET_ID=your_secret_id
   NORDIGEN_SECRET_KEY=your_secret_key
   NTFY_TOPIC=my-expenses-fetcher
   ```

4. **Ensure credentials are in place:**
   ```
   expenses_fetcher/
   ├── config/
   │   ├── config.yaml          # Your configuration
   │   └── credentials.json     # Google OAuth client credentials
   ├── data/
   │   └── token.pickle         # Google OAuth token (after first auth)
   └── logs/                    # Created automatically
   ```

   **Important:** `credentials.json` must be in the `config/` directory (mapped to `/app/config` in Docker). This is the OAuth client file downloaded from Google Cloud Console, NOT the token.

5. **Start services:**
   ```bash
   docker-compose up -d nordigen-onboarding
   ```

6. **Set up cron job** (system crontab or CasaOS scheduler):
   ```bash
   0 8 * * * cd /path/to/expenses_fetcher && docker-compose run --rm expenses-fetcher-cron
   ```

7. **Install ntfy app** on phone, subscribe to your topic

8. **Test:** Run manually to verify:
   ```bash
   docker-compose run --rm expenses-fetcher-cron
   ```

---

## Key Codebase References

Understanding these files is essential for implementation:

| File | Purpose |
|------|---------|
| `main.py` | Entry point, `build_expense_fetcher()` creates the fetcher from config |
| `do_pull_sort_push.py` | Simple example of non-interactive pull/sort/push flow |
| `src/application/expenses_fetcher/expenses_fetcher.py` | Core `ExpensesFetcher` class with `pull_transactions()`, `push_transactions()` |
| `src/infrastructure/bank_account_transactions_fetchers/nordigen_fetcher.py` | Nordigen API client, where auth errors occur |
| `src/service/configuration/configuration_parser.py` | Parses YAML config, maps `type: nordigen-account` to `NordigenAccountManager` |
| `tools/nordigen_onboarding_web/app.py` | Flask wizard for Nordigen re-authorization |

---

## Testing Checklist

- [ ] Unit test: `NordigenAuthExpiredException` raised on mock expired auth response
- [ ] Unit test: `NtfyNotifier.send()` with mocked requests
- [ ] Integration test: `cron_runner.py` with one valid, one expired account
- [ ] End-to-end: Docker build and run locally
- [ ] Manual test: Trigger ntfy notification, verify phone receives it

---

## Step 7: Google Apps Script Web App for Mobile

Since Google Sheets mobile app doesn't support script buttons, deploy your existing "move to Expenses" script as a web app.

### In Google Apps Script Editor

Add a `doGet` function to your existing script with token-based authentication:

```javascript
function doGet(e) {
  var token = e.parameter.token;
  if (token !== "YOUR_SECRET_TOKEN_HERE") {
    return ContentService.createTextOutput("Unauthorized");
  }
  submitTransactions(); // your existing function name
  return ContentService.createTextOutput("Transactions submitted!");
}
```

Replace `YOUR_SECRET_TOKEN_HERE` with a secure random string (e.g., `xK9m2Pq7Rz`).

### Deploy as Web App

1. In Script Editor: **Deploy → New deployment**
2. Type: **Web app**
3. Execute as: **Me**
4. Who has access: **Anyone** (the token provides security)
5. Click **Deploy**, copy the URL

### Security Note

Setting "Anyone" sounds open, but the secret token in the URL acts as your password:
- The full URL (including `?token=...`) is encrypted via HTTPS
- Network snoopers can only see you're connecting to `script.google.com`, not the token
- Only someone with the full URL can execute the script

### iOS Shortcut Setup (Recommended)

This gives you a home screen icon that runs the script without opening a browser:

1. Open **Shortcuts** app on iOS
2. Create new Shortcut
3. Add action: **Get Contents of URL**
   - URL: `https://script.google.com/macros/s/.../exec?token=YOUR_SECRET_TOKEN_HERE`
4. Add action: **Show Notification**
   - Set notification body to the output from previous step (Contents of URL)
5. Tap Shortcut name → **Add to Home Screen**
6. Name it "Submit Expenses" and choose an icon

### Usage (Mobile Workflow)

1. Receive ntfy notification "Daily sync complete"
2. Open Google Sheets app, review Expenses Staging, fill in categories
3. Tap your "Submit Expenses" home screen icon
4. See notification: "Transactions submitted!"

### Alternative: Chrome on iOS

If you prefer using a browser instead of Shortcuts:
- Safari on iOS may redirect `script.google.com` to Google Drive app (broken)
- Use **Chrome on iOS** instead - it handles the URL correctly
- You can create a Shortcut that opens Chrome with the URL: `googlechrome://script.google.com/macros/s/.../exec?token=YOUR_SECRET_TOKEN_HERE`

**Note:** The URL with token is never sent through ntfy - keep it private.

---

## Future Enhancements (Out of Scope)

- Telegram bot as alternative to ntfy
- Email notifications
- Web dashboard for status monitoring
- Support for other account types (MyEdenred, ActivoBank) in automation
- Remote access via Tailscale if needed later

---

*Document created: January 2025*
*Status: Agreed plan, ready for implementation*
