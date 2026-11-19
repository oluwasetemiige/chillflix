"""Small, readable input checks. Every function raises ApiError with a clear message."""
import re

from flask import request

from utils.responses import ApiError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,24}$")


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Send a JSON body.", 400, "invalid_json")
    return data


def text(data, key, label=None, min_len=1, max_len=500, required=True):
    label = label or key
    value = data.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ApiError(f"{label} is required.", 422, "validation_error", {key: "required"})
        return None
    if not isinstance(value, str):
        raise ApiError(f"{label} must be text.", 422, "validation_error", {key: "invalid"})
    value = value.strip()
    if len(value) < min_len or len(value) > max_len:
        raise ApiError(f"{label} must be {min_len}-{max_len} characters.", 422, "validation_error", {key: "length"})
    return value


def email(data, key="email"):
    value = text(data, key, "Email", max_len=254).lower()
    if not EMAIL_RE.match(value):
        raise ApiError("Enter a valid email address.", 422, "validation_error", {key: "invalid"})
    return value


def username(data, key="username"):
    value = text(data, key, "Username", max_len=24)
    if not USERNAME_RE.match(value):
        raise ApiError(
            "Username must be 3-24 characters: letters, numbers, dot, dash or underscore.",
            422, "validation_error", {key: "invalid"},
        )
    return value


def password(data, key="password"):
    value = data.get(key)
    if not isinstance(value, str) or len(value) < 8 or len(value) > 128:
        raise ApiError("Password must be 8-128 characters.", 422, "validation_error", {key: "invalid"})
    if value.isdigit() or value.isalpha():
        raise ApiError("Use a mix of letters and numbers in your password.", 422, "validation_error", {key: "weak"})
    return value


def integer(value, default=None, minimum=None, maximum=None, name="value"):
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ApiError(f"{name} must be a whole number.", 422, "validation_error", {name: "invalid"})
    if minimum is not None and number < minimum:
        number = minimum
    if maximum is not None and number > maximum:
        number = maximum
    return number


def choice(value, options, name="value"):
    if value not in options:
        raise ApiError(f"{name} must be one of: {', '.join(options)}.", 422, "validation_error", {name: "invalid"})
    return value


def media_type(value):
    return choice(value, ("movie", "series"), "media_type")
