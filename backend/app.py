"""CHILLFLIX backend entry point.

Local:       python app.py
Production:  gunicorn app:app
"""
import logging
from datetime import date, datetime
from decimal import Decimal

from flask import Flask, request
from flask.json.provider import DefaultJSONProvider

from config import Config

Config.validate()

from routes import admin, auth, catalog, health, library, premium, users  # noqa: E402
from services.catalog import seed_categories  # noqa: E402
from services.sync import start_scheduler  # noqa: E402
from utils.db import db  # noqa: E402
from utils.ratelimit import check as rate_check  # noqa: E402
from utils.responses import ApiError, fail  # noqa: E402


class JSONProvider(DefaultJSONProvider):
    sort_keys = False

    @staticmethod
    def default(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        return DefaultJSONProvider.default(o)


def create_app():
    app = Flask(__name__)
    app.json = JSONProvider(app)
    app.config["SECRET_KEY"] = Config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024  # 1 MB request bodies
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    for module in (health, auth, catalog, users, library, premium, admin):
        app.register_blueprint(module.bp, url_prefix="/api" + (module.bp.url_prefix or ""))

    @app.before_request
    def global_rate_limit():
        if request.method != "OPTIONS" and request.path.startswith("/api"):
            rate_check("global", 300, 60)

    @app.after_request
    def add_headers(resp):
        origin = request.headers.get("Origin")
        if origin and ("*" in Config.CORS_ORIGINS or origin in Config.CORS_ORIGINS):
            resp.headers["Access-Control-Allow-Origin"] = "*" if "*" in Config.CORS_ORIGINS else origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            resp.headers["Access-Control-Max-Age"] = "600"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return resp

    @app.errorhandler(ApiError)
    def api_error(err):
        return fail(err.message, err.status, err.code, err.details)

    @app.errorhandler(404)
    def not_found(_):
        return fail("That endpoint does not exist.", 404, "not_found")

    @app.errorhandler(405)
    def not_allowed(_):
        return fail("Method not allowed.", 405, "method_not_allowed")

    @app.errorhandler(413)
    def too_big(_):
        return fail("That request is too large.", 413, "too_large")

    @app.errorhandler(Exception)
    def crash(err):
        app.logger.exception("Unhandled error: %s", err)
        return fail("Something went wrong on our side. Please try again.", 500, "server_error")

    @app.get("/")
    def index():
        return {"name": "CHILLFLIX API", "version": Config.VERSION, "health": "/api/health"}

    return app


def prepare_database():
    db.init_schema()
    seed_categories()


app = create_app()

try:
    prepare_database()
except Exception as exc:  # the app still starts; /api/health will show the database as down
    logging.getLogger("chillflix").error("Database setup failed: %s", exc)

start_scheduler()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG, use_reloader=False)
