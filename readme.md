# CareVerify — AI Healthcare Claim Mediation Platform

> Production-grade backend powering a neutral mediation layer between hospitals, insurance companies, and CareVerify administration.

---

## Architecture Overview

```
Internet → Nginx → Flask API (Gunicorn)
                        ↓
               Supabase (Auth + DB + Storage + Realtime)
                        ↓
               Redis → Celery Workers
                           ↓
               AI Ensemble Engine (XGBoost + RF + IsoForest + Autoencoder + NLP)
```

### Hybrid SaaS Architecture

| Layer | Technology | Responsibility |
|-------|-----------|---------------|
| API Gateway | Nginx | Rate limiting, TLS, reverse proxy |
| Application | Flask + Gunicorn | Business logic, orchestration |
| Auth | Supabase Auth | Google OAuth, JWT, sessions |
| Database | Supabase PostgreSQL | Multi-tenant data + RLS |
| Storage | Supabase Storage | Medical documents (PHI-aware) |
| Realtime | Supabase Realtime | Live notifications, claim updates |
| Async Queue | Celery + Redis | AI processing, SLA monitoring |
| AI Engine | scikit-learn + XGBoost + spaCy | Trust scoring, fraud detection |

---

## Project Structure

```
careverify/
├── app/
│   ├── __init__.py              # Flask app factory
│   ├── extensions.py            # Celery + shared extensions
│   ├── api/
│   │   ├── auth.py              # Auth endpoints
│   │   ├── claims.py            # Claim lifecycle (full CRUD + workflow)
│   │   ├── documents.py         # Document upload + OCR
│   │   ├── analytics.py         # Dashboard intelligence
│   │   ├── admin.py             # Platform administration
│   │   ├── organizations.py     # Org management
│   │   ├── notifications.py     # Notification CRUD
│   │   └── health.py            # Health check
│   ├── middleware/
│   │   └── auth.py              # JWT verification + RBAC decorators
│   ├── services/
│   │   ├── supabase_client.py   # Supabase singleton + helpers
│   │   ├── services.py          # Audit, Notifications, Analytics, Routing
│   │   ├── audit_service.py     # Audit service alias
│   │   ├── notification_service.py
│   │   ├── analytics_service.py
│   │   └── routing_service.py   # Smart insurer routing
│   ├── tasks/
│   │   ├── ai_tasks.py          # Celery async AI pipeline
│   │   └── maintenance_tasks.py # Scheduled maintenance
│   └── utils/
│       ├── validators.py        # Input validation
│       └── pagination.py        # Query pagination
├── ai/
│   ├── models/
│   │   └── ensemble_engine.py   # XGBoost + RF + IsoForest + Autoencoder + NLP
│   └── pipeline/
│       ├── ocr_pipeline.py      # Tesseract / EasyOCR document extraction
│       └── feature_engineering.py  # Claim → ML feature vector
├── migrations/
│   └── 001_initial_schema.sql   # Full DB schema with RLS
├── config/
│   ├── settings.py              # Environment-aware config
│   └── celery_schedule.py       # Periodic task schedule
├── docker/
│   ├── Dockerfile.api           # Production container
│   └── nginx.conf               # Reverse proxy + security headers
├── docker-compose.yml           # Full stack orchestration
├── wsgi.py                      # Flask entry point
├── celery_worker.py             # Celery entry point
├── requirements.txt
└── .env.example
```

---

## Quick Start

### 1. Clone and configure environment

```bash
git clone https://github.com/your-org/careverify-backend.git
cd careverify-backend
cp .env.example .env
# Fill in Supabase and Redis credentials
```

### 2. Run database migrations

Apply `migrations/001_initial_schema.sql` in the Supabase SQL editor.

### 3. Start with Docker Compose

```bash
docker compose up --build
```

Services started:
- **API**: http://localhost:5000
- **Flower** (Celery monitor): http://localhost:5555
- **Nginx**: http://localhost:80

### 4. Local development (without Docker)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Start Redis locally
redis-server

# Start Flask
FLASK_ENV=development python wsgi.py

# Start AI worker
celery -A celery_worker.celery worker -Q ai_processing -c 2 --loglevel=info

