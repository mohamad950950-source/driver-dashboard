# Driver Dashboard — Cloud Review Document

## 📦 Project Overview

| Item | Detail |
|------|--------|
| **Name** | Driver Revenue Dashboard |
| **Backend** | FastAPI + Jinja2 (Python 3.11) |
| **Database** | SQLite (`data/driver.db`) |
| **Auth** | Owner: plate_number + phone / Driver: phone + OTP |
| **Frontend (old)** | Jinja2 templates with Apple-style dark UI |
| **Frontend (new)** | React + shadcn/ui at `/frontend` (Vite, port 5173) |
| **Port** | `http://localhost:8000` |
| **Theme** | `#000` bg, `#0071e3` accent, `#1c1c1e` cards |

## 📂 File Structure

```
driver-dashboard/
├── app.py                 ← Backend (1717 lines, ALL logic here)
├── run_daemon.py          ← Background daemon with auto-restart
├── install_permanent.bat  ← Windows Startup registration
├── run_hidden.vbs         ← VBS launcher (no window)
├── start.bat              ← Simple launcher
├── stop_server.bat        ← Kill all
├── translations.py        ← Arabic/English dict (228 keys)
├── requirements.txt       ← Python deps
├── data/driver.db         ← SQLite database
├── uploads/               ← Driver document photos
├── static/                ← Static files (CSS, loading.html)
├── templates/             ← Jinja2 HTML pages (12 files)
│   ├── base.html
│   ├── login.html         ← **NEEDS REWRITE** (see below)
│   ├── driver_connect.html
│   ├── driver_dashboard.html
│   ├── owner_dashboard.html
│   ├── drivers.html
│   ├── accounts.html
│   ├── fuel.html, trips.html, expenses.html, maintenance.html, reports.html
│   ├── settings.html, verify.html
│   ├── mobile_nav.html
│   └── oauth_*.html (3 files)
├── frontend/              ← React + shadcn/ui (separate SPA)
│   ├── src/App.jsx
│   ├── src/components/ui/ (button, card, dialog, table)
│   ├── vite.config.js (proxy :8000)
│   └── netlify.toml
```

---

## 🔐 AUTH SYSTEM — THE BROKEN PART

### What the Backend Expects

| Endpoint | Method | Input | Output |
|----------|--------|-------|--------|
| `/api/auth/owner-login` | POST | `{"plate":"ABC123","phone":"01000000001"}` | Session cookie + user object |
| `/api/auth/request-otp` | POST | `{"phone":"01009998877"}` | `{"otp":"1234","expires_in":300}` |
| `/api/auth/verify-otp` | POST | `{"phone":"01009998877","code":"1234"}` | Session cookie + user object |
| `/api/auth/dev-login` | POST | `{"role":"owner/driver"}` | Session cookie (DEBUG only) |
| `/api/auth/logout` | POST | (cookie) | Clears session |
| `/api/auth/me` | GET | (cookie) | `{"authenticated":true/false}` |

### The BUG

The file **`templates/login.html`** (line 75) calls:

```javascript
fetch('/api/auth/'+(m==='login'?'login':'register'), {
  body: JSON.stringify({username:p, email:p+'@d.driver', password:pw, role:r})
})
```

**But there is NO `/api/auth/login` or `/api/auth/register` endpoint anymore!** They were replaced by the OTP system. The login page is completely disconnected from the backend.

### What I Already Fixed

I rewrote `templates/login.html` with the correct flow:

1. **Step 1**: Choose role (Driver / Owner)
   - **Driver**: Enter phone → click "Send OTP code"
   - **Owner**: Enter phone + plate_number → click "Login"

2. **Step 2** (driver only): Enter 4-digit OTP code with 4 separate input boxes
   - Auto-submits when all 4 digits entered
   - Shows the OTP code in-app (will be SMS later)
   - 5-minute timer

3. On success: redirects to `/owner-dashboard` or `/driver-connect`

### What Cloud Should Check

- [ ] Login page JS calls the correct API endpoints
- [ ] Owner flow: `/api/auth/owner-login` with `{plate, phone}`
- [ ] Driver flow: `/api/auth/request-otp` then `/api/auth/verify-otp`
- [ ] Error messages are user-friendly
- [ ] OTP auto-submit works
- [ ] Rate limiting shows proper messages (3/5min for OTP request, 5/5min for verify)

---

## ⚙️ DAEMON — PERMANENT SERVER

