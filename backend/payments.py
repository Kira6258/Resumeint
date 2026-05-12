import os
import razorpay
import schemas
import crud
import auth
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from database import get_db
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

# Initialize Razorpay client
client = razorpay.Client(auth=(os.getenv("RAZORPAY_KEY_ID", "NOT_SET"), os.getenv("RAZORPAY_KEY_SECRET", "NOT_SET")))

# Plan config: amount in paise, duration in days
PLANS = {
    "monthly": {"amount": 5000,  "duration_days": 30,  "label": "Pro Monthly"},
    "yearly":  {"amount": 55000, "duration_days": 365, "label": "Pro Yearly"},
}

class CreateOrderRequest(BaseModel):
    plan: Optional[str] = "monthly"

@router.get("/config")
async def get_config():
    return {"razorpay_key_id": os.getenv("RAZORPAY_KEY_ID", "NOT_SET")}

@router.post("/create-order")
async def create_order(body: CreateOrderRequest, current_user=Depends(auth.get_current_user)):
    """
    Creates a Razorpay order. Plan can be 'monthly' (₹50) or 'yearly' (₹550).
    """
    plan_key = body.plan if body.plan in PLANS else "monthly"
    plan = PLANS[plan_key]

    try:
        order_data = {
            "amount": plan["amount"],
            "currency": "INR",
            "receipt": f"receipt_{current_user.id}_{plan_key}",
            "payment_capture": 1,
            "notes": {"plan": plan_key}
        }
        order = client.order.create(data=order_data)
        order["plan"] = plan_key          # pass plan back to frontend
        order["plan_label"] = plan["label"]
        return order
    except Exception as e:
        print(f"Razorpay Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment order")

@router.post("/verify")
async def verify_payment(request: Request, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    """
    Verifies Razorpay payment signature and updates subscription.
    """
    data = await request.json()

    razorpay_payment_id = data.get("razorpay_payment_id")
    razorpay_order_id   = data.get("razorpay_order_id")
    razorpay_signature  = data.get("razorpay_signature")
    plan_key            = data.get("plan", "monthly")

    if not all([razorpay_payment_id, razorpay_order_id, razorpay_signature]):
        raise HTTPException(status_code=400, detail="Missing payment verification details")

    plan = PLANS.get(plan_key, PLANS["monthly"])

    try:
        params_dict = {
            'razorpay_order_id':   razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature':  razorpay_signature
        }
        client.utility.verify_payment_signature(params_dict)

        expires_at = datetime.utcnow() + timedelta(days=plan["duration_days"])
        crud.update_user_subscription(
            db,
            current_user.id,
            tier="pro",
            razorpay_cust_id=razorpay_payment_id,
            razorpay_sub_id=razorpay_order_id,
            expires_at=expires_at
        )

        return {"message": f"Payment verified — {plan['label']} active!", "status": "success"}
    except Exception as e:
        print(f"Verification Error: {e}")
        raise HTTPException(status_code=400, detail="Payment verification failed")


