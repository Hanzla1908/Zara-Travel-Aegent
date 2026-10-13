# CafeBot 2.0

AI-powered chatbot for **Cozy Corner Cafe**. Customers chat with "Brew" to browse the
menu, get recommendations, and place dine-in, takeaway, or delivery orders. Staff view
and advance order status on a live dashboard.

---

## Project structure

```
Cafe-Bot2.0/
├── backend/
│   ├── app.py              # Flask server + Anthropic tool-use loop
│   └── requirements.txt    # Python dependencies
├── data/
│   ├── menu.json           # Menu items, prices, sizes, categories
│   ├── promotions.json     # Active promotions and eligibility rules
│   └── orders.json         # Confirmed orders (auto-created, git-ignored)
├── frontend/
│   ├── index.html          # Customer chat UI  →  served at /
│   └── dashboard.html      # Staff order dashboard  →  served at /dashboard.html
├── prompts/
│   └── system-prompt.md    # Bot persona, ordering flow, confirmation rules
├── .env.example            # Environment variable template
├── .gitignore
└── README.md
```

---

## Prerequisites

- Python 3.9+
- An [Anthropic API key](https://console.anthropic.com/)

---

## Quick start (development)

```bash
# 1. Clone the repo and enter the directory
cd Cafe-Bot2.0

# 2. Create and activate a virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r backend/requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Open .env and set ANTHROPIC_API_KEY

# 5. Start the development server
python backend/app.py
```

Then open **http://localhost:5000** in your browser.
Staff dashboard is at **http://localhost:5000/dashboard.html**.

> The first time the server starts it creates `data/orders.json` automatically if it
> does not exist.

---

## Environment variables

Copy `.env.example` to `.env`. Required variables are marked **bold**.

| Variable | Default | Description |
|---|---|---|
| **`ANTHROPIC_API_KEY`** | — | Your Anthropic API key. Never commit this. |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5` | Model ID. Upgrade only if needed (costs more). |
| `ANTHROPIC_MAX_TOKENS` | `512` | Max tokens per bot reply. |
| `ANTHROPIC_MAX_HISTORY_TURNS` | `6` | Conversation turns kept per request (cost control). |
| `PORT` | `5000` | Port the server listens on. |
| `FLASK_ENV` | `development` | Set to `production` in production. |
| `SYSTEM_PROMPT_PATH` | `prompts/system-prompt.md` | Path to the bot persona file. |
| `MENU_PATH` | `data/menu.json` | Path to the menu data file. |
| `PROMOTIONS_PATH` | `data/promotions.json` | Path to the promotions data file. |
| `ORDERS_PATH` | `data/orders.json` | Path to the confirmed-orders store. |
| `TAX_RATE` | `0.0` | Decimal sales-tax rate, e.g. `0.10` for 10 %. |
| `DELIVERY_FEE` | `0.0` | Flat delivery fee per delivery order, e.g. `2.50`. |

---

## Production deployment (Linux)

Use **Gunicorn** instead of the Flask dev server:

```bash
# Set environment variables (or use a .env file with python-dotenv)
export FLASK_ENV=production
export ANTHROPIC_API_KEY=sk-...

# Run with Gunicorn (4 worker processes)
gunicorn --workers 4 --bind 0.0.0.0:5000 "backend.app:app"
```

> **Note:** `data/orders.json` must be writable by the process user. Create it before
> starting if it does not exist: `echo '[]' > data/orders.json`

For a persistent setup, run Gunicorn behind a reverse proxy (nginx or Caddy) with TLS.

---

## API reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Customer chat UI |
| `GET` | `/dashboard.html` | Staff order dashboard |
| `POST` | `/api/chat` | Send a message; returns bot reply + order state |
| `GET` | `/api/orders` | List all confirmed orders (newest first) |
| `PATCH` | `/api/orders/<id>/status` | Advance order status |

### `POST /api/chat`

**Request body:**
```json
{
  "message": "I'd like a latte please",
  "history": [
    { "role": "user",      "content": "Hi" },
    { "role": "assistant", "content": "Hey there! ..." }
  ],
  "session_id": "abc123"
}
```

**Response:**
```json
{
  "reply": "Great choice! What size — Small, Medium, or Large?",
  "session_id": "abc123",
  "order": { ... }
}
```

### `PATCH /api/orders/<id>/status`

Valid status transitions:

```
confirmed → preparing | cancelled
preparing → ready     | cancelled
ready     → completed
```

**Request body:** `{ "status": "preparing" }`

---

## Customising the bot

- **Menu** — edit `data/menu.json`. Set `"available": false` to hide an item without
  deleting it. The server loads the menu once at startup; restart after changes.
- **Promotions** — edit `data/promotions.json`. Set `"active": false` to disable a
  promotion without removing it.
- **Persona and rules** — edit `prompts/system-prompt.md`. Restart the server after
  changes.
- **Pricing** — set `TAX_RATE` and `DELIVERY_FEE` in `.env`.

---

## Security notes

- `.env` and `data/orders.json` are in `.gitignore` and must never be committed.
  `orders.json` contains customer PII (name, phone, address).
- The API key is read only from `os.getenv("ANTHROPIC_API_KEY")` and is never logged.
- Internal error details are not exposed to the frontend.
- All customer input is sanitised before reaching prompts or file operations.
