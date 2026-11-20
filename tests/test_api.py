from fastapi.testclient import TestClient
from app.main import app
c=TestClient(app)

def test_aging_and_summary():
    x=c.get("/api/overview").json()
    assert x["invoice_count"]==6 and x["open_invoice_count"]==4
    inv=next(i for i in c.get("/api/invoices").json() if i["id"]=="INV-2003")
    assert inv["days_overdue"]==67 and inv["aging_bucket"]=="61_90"

def test_priority_explainable():
    rows=c.get("/api/collections/priority").json()
    assert rows[0]["priority_score"]>=rows[-1]["priority_score"]
    assert all(len(x["factors"])==4 for x in rows)

def test_dispute_is_routed_before_reminder():
    r=c.get("/api/invoices/INV-2004/recommendation").json()
    assert "Resolve the invoice dispute" in r["recommended_next_step"]

def test_reminder_approval_state():
    a=c.post("/api/collection-actions",json={"invoice_id":"INV-2003","action_type":"reminder"})
    assert a.status_code==201 and a.json()["status"]=="pending_approval"
    aid=a.json()["id"]
    d=c.post(f"/api/collection-actions/{aid}/decision",json={"decision":"approved","reviewer":"AR Lead"})
    assert d.json()["status"]=="approved"
    assert c.post(f"/api/collection-actions/{aid}/decision",json={"decision":"rejected","reviewer":"AR Lead"}).status_code==409

def test_payment_plan_and_missing_invoice():
    a=c.post("/api/collection-actions",json={"invoice_id":"INV-2003","action_type":"payment_plan"})
    assert a.status_code==201 and a.json()["details"]["installments"]==4
    assert c.post("/api/collection-actions",json={"invoice_id":"missing","action_type":"reminder"}).status_code==404

def test_health():
    assert c.get("/health").json()["status"]=="ok"