### The Bug

**`run_daemon.py`** line 10:

```python
PYTHON = os.path.join(os.path.dirname(sys.executable), "uv") + " run python"
```

This is WRONG. `uv run python` assumes `uv` is in the same dir as the Python executable, which it's NOT when using `uv`-managed Python. It should be:

```python
PYTHON = sys.executable  # Just use the current python directly
```

### What I Fixed

- `run_daemon.py` now uses `sys.executable` directly
- Adds exponential backoff on crash (2s → 4s → 8s → ... → 30s)
- Logs everything to `server.log`
- Kills old processes before starting

### Files for Permanent Startup

| File | Purpose |
|------|---------|
| `run_daemon.py` | Python daemon with auto-restart |
| `run_hidden.vbs` | VBScript that runs daemon without window |
| `install_permanent.bat` | Installs to Startup + starts server |
| `stop_server.bat` | Kills all python + ssh processes |

### To Install

```
Double-click: install_permanent.bat
Or manually:  start /B wscript run_hidden.vbs
```

### To Verify

```
curl http://localhost:8000/login
→ should return 200
```

---

## 🔒 SECURITY FIXES APPLIED (July 16, 2026)

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 1 | **SQL Injection** in `owner_summary` — f-string date | 🔴 Critical | ✅ Fixed — uses `?` params |
| 2 | **No Rate Limiting** — OTP / login spray | 🔴 Critical | ✅ Added — OTP 3/5min, login 5/15min |
| 3 | **Dev Login open** — anyone logs in as admin | 🔴 Critical | ✅ Fixed — blocked when `DEBUG=False` |
| 4 | **Imports** — `random` in middle of file | 🟡 Medium | ✅ Fixed — all at top |
| 5 | **datetime.utcnow()** — deprecated in 3.12+ | 🟡 Medium | ✅ Fixed — `timezone.utc` |
| 6 | **Bare `except:`** — catches KeyboardInterrupt | 🟠 High | ✅ Fixed — specific exceptions |
| 7 | **No CORS** — React frontend can't talk to API | 🟠 High | ✅ Added — `CORSMiddleware` |
| 8 | **Weak Cookies** — `samesite=lax`, no `secure` | 🟡 Medium | ✅ Fixed — `strict` + `secure=not DEBUG` |
| 9 | **No Input Validation** — negative numbers | 🟠 High | ✅ Fixed — trips reject `< 0` |
| 10 | **No Logging** — no audit trail | 🟡 Medium | ✅ Added — session, login, add-driver, summary |

---

## 🐛 KNOWN ISSUES

### 1. `date_param * 3` Fragile (app.py:565)

```python
conn.execute(
    f"SELECT ... {date_sql} ... {date_sql} ... {date_sql} ...",
    date_param * 3  # If someone adds another {date_sql}, this breaks!
).fetchall()
```

If the query is changed to use `{date_sql}` 4 times, the binding count is wrong. Should use named params or repeat the param list explicitly.

### 2. Old Dev Data Persists

The test account `dev_driver` / `dev_owner` still gets created on fresh DB via dev-login. Need to either:
- Remove dev-login entirely for production
- Or make it not create users from scratch

### 3. Login.html Still Exists as Old

The old `login.html` was overwritten, but you should verify the new one renders correctly in Jinja2 (it uses `{{ lang }}`, `{{ dir }}`, `{{ _('...') }}` translation keys).

### 4. No HTTPS

Cookies use `secure=not DEBUG`, which means `secure=False` in dev. For production, need HTTPS.

---

## 📋 API ENDPOINTS COMPLETE LIST

### Auth (5)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/owner-login` | None | Login with plate + phone (auto-registers) |
| POST | `/api/auth/request-otp` | None | Request OTP code (3/5min rate limit) |
| POST | `/api/auth/verify-otp` | None | Verify OTP + login (5/5min rate limit) |
| POST | `/api/auth/dev-login` | None | Dev bypass (blocked when DEBUG=False) |
| POST | `/api/auth/logout` | Cookie | Clear session |

### User (1)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/auth/me` | Cookie | Check if authenticated |

### Owner (6)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/owner/summary` | Owner | Aggregate revenue per period |
| GET | `/api/owner/drivers` | Owner | List cars with assigned drivers |
| GET | `/api/owner/cars` | Owner | List all cars |
| POST | `/api/owner/cars` | Owner | Add car |
| POST | `/api/owner/cars/{id}/assign` | Owner | Assign driver to car |
| POST | `/api/owner/cars/{id}/unassign` | Owner | Unassign driver |
| DELETE | `/api/owner/cars/{id}` | Owner | Delete car |
| POST | `/api/owner/add-driver` | Owner | Add driver by name + phone |
| GET | `/api/owner/driver-trips/{id}` | Owner | View driver's trips |

### Driver — Trips (3)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/trips` | Driver | List trips (paginated) |
| POST | `/api/trips` | Driver | Add trip (validates no negative) |
| DELETE | `/api/trips/{id}` | Driver | Delete own trip |

### Driver — Expenses (2)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/expenses` | Driver | List expenses |
| POST | `/api/expenses` | Driver | Add expense |

### Driver — Fuel (3)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/fuel` | Driver | List fuel fills |
| POST | `/api/fuel` | Driver | Add fuel fill |
| DELETE | `/api/fuel/{id}` | Driver | Delete fuel fill |

### Driver — Maintenance (2)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/maintenance` | Driver | List maintenance |
| POST | `/api/maintenance` | Driver | Add maintenance |

### Reports (1)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/reports` | Driver | Generate report |

### Uploads (2)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/upload-doc` | Cookie | Upload document photo |
| POST | `/api/verify-driver/{id}` | Owner | Approve/reject documents |

### HTML Routes (12)
| Method | Path | Auth | Template |
|--------|------|------|----------|
| GET | `/login` | None | `login.html` |
| GET | `/` | Cookie | redirect to `/driver-connect` or `/owner-dashboard` |
| GET | `/driver-connect` | Driver | `driver_connect.html` |
| GET | `/driver-summary` | Driver | `driver_dashboard.html` |
| GET | `/owner-dashboard` | Owner | `owner_dashboard.html` |
| GET | `/drivers` | Owner | `drivers.html` |
| GET | `/trips` | Driver | `trips.html` |
| GET | `/expenses` | Driver | `expenses.html` |
| GET | `/fuel` | Driver | `fuel.html` |
| GET | `/maintenance` | Driver | `maintenance.html` |
| GET | `/reports` | Driver | `reports.html` |
| GET | `/settings` | Any | `settings.html` |
| GET | `/verify` | Owner | `verify.html` |
| GET | `/accounts` | Any | `accounts.html` |
| GET | `/register/{platform}` | Any | `register_uber/didi/indrive.html` |

---

## 🚀 IMMEDIATE FIXES NEEDED

### Priority 1: Login Page
- [ ] Verify new `login.html` renders correctly
- [ ] Test owner flow end-to-end
- [ ] Test driver OTP flow end-to-end
- [ ] Check Arabic/English translations work
- [ ] The login page I wrote is at `templates/login.html` — it works with:
  - `POST /api/auth/owner-login` (owner: plate + phone)
  - `POST /api/auth/request-otp` (driver: phone → gets code)
  - `POST /api/auth/verify-otp` (driver: phone + code → session)
- [ ] The OLD login.js was calling `/api/auth/login` and `/api/auth/register` which DON'T EXIST

### Priority 2: Daemon
- [ ] Run `run_daemon.py` directly — verify it starts
- [ ] Run `install_permanent.bat` — verify it registers in Startup
- [ ] Reboot Windows — verify server starts automatically

### Priority 3: Code Quality
- [ ] Fix `date_param * 3` fragility (use explicit params)
- [ ] Remove or guard dev-login test account creation
- [ ] Add `commit()` after all DB writes (some rely on auto-close)

### Priority 4: Production Readiness
- [ ] Set up HTTPS / reverse proxy
- [ ] Add environment file (`.env`) with `DEBUG=False`
- [ ] Add database backup strategy
- [ ] Configure proper logging to file (already in daemon)

---

## 🧪 Test Results (Latest, Fresh DB)

```
✅ Login page: 200
✅ Owner register (plate+phone): 200
✅ Owner summary: 200
✅ Add driver: 200
✅ OTP request: 200
✅ Wrong OTP: 401
✅ Logout: 200
✅ Dev login (DEBUG=True): 200
✅ Non-owner blocked (403): 200
✅ Rate limiting (429): working
✅ SQL Injection patched: confirmed
✅ Negative fare rejected: confirmed
```

---

**Generated:** July 16, 2026  
**For:** Cloud — review and fix  
**Contact:** Mohamed Gamal
