import secrets

from flask import Blueprint, g, request

from config import Config
from services import paystack
from services.membership import get_membership, settle_payment
from utils import validation as v
from utils.db import db
from utils.ratelimit import limit
from utils.responses import ApiError, ok
from utils.security import login_required

bp = Blueprint("premium", __name__, url_prefix="/premium")


@bp.get("/plans")
def plans():
    items = list(Config.plans().values())
    return ok({"plans": items, "payments_enabled": paystack.configured(), "currency": Config.PAYMENT_CURRENCY,
               "features": {
                   "free": ["Standard catalogue", "Basic discovery", "Personal watchlist"],
                   "premium": ["Premium interface themes", "Advanced recommendations",
                               "Enhanced viewing preferences", "Supported high-quality playback",
                               "Additional account features"]}})


@bp.get("/status")
@login_required
def status():
    return ok({"membership": get_membership(g.user["id"]), "payments_enabled": paystack.configured()})


@bp.post("/checkout")
@login_required
@limit(10, 600, "checkout")
def checkout():
    data = v.json_body()
    plan_id = v.choice(data.get("plan"), tuple(Config.plans()), "plan")
    plan = Config.plans()[plan_id]
    amount_minor = plan["price"] * 100
    reference = "CFX-" + secrets.token_hex(10).upper()
    callback = f"{Config.FRONTEND_URL}/premium.html"
    # Ask Paystack first: if payments are not configured nothing is stored.
    init = paystack.initialize(g.user["email"], amount_minor, plan["currency"], reference, callback,
                               {"user_id": g.user["id"], "plan": plan_id})
    db.execute("INSERT INTO payments (user_id, reference, plan, amount, currency, status) VALUES (?,?,?,?,?,'pending')",
               [g.user["id"], reference, plan_id, amount_minor, plan["currency"]])
    return ok({"authorization_url": init["authorization_url"], "reference": reference})


@bp.get("/verify")
@login_required
def verify():
    reference = (request.args.get("reference") or request.args.get("trxref") or "").strip()
    if not reference:
        raise ApiError("Payment reference is missing.", 422, "validation_error", {"reference": "required"})
    payment = db.one("SELECT user_id FROM payments WHERE reference = ?", [reference])
    if not payment or payment["user_id"] != g.user["id"]:
        raise ApiError("Payment not found.", 404, "not_found")
    result = settle_payment(reference)
    return ok({**result, "membership": get_membership(g.user["id"])})


@bp.post("/webhook")
def webhook():
    """Paystack calls this after a payment. We check the signature, then verify with Paystack again."""
    raw = request.get_data()
    if not paystack.valid_signature(raw, request.headers.get("x-paystack-signature", "")):
        raise ApiError("Invalid signature.", 401, "invalid_signature")
    event = request.get_json(silent=True) or {}
    reference = (event.get("data") or {}).get("reference")
    if event.get("event") == "charge.success" and reference:
        settle_payment(reference)
    return ok({"received": True})


@bp.get("/payments")
@login_required
def payments():
    rows = db.query("SELECT reference, plan, amount, currency, status, channel, paid_at, created_at FROM payments "
                    "WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 50", [g.user["id"]])
    for r in rows:
        r["amount_major"] = r["amount"] / 100
    return ok({"items": rows})
