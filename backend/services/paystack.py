"""Paystack payments. Every payment is verified server-side before upgrading anyone.

Docs: https://paystack.com/docs/api/transaction/
"""
import hashlib
import hmac

import requests

from config import Config
from utils.responses import ApiError

BASE = "https://api.paystack.co"


def configured():
    return bool(Config.PAYSTACK_SECRET_KEY)


def _headers():
    return {"Authorization": f"Bearer {Config.PAYSTACK_SECRET_KEY}", "Content-Type": "application/json"}


def _require():
    if not configured():
        raise ApiError("Payments are not set up yet. Add PAYSTACK_SECRET_KEY on the server.", 503, "payments_unavailable")


def initialize(email, amount_minor, currency, reference, callback_url, metadata):
    _require()
    try:
        resp = requests.post(f"{BASE}/transaction/initialize", headers=_headers(), timeout=20, json={
            "email": email, "amount": amount_minor, "currency": currency,
            "reference": reference, "callback_url": callback_url, "metadata": metadata,
        })
        body = resp.json()
    except (requests.RequestException, ValueError):
        raise ApiError("Could not reach Paystack. Try again shortly.", 502, "payments_unavailable")
    if resp.status_code != 200 or not body.get("status"):
        raise ApiError(body.get("message") or "Paystack rejected the payment request.", 502, "payments_unavailable")
    return body["data"]  # authorization_url, access_code, reference


def verify(reference):
    _require()
    try:
        resp = requests.get(f"{BASE}/transaction/verify/{reference}", headers=_headers(), timeout=20)
        body = resp.json()
    except (requests.RequestException, ValueError):
        raise ApiError("Could not verify the payment right now. Try again shortly.", 502, "payments_unavailable")
    if resp.status_code != 200 or not body.get("status"):
        return {"status": "unknown", "amount": 0, "currency": "", "channel": None}
    data = body["data"]
    return {"status": data.get("status"), "amount": data.get("amount"),
            "currency": data.get("currency"), "channel": data.get("channel")}


def valid_signature(raw_body, signature):
    if not configured() or not signature:
        return False
    digest = hmac.new(Config.PAYSTACK_SECRET_KEY.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(digest, signature)