# Start general worker + beat
celery -A celery_worker.celery worker -Q default,notifications,audit -c 4 --loglevel=info
celery -A celery_worker.celery beat --loglevel=info
```

---

## API Reference

### Authentication

All endpoints (except `/health` and `/api/v1/auth/verify`) require:
```
Authorization: Bearer <supabase-jwt-token>
```

### Core Endpoints

| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/verify` | — | Verify JWT, get user profile |
| GET | `/api/v1/auth/profile` | All | Get current user profile |
| GET | `/api/v1/claims` | All | List claims (auto-scoped by RLS) |
| POST | `/api/v1/claims` | Hospital | Create new claim |
| GET | `/api/v1/claims/:id` | All | Get claim details |
| POST | `/api/v1/claims/:id/submit` | Hospital | Submit claim → triggers AI pipeline |
| GET | `/api/v1/claims/:id/ai-analysis` | All | AI explainability panel |
| GET | `/api/v1/claims/:id/timeline` | All | Audit event replay |
| POST | `/api/v1/claims/:id/review` | Admin | Submit compliance review |
| POST | `/api/v1/claims/:id/decision` | Insurance | Submit insurance decision |
| POST | `/api/v1/claims/:id/appeal` | Hospital | File appeal |
| POST | `/api/v1/documents/claims/:id/documents` | Hospital | Upload document |
| GET | `/api/v1/documents/:id/url` | All | Get signed document URL |
| GET | `/api/v1/analytics/dashboard` | All | Role-aware dashboard KPIs |
| GET | `/api/v1/analytics/fraud/graph` | Admin/Insurance | Fraud Intelligence Graph |
| GET | `/api/v1/analytics/anomalies` | Admin/Insurance | Cross-hospital anomalies |
| GET | `/api/v1/analytics/sla/status` | Admin | SLA monitoring |
| GET | `/api/v1/admin/organizations` | Admin | List all organizations |
| POST | `/api/v1/admin/insurer-routing/:id` | Admin | Smart insurer routing |
| GET | `/api/v1/admin/audit-logs` | Admin | Immutable audit log |
| GET | `/api/v1/notifications` | All | User notifications |

---

## AI Engine

The **CareVerify Trust Score** (0–100) is computed by an ensemble of 5 models:

| Model | Purpose | Weight |
|-------|---------|--------|
| XGBoost | Fraud probability | 30% |
| Random Forest | Approval likelihood | 25% |
| Isolation Forest | Billing anomalies | 20% |
| Autoencoder | Unseen fraud patterns | 15% |
| NLP (spaCy) | Document inconsistency | 10% |

**Score interpretation:**
- **85–100**: Auto-approve eligible
- **60–84**: Approve with light review
- **40–59**: Compliance review required
- **0–39**: High-risk hold — immediate review

Each result includes:
- Per-model raw scores
- Feature importances
- Risk factors with severity
- Human-readable explanation text

### Training Your Own Models

```python
# Place trained model files in ai/saved_models/
# Required files:
# - xgboost_fraud.pkl    (XGBoost, binary classifier, fraud=1)
# - rf_approval.pkl      (RandomForest, binary classifier, approved=1)
# - isolation_forest.pkl (IsolationForest, fit on clean data)
# - autoencoder/         (Keras SavedModel, trained on normal billing patterns)

import joblib
from sklearn.ensemble import IsolationForest, RandomForestClassifier
import xgboost as xgb

# Train models with your labeled claim dataset
# Feature vector: see ClaimFeatures in ai/models/ensemble_engine.py
```

---

## Security

- **JWT verification**: All tokens validated against Supabase JWT secret
- **RBAC**: Three-tier role system (hospital / insurance / admin)
- **Row-Level Security**: PostgreSQL RLS enforces tenant isolation at DB level
- **PHI-aware**: Patient data stored as `patient_id` references only; PII not in plain columns
- **Signed URLs**: Documents accessed via time-limited signed URLs (1–24h)
- **Audit immutability**: Trigger prevents UPDATE/DELETE on `audit_logs`
- **Rate limiting**: Nginx rate limits (60 req/min API, 10 req/min uploads)
- **7-year audit retention**: Configurable per HIPAA requirements

---

## Celery Workers & Queues

| Queue | Workers | Tasks |
|-------|---------|-------|
| `ai_processing` | 2 | OCR, AI ensemble, feature engineering |
| `notifications` | 4 | Realtime notifications |
| `audit` | 4 | Audit log writes |
| `default` | 4 | Trust scores, SLA monitoring, maintenance |

**Periodic Tasks (Celery Beat):**
- SLA breach detection: every 30 minutes
- Trust score refresh: nightly at 2 AM UTC
- Cleanup: hourly

---

## Supabase Realtime

Frontend subscribes to:
```javascript
// Claim status updates
supabase.channel('claims')
  .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'claims' }, handler)
  .subscribe()

// Live notifications
supabase.channel(`notifications:${userId}`)
  .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'notifications',
      filter: `user_id=eq.${userId}` }, handler)
  .subscribe()
```

---

## License

Proprietary. CareVerify © 2025. All rights reserved.