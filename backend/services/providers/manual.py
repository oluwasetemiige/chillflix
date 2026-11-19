"""Sources added by an administrator in the admin dashboard (stored in provider_sources)."""
from utils import db
from .base import BaseProvider


class ManualProvider(BaseProvider):
    name = "manual"
    label = "Admin-added sources"

    def configured(self):
        return True

    def health(self):
        n = db.query("SELECT COUNT(*) AS n FROM provider_sources WHERE provider = 'manual' AND is_active = 1", one=True)["n"]
        return {"status": "ok", "detail": f"{n} active source(s)"}
