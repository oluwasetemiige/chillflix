"""Premium membership: who is premium, and how a paid plan is activated."""
from datetime import timedelta

from config import Config
from utils.db import db
from utils.times import iso, parse, utcnow


def get_membership(user_id):
    now = iso()
    active = db.query(
        "SELECT plan, starts_at, ends_at FROM subscriptions WHERE user_id = ? AND status = 'active' "
        "AND starts_at <= ? AND ends_at > ? ORDER BY ends_at DESC", [user_id, now, now])
    if not active:
        return {"tier": "free", "is_premium": False, "plan": None, "ends_at": None}
    latest = db.one("SELECT MAX(ends_at) AS e FROM subscriptions WHERE user_id = ? AND status = 'active'", [user_id])
    return {"tier": "premium", "is_premium": True, "plan": active[0]["plan"],
            "ends_at": parse(latest["e"]).isoformat()}


def is_premium(user_id):
    return get_membership(user_id)["is_premium"]


def grant(user_id, plan, days, payment_id=None, tx=None):
    """Adds `days` of premium, stacking after any time the user already has left."""
    runner = tx or db
    now = utcnow()
    current_end = runner.one(
        "SELECT MAX(ends_at) AS e FROM subscriptions WHERE user_id = ? AND status = 'active' AND ends_at > ?",
        [user_id, iso(now)])["e"]
    start = max(now, parse(current_end)) if current_end else now
    end = start + timedelta(days=days)
    return runner.insert(
        "INSERT INTO subscriptions (user_id, plan, status, starts_at, ends_at, payment_id) VALUES (?,?,?,?,?,?)",
        [user_id, plan, "active", iso(now if start == now else start), iso(end), payment_id])


def cancel(user_id):
    return db.execute("UPDATE subscriptions SET status = 'cancelled' WHERE user_id = ? AND status = 'active'", [user_id])


def settle_payment(reference):
    """Verify a Paystack payment SERVER-SIDE and upgrade the user. Safe to call repeatedly."""
    from services import paystack
    payment = db.one("SELECT * FROM payments WHERE reference = ?", [reference])
    if not payment:
        return {"status": "unknown", "message": "Payment reference not found."}
    if payment["status"] == "success":
        return {"status": "success", "message": "Payment already confirmed.", "plan": payment["plan"]}
    result = paystack.verify(reference)
    plan = Config.plans().get(payment["plan"])
    paid_ok = (result["status"] == "success" and result["amount"] == payment["amount"]
               and result["currency"] == payment["currency"] and plan)
    if not paid_ok:
        status = "failed" if result["status"] in ("failed", "abandoned", "reversed") else "pending"
        if status == "failed":
            db.execute("UPDATE payments SET status = 'failed' WHERE reference = ? AND status = 'pending'", [reference])
        if result["status"] == "success":  # paid, but amount/currency do not match what we asked for
            db.execute("UPDATE payments SET status = 'failed' WHERE reference = ? AND status = 'pending'", [reference])
            return {"status": "failed", "message": "Payment amount did not match the plan. Contact support."}
        return {"status": status, "message": f"Payment is {result['status']}."}
    with db.tx() as t:
        # Only the request that flips pending -> success may grant premium (no double upgrades).
        flipped = t.execute(
            "UPDATE payments SET status = 'success', paid_at = ?, channel = ? WHERE reference = ? AND status = 'pending'",
            [iso(), result.get("channel"), reference])
        if flipped:
            grant(payment["user_id"], payment["plan"], plan["days"], payment["id"], tx=t)
    return {"status": "success", "message": "Payment confirmed. Welcome to Premium!", "plan": payment["plan"]}
