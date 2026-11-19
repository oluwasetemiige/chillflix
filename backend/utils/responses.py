"""One JSON shape for every API response.

Success: {"success": true,  "data": {...}}
Failure: {"success": false, "error": {"code": "...", "message": "...", "details": {...}}}
"""
from flask import jsonify


class ApiError(Exception):
    def __init__(self, message, status=400, code="bad_request", details=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.details = details


def ok(data=None, status=200):
    return jsonify({"success": True, "data": data if data is not None else {}}), status


def fail(message, status=400, code="bad_request", details=None):
    error = {"code": code, "message": message}
    if details:
        error["details"] = details
    return jsonify({"success": False, "error": error}), status
