# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Bounded HTTPS transport. Invoke only from the adapter's background worker."""
import json
import ssl
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # An explicit APP origin must not forward its bearer token elsewhere.
        return None


def post(request, timeout=10):
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "User-Agent": "EnergySketch-ArchEnergy/0.1"}
    if request.token:
        headers["Authorization"] = "Bearer " + request.token
    req = urllib.request.Request(request.url, request.body, headers, method="POST")
    opener = urllib.request.build_opener(NoRedirect(),
                urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        response = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    except Exception:
        return 0, {}
    try:
        with response:
            status = response.code
            raw = response.read(1024*1024 + 1)
            if len(raw) > 1024*1024:
                return 0, {}
            try:
                body = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeError):
                return status if status != 200 else 0, {}
            return status, body if isinstance(body, dict) else {}
    except Exception:
        return 0, {}
