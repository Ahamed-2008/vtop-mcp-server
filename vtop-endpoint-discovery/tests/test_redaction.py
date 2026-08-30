from __future__ import annotations

import json
from vtop_discovery.utils.redaction import (
    REDACTED,
    cookie_names_redacted,
    is_sensitive_field,
    is_sensitive_value,
    redact_headers,
    redact_payload,
    redact_value,
    set_cookie_names_redacted,
)


def test_is_sensitive_field():
    assert is_sensitive_field("password")
    assert is_sensitive_field("user_password")
    assert is_sensitive_field("csrf_token")
    assert is_sensitive_field("_csrf")
    assert is_sensitive_field("JSESSIONID")
    assert is_sensitive_field("captcha_code")
    assert is_sensitive_field("CAPTCHA")
    assert is_sensitive_field("authorizedID")
    assert is_sensitive_field("regNo")
    assert is_sensitive_field("registration_no")
    assert is_sensitive_field("studentId")
    assert not is_sensitive_field("semesterSubId")
    assert not is_sensitive_field("courseId")


def test_is_sensitive_value():
    assert is_sensitive_value("21BCE1234")
    assert is_sensitive_value("20MIS0042")
    assert not is_sensitive_value("FALL2026")
    assert not is_sensitive_value("CSE1001")


def test_redact_headers():
    headers = {
        "Host": "vtop.vit.ac.in",
        "User-Agent": "Mozilla/5.0",
        "Cookie": "JSESSIONID=12345; auth=xyz",
        "Authorization": "Bearer secret-token",
        "X-CSRF-Token": "secret-csrf",
        "Content-Type": "application/json",
    }
    redacted = redact_headers(headers)
    assert redacted["Host"] == "vtop.vit.ac.in"
    assert redacted["User-Agent"] == "Mozilla/5.0"
    assert redacted["Content-Type"] == "application/json"
    assert redacted["Cookie"] == REDACTED
    assert redacted["Authorization"] == REDACTED
    assert redacted["X-CSRF-Token"] == REDACTED


def test_cookie_names_redacted():
    header = "JSESSIONID=ABCDEF123456; _ga=GA1.2.3456; remember_me=true"
    cookies = cookie_names_redacted(header)
    assert cookies == {
        "JSESSIONID": REDACTED,
        "_ga": REDACTED,
        "remember_me": REDACTED,
    }
    assert cookie_names_redacted(None) == {}
    assert cookie_names_redacted("") == {}


def test_set_cookie_names_redacted():
    header = "JSESSIONID=ABCDEF; Path=/; Secure; HttpOnly, session_id=XYZ; SameSite=Lax"
    cookies = set_cookie_names_redacted(header)
    assert "JSESSIONID" in cookies
    assert cookies["JSESSIONID"] == REDACTED
    assert "session_id" in cookies
    assert cookies["session_id"] == REDACTED
    assert "Path" not in cookies
    assert "Secure" not in cookies
    assert "HttpOnly" not in cookies
    assert "SameSite" not in cookies


def test_redact_value_dict_and_list():
    payload = {
        "username": "admin",
        "password": "my_secret_password",
        "authorizedID": "21BCE0001",
        "nested": {
            "token": "secret_token_value",
            "course": "CSE1001",
        },
        "items": [
            {"otp": "123456", "note": "public"},
            "regular_string",
        ],
    }
    result = redact_value(payload)
    assert result["username"] == "admin"
    assert result["password"] == REDACTED
    assert result["authorizedID"] == REDACTED
    assert result["nested"]["token"] == REDACTED
    assert result["nested"]["course"] == "CSE1001"
    assert result["items"][0]["otp"] == REDACTED
    assert result["items"][0]["note"] == "public"
    assert result["items"][1] == "regular_string"


def test_redact_payload_json():
    raw_json = json.dumps({
        "username": "test_user",
        "password": "supersecretpassword",
        "authorizedID": "21BCE0001",
        "captcha": "XYZ9",
    })
    redacted_str = redact_payload(raw_json)
    assert "supersecretpassword" not in redacted_str
    assert "21BCE0001" not in redacted_str
    parsed = json.loads(redacted_str)
    assert parsed["password"] == REDACTED
    assert parsed["authorizedID"] == REDACTED
    assert parsed["captcha"] == REDACTED


def test_redact_payload_form():
    form_data = "authorizedID=21BCE0001&passwd=supersecret&captchaCheck=AB12&course=CSE1001"
    redacted_form = redact_payload(form_data)
    assert "supersecret" not in redacted_form
    assert "21BCE0001" not in redacted_form
    assert "course=CSE1001" in redacted_form
