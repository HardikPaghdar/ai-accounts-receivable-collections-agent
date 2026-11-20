import json
from datetime import date
from pathlib import Path
from uuid import uuid4
from typing import Literal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

D=json.loads((Path(__file__).resolve().parents[1]/"data.json").read_text())
C,I,P=D["customers"],D["invoices"],D["payments"]
AS_OF=date(2026,11,20)
ACTIONS={}
app=FastAPI(title="AI Accounts Receivable & Collections Agent",version="1.0.0",description="Explainable receivables prioritization and human-approved collection actions.")

def customer(cid): return next(x for x in C if x["id"]==cid)
def metrics(inv):
    days=max(0,(AS_OF-date.fromisoformat(inv["due_date"])).days)
    paid=sum(p["amount"] for p in P if p["invoice_id"]==inv["id"])
    bal=max(0,round(inv["amount"]-paid,2))
    bucket="not_due" if days==0 else "1_30" if days<=30 else "31_60" if days<=60 else "61_90" if days<=90 else "90_plus"
    return {"days_overdue":days,"paid_amount":round(paid,2),"balance":bal,"aging_bucket":bucket}
def behavior(cid):
    rows=[p for p in P if p["customer_id"]==cid]
    if not rows: return {"average_days_late":0,"late_payment_rate":0.0,"payment_count":0}
    ds=[max(0,p["days_late"]) for p in rows]
    return {"average_days_late":round(sum(ds)/len(ds),1),"late_payment_rate":round(sum(x>0 for x in ds)/len(ds),2),"payment_count":len(ds)}
def score(inv):
    m=metrics(inv); b=behavior(inv["customer_id"])
    parts=[min(25,m["balance"]/1000*2.5),min(35,m["days_overdue"]/90*35),min(25,b["late_payment_rate"]*15+b["average_days_late"]/30*10),15 if inv["status"]=="disputed" else 0]
    val=round(min(100,sum(parts)),1)
    return {"invoice_id":inv["id"],"customer_id":inv["customer_id"],"customer_name":customer(inv["customer_id"])["name"],"balance":m["balance"],"days_overdue":m["days_overdue"],"aging_bucket":m["aging_bucket"],"priority_score":val,"priority_band":"high" if val>=65 else "medium" if val>=35 else "low","payment_behavior":b,"factors":[
      {"factor":"outstanding_balance","contribution":round(parts[0],1),"evidence":f"Outstanding balance {m['balance']:.2f}"},
      {"factor":"invoice_age","contribution":round(parts[1],1),"evidence":f"{m['days_overdue']} days overdue ({m['aging_bucket']})"},
      {"factor":"payment_behavior","contribution":round(parts[2],1),"evidence":f"{b['late_payment_rate']*100:.0f}% late-payment rate; average {b['average_days_late']} days late"},
      {"factor":"dispute_status","contribution":parts[3],"evidence":"Invoice is disputed" if parts[3] else "No active dispute recorded"}]}
def recommend(inv):
    x=score(inv); days=x["days_overdue"]
    if inv["status"]=="disputed": step="Resolve the invoice dispute before sending a payment reminder."
    elif days==0: step="Send a courtesy due-date reminder only if permitted by communication policy."
    elif days<=30: step="Send a friendly reminder and confirm the expected payment date."
    elif days<=60: step="Request a firm payment date and offer an approved payment-plan discussion."
    else: step="Escalate to the finance lead for account review and documented outreach."
    return {**x,"recommended_next_step":step}

class ActionIn(BaseModel):
    invoice_id:str
    action_type:Literal["reminder","payment_plan"]
class Decision(BaseModel):
    decision:Literal["approved","rejected"]
    reviewer:str=Field(min_length=2,max_length=80)
    note:str=Field(default="",max_length=500)

@app.get("/health")
def health(): return {"status":"ok","as_of_date":AS_OF.isoformat()}
@app.get("/api/overview")
def overview():
    rows=[(i,metrics(i)) for i in I]; open_rows=[(i,m) for i,m in rows if m["balance"]>0]
    return {"invoice_count":len(I),"open_invoice_count":len(open_rows),"total_outstanding":round(sum(m["balance"] for _,m in open_rows),2),"overdue_balance":round(sum(m["balance"] for _,m in open_rows if m["days_overdue"]>0),2),"disputed_invoice_count":sum(i["status"]=="disputed" for i,_ in open_rows),"high_priority_count":sum(score(i)["priority_band"]=="high" for i,_ in open_rows)}
@app.get("/api/invoices")
def invoices(): return [{**i,**metrics(i)} for i in I]
@app.get("/api/collections/priority")
def queue(): return sorted([score(i) for i in I if metrics(i)["balance"]>0],key=lambda x:x["priority_score"],reverse=True)
@app.get("/api/invoices/{iid}/recommendation")
def invoice_recommendation(iid:str):
    i=next((x for x in I if x["id"]==iid),None)
    if not i: raise HTTPException(404,"Invoice not found")
    return recommend(i)
@app.post("/api/collection-actions",status_code=201)
def create_action(req:ActionIn):
    i=next((x for x in I if x["id"]==req.invoice_id),None)
    if not i: raise HTTPException(404,"Invoice not found")
    r=recommend(i)
    if r["balance"]<=0: raise HTTPException(409,"Invoice has no outstanding balance")
    c=customer(i["customer_id"])
    if req.action_type=="reminder":
        draft=(f"Subject: Payment reminder for invoice {i['id']}\n\nHello {c['contact']},\n\nOur records show an outstanding balance of {r['balance']:.2f} for invoice {i['id']}, due {i['due_date']}. Could you please confirm the expected payment date? If payment has already been sent, please share the remittance details.\n\nThank you,\nAccounts Receivable")
        details={"draft":draft}
    else:
        n=min(4,max(2,c["installments"])); amount=round(r["balance"]/n,2)
        if amount<c["min_installment"]: raise HTTPException(422,"Balance is below the configured minimum installment")
        details={"installments":n,"installment_amount":amount,"final_installment":round(r["balance"]-amount*(n-1),2),"interval_days":14,"minimum_installment":c["min_installment"],"note":"Illustrative proposal; confirm affordability and policy before approval."}
    a={"id":str(uuid4()),"invoice_id":i["id"],"customer_id":c["id"],"action_type":req.action_type,"status":"pending_approval","created_on":AS_OF.isoformat(),"details":details,"reviewer":None,"decision_note":None}
    ACTIONS[a["id"]]=a; return a
@app.post("/api/collection-actions/{aid}/decision")
def decide(aid:str,req:Decision):
    a=ACTIONS.get(aid)
    if not a: raise HTTPException(404,"Collection action not found")
    if a["status"]!="pending_approval": raise HTTPException(409,"Action already reviewed")
    a.update(status=req.decision,reviewer=req.reviewer,decision_note=req.note); return a
@app.get("/api/collection-actions")
def actions(): return list(ACTIONS.values())
