# AI Accounts Receivable & Collections Agent

A runnable FastAPI decision-support demo for B2B finance teams. It calculates invoice aging, prioritizes collection work using explainable payment-behavior factors, drafts personalized reminders, and proposes installment plans for human review.

## Run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```
API docs: http://127.0.0.1:8000/docs

## Example
```bash
curl http://127.0.0.1:8000/api/collections/priority
curl http://127.0.0.1:8000/api/invoices/INV-2003/recommendation
curl -X POST http://127.0.0.1:8000/api/collection-actions -H "Content-Type: application/json" -d '{"invoice_id":"INV-2003","action_type":"reminder"}'
```

## Workflow
Invoices and payment history → aging and payment behavior → explainable priority score → reminder/payment-plan draft → finance approval.

## API
- GET `/health`, `/api/overview`, `/api/invoices`, `/api/collections/priority`
- GET `/api/invoices/{id}/recommendation`
- POST `/api/collection-actions`, `/api/collection-actions/{id}/decision`
- GET `/api/collection-actions`

## Limitations
Deterministic rules, not a trained credit or default-prediction model. Synthetic data; as-of date fixed at 2026-11-20; action state is in memory. No accounting-system connection, email/SMS delivery, payment processing, legal notice, or autonomous plan execution. A disputed invoice is routed to dispute resolution rather than generic reminder. Review all outputs against finance policy and applicable law.
