# ⬡ Liquid Gold — Digital Wallet Platform

> A fullstack financial web application built with Flask, SQLAlchemy, and vanilla JavaScript. Features real OAuth authentication, 10-table relational database, 20+ REST API endpoints, and a complete gamification system.

---

## ✨ Features

### 💸 Core Banking
- **Instant Transfers** — Send money via email or LG account number. Auto 0.1% fee above ₹1,000. ₹50,000 single transfer limit.
- **Deposit & Withdraw** — Multiple methods (UPI, Card, Bank). Real-time balance updates.
- **Virtual Card** — Unique `LG...` account number with tier badge display.

### 🏦 Savings & Budgeting
- **Savings Goals** — Create goals with emoji, target amount, and deadline. Deposit/withdraw independently. 100 XP bonus on completion.
- **Budget Manager** — 6 default categories (Food, Transport, Shopping, Entertainment, Health, Other). Monthly limits with live progress bars. Turns yellow at 70%, red at 90%.

### 📊 Analytics & Tracking
- **30-Day Analytics** — Spending vs income line chart. Category doughnut chart. All powered by real transaction data.
- **Activity / Security Log** — Full audit trail of every login, transfer, and change with IP and timestamp.

### 🤝 Social Features
- **Split Bills** — Create group bills, assign amounts to members, collect payments in-app. Auto-notifies all members.
- **Contacts** — Auto-saved after transfers. Quick-send button. Manual add by email or account number.
- **Scheduled Payments** — Weekly / monthly / quarterly recurring transfers. Cancel anytime.

### 🏆 Gamification
- **XP System** — Earn XP for every meaningful action.
- **5 Tiers** — Bronze → Silver → Gold → Platinum → Diamond.
- **Login Streaks** — Daily XP, +50 bonus every 7-day streak.
- **Leaderboard** — Top 5 users by XP across all accounts.

| Action | XP Reward |
|---|---|
| Create Account | +100 |
| Send Transfer | +15 |
| Create Savings Goal | +20 |
| Complete a Goal | +100 |
| Daily Login | +10 |
| 7-Day Streak | +50 |

### 🔔 Notifications
Real-time alerts for every transfer, goal milestone, split bill request, streak achievement, and more.

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | HTML5, CSS3, Vanilla JavaScript (fetch API, Chart.js) |
| **Backend** | Python 3, Flask, Flask-Login |
| **Database** | SQLite + SQLAlchemy ORM |
| **Auth** | OAuth 2.0 (Google + GitHub) |
| **Deployment** | Local / any Python host |

---

## 🗄 Database Schema

10 tables with full relational integrity:

```
users               — accounts, balances, XP, tiers, streaks
transactions        — all money movements with category tagging
notifications       — per-user real-time alerts
savings_goals       — individual goal tracking
budget_categories   — monthly spend limits per category
contacts            — saved recipients
scheduled_payments  — recurring transfer configs
split_bills         — group bill records
split_bill_members  — per-member payment status
activity_log        — security audit trail
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- Google and/or GitHub OAuth credentials

### 1. Clone the repo
```bash
git clone https://github.com/AnirudhAnand3/liquid-gold.git
cd liquid-gold
```

### 2. Create and activate virtual environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up environment variables
```bash
cp .env.example .env
```
Edit `.env` and fill in your credentials:
```env
SECRET_KEY=your-random-secret-key

GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
```

**Getting OAuth credentials:**
- **Google:** [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials → OAuth 2.0 Client ID. Redirect URI: `http://localhost:5000/callback/google`
- **GitHub:** [github.com/settings/developers](https://github.com/settings/developers) → OAuth Apps → New. Callback URL: `http://localhost:5000/callback/github`

### 5. Run
```bash
python app.py
```

Open `http://localhost:5000` — the database creates itself automatically on first run.

> ⚠️ Always use `http://localhost:5000` (not `127.0.0.1`) to match your OAuth redirect URI settings.

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/user` | Current user profile |
| `GET` | `/api/balance` | Balance, XP, tier, streak |
| `POST` | `/api/deposit` | Add funds |
| `POST` | `/api/withdraw` | Withdraw to bank |
| `POST` | `/api/transfer` | Send money to user |
| `GET` | `/api/transactions` | Paginated transaction history |
| `GET` | `/api/analytics` | 30-day chart + category data |
| `POST` | `/api/savings/create` | New savings goal |
| `POST` | `/api/savings/deposit` | Deposit into goal |
| `POST` | `/api/savings/withdraw` | Withdraw from goal |
| `DELETE` | `/api/savings/delete/<id>` | Delete goal |
| `GET` | `/api/notifications` | All notifications |
| `POST` | `/api/notifications/read` | Mark all as read |
| `POST` | `/api/contacts/add` | Add contact |
| `DELETE` | `/api/contacts/delete/<id>` | Remove contact |
| `POST` | `/api/scheduled/create` | Create recurring payment |
| `DELETE` | `/api/scheduled/delete/<id>` | Cancel scheduled payment |
| `POST` | `/api/split/create` | Create split bill |
| `POST` | `/api/split/pay/<id>` | Pay your share |
| `POST` | `/api/budget/update` | Update category limit |
| `POST` | `/api/profile/update` | Update profile |
| `DELETE` | `/api/account/delete` | Delete account |

---

## 📁 Project Structure

```
liquid_gold/
├── app.py                  # Flask app, all routes and models
├── requirements.txt        # Python dependencies
├── .env                    # Secrets (not committed)
├── .env.example            # Template for .env
├── templates/
│   ├── index.html          # Landing page
│   └── dashboard.html      # Main app (1300+ lines)
└── instance/
    └── liquidgold.db       # SQLite database (auto-created)
```

---

## 🔐 Security

- OAuth 2.0 only — no passwords stored
- CSRF state tokens on every OAuth flow
- All financial endpoints require `@login_required`
- Transfer limits enforced server-side (not just frontend)
- `.env` and `instance/` excluded from version control
- Full activity log with IP tracking

---

## 🪪 License

MIT — free to use, modify, and distribute.

---

<p align="center">Built with Flask · SQLAlchemy · OAuth 2.0</p>
