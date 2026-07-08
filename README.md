# BookinGuru Investor Dashboard

AI-powered KPI dashboard for BookinGuru investors and executives.

> 🎓 **Portfolio version.** This is a sanitized copy of a real production app
> I built for BookinGuru, shared with their permission. It runs on seeded
> fake data (`seed_data.py`) — no live connection to BookinGuru's real
> booking data, API keys, or infrastructure. All external integrations
> (bookings API, Google Sheets, email alerts) are optional and disabled by
> default; the app runs fully self-contained on the demo data below.

## Quick Start

### 1. Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy env file
cp .env.example .env

# Seed demo data
python seed_data.py

# Start API server
uvicorn app.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/api/docs

### 2. Frontend

```bash
cd frontend

npm install
npm run dev
```

Dashboard at: http://localhost:5173

**Default login:** `bookinguru` / `investor2026`

---

## Architecture

```
DATA SOURCES          INGESTION            STORAGE            PRESENTATION
─────────────────────────────────────────────────────────────────────────
Weekly KPI (.xlsx)  → File Parser      →  Hotel_Master     → React Dashboard
BookinGuru API      → API Connectors   →  Weekly_Perf      → PDF / CSV Export
Google Analytics    → (stub)           →  Financial_Snaps
                         ↓
                   Reconciliation Engine
                         ↓
                   KPI Calculation Engine
                   (ARPAR_BG, Attach Rate,
                    Net Revenue, MRR Growth)
```

## KPI Dictionary

| Metric | Formula | Target |
|--------|---------|--------|
| ARPAR_BG | Net Revenue / Total Rooms | — |
| Attach Rate | (BG Bookings / Hotel Check-ins) × 100 | 15–25% |
| Net Revenue | GMV × Take Rate | — |
| MRR Growth | (This MRR − Last MRR) / Last MRR × 100 | 15–20% MoM |
| Active Hotels | Hotels with ≥ 30 bookings/month | — |

## Uploading Weekly KPI Data

Upload `.xlsx` or `.csv` files via the "Upload KPI" button in the navbar.

**Required columns** (flexible naming supported):
- `hotel_name` — property name (must match HubSpot/master list)
- `week_start_date` — ISO date or DD/MM/YYYY
- `gmv` — gross merchandise value in EUR
- `transactions` — number of bookings via BG
- `take_rate` — commission percentage

Optional: `avg_cart_value`, `bg_gross_revenue`, `total_hotel_checkins`

## Credentials

Change `DASHBOARD_USER` and `DASHBOARD_PASS` in `.env` before deploying.

For PostgreSQL: set `DATABASE_URL=postgresql://user:pass@host/dbname`

## V2 Roadmap

- HubSpot API integration (CRM pipeline sync)
- Revolut API integration (live cash balance & runway)
- Google Analytics funnel tracking
- Automated milestone alerts (Runway < 9mo, GMV > €1M)
- Enhanced cohort analysis
