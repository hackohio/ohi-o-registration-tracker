import json
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlsplit

import requests


class AppsScriptError(RuntimeError):
    pass


class _RetryableTransportError(Exception):
    pass


_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_ALLOWED_HOSTS = {"script.google.com", "script.googleusercontent.com"}
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\Z")


def _safe_google_url(url):
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in _ALLOWED_HOSTS
            and parsed.netloc.casefold() in _ALLOWED_HOSTS
            and parsed.username is None
            and parsed.password is None
        )
    except (TypeError, ValueError):
        return False


def _close(response):
    close = getattr(response, "close", None)
    if close: close()


def _request_timeout(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0: raise AppsScriptError("Apps Script fetch deadline expired")
    return min(5, remaining), remaining


def _fetch_once(session, url, *, secret, stream, deadline):
    try:
        response = session.post(
            url,
            json={"secret": secret, "stream": stream},
            headers={"Accept": "application/json"},
            timeout=_request_timeout(deadline),
            allow_redirects=False,
            stream=True,
        )
    except requests.RequestException:
        raise _RetryableTransportError from None

    redirects = 0
    current_url = url
    while response.status_code in (301, 302, 303, 307, 308):
        if redirects >= 3:
            _close(response)
            raise AppsScriptError("Apps Script returned too many redirects")
        location = response.headers.get("Location")
        try: target = urljoin(current_url, location or "")
        except ValueError:
            _close(response)
            raise AppsScriptError("Apps Script returned an unexpected redirect") from None
        if not location or not _safe_google_url(target):
            _close(response)
            raise AppsScriptError("Apps Script returned an unexpected redirect")
        parts = urlsplit(target)
        if "login" in parts.path.casefold():
            _close(response)
            raise AppsScriptError("Apps Script redirected to a login page")
        _close(response)
        try:
            response = session.get(
                target,
                headers={"Accept": "application/json"},
                timeout=_request_timeout(deadline),
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestException:
            raise _RetryableTransportError from None
        redirects += 1
        current_url = target
    return response


def _json(response, deadline):
    try:
        if hasattr(response, "iter_content"):
            body = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                if time.monotonic() >= deadline:
                    raise AppsScriptError("Apps Script fetch deadline expired")
                if chunk: body.extend(chunk)
            if time.monotonic() >= deadline:
                raise AppsScriptError("Apps Script fetch deadline expired")
            payload = json.loads(body)
        else:
            payload = response.json()
    except ValueError:
        raise AppsScriptError("Apps Script returned invalid JSON") from None
    except requests.RequestException:
        raise _RetryableTransportError from None
    if not isinstance(payload, dict):
        raise AppsScriptError("Apps Script returned an invalid payload")
    if payload.get("ok") is not True:
        code = payload.get("error")
        if isinstance(code, str) and code in {"bad_request", "unauthorized", "unknown_stream", "source_error"}:
            raise AppsScriptError(f"Apps Script rejected request ({code})")
        raise AppsScriptError("Apps Script returned an unsuccessful response")
    return payload


def _retry_delay(response, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0: raise AppsScriptError("Apps Script fetch deadline expired")
    headers = response.headers if response is not None else {}
    try: delay = min(max(float(headers.get("Retry-After", "0.5")), 0), 1)
    except (TypeError, ValueError): delay = 0.5
    time.sleep(min(delay, remaining))


def fetch_timestamps(url, *, secret, stream, timezone, session=None, deadline=25):
    """Fetch and validate local timestamps from one Apps Script stream."""
    if not _safe_google_url(url):
        raise AppsScriptError("Apps Script endpoint URL is invalid")
    endpoint = urlsplit(url)
    if (endpoint.hostname != "script.google.com" or
            endpoint.netloc.casefold() != "script.google.com" or
            re.fullmatch(r"/macros/s/[A-Za-z0-9_-]+/exec", endpoint.path) is None or
            endpoint.query or endpoint.fragment):
        raise AppsScriptError("Apps Script endpoint URL is invalid")
    if stream not in {"participants", "leaders"}:
        raise AppsScriptError("Apps Script stream is invalid")
    if not isinstance(secret, str) or not secret:
        raise AppsScriptError("Apps Script shared secret is missing")
    session = session or requests.Session()
    expires_at = time.monotonic() + deadline
    response = None
    payload = None
    for attempt in range(3):
        try:
            response = _fetch_once(session, url, secret=secret, stream=stream, deadline=expires_at)
        except _RetryableTransportError:
            if attempt == 2: raise AppsScriptError("Apps Script request failed (transport error)") from None
            _retry_delay(None, expires_at)
            continue
        if response.status_code in _TRANSIENT_STATUS:
            if attempt == 2: break
            _retry_delay(response, expires_at)
            _close(response)
            continue
        if response.status_code != 200:
            _close(response)
            raise AppsScriptError(f"Apps Script returned HTTP {response.status_code}")
        try:
            payload = _json(response, expires_at)
            break
        except _RetryableTransportError:
            _close(response)
            if attempt == 2: raise AppsScriptError("Apps Script result request failed (transport error)") from None
            _retry_delay(None, expires_at)
        except AppsScriptError:
            _close(response)
            raise
    if time.monotonic() >= expires_at:
        raise AppsScriptError("Apps Script fetch deadline expired")
    if payload is None:
        status = response.status_code if response is not None else "unknown"
        _close(response)
        raise AppsScriptError(f"Apps Script temporarily unavailable (HTTP {status})")

    if set(payload) != {"ok", "stream", "timezone", "timestamps"}:
        raise AppsScriptError("Apps Script returned an invalid payload schema")
    if payload.get("stream") != stream:
        raise AppsScriptError("Apps Script response stream does not match request")
    if payload.get("timezone") != timezone:
        raise AppsScriptError("Apps Script Sheet timezone does not match event timezone")
    timestamps = payload.get("timestamps")
    if not isinstance(timestamps, list):
        raise AppsScriptError("Apps Script response lacks a timestamp list")
    for value in timestamps:
        if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
            raise AppsScriptError("Apps Script returned an invalid timestamp")
        try: datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise AppsScriptError("Apps Script returned an invalid timestamp") from None
    _close(response)
    return timestamps
