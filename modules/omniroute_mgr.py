"""OmniRoute integration. Never reports synthetic health or fake successful actions."""
from __future__ import annotations

import json
import os
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


# Only these hosts may be probed; prevents SSRF via crafted OMNIROUTE_HEALTH_URL.
_ALLOWED_HOSTS = {"omniroute.local", "127.0.0.1", "localhost"}


def get_status() -> str:
    url = os.getenv("OMNIROUTE_HEALTH_URL", "").strip()
    if not url:
        return "OmniRoute: endpoint di stato non configurato; stato non verificato."
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in _ALLOWED_HOSTS:
            return "OmniRoute: endpoint non autorizzato."
        request = Request(url, headers={"Accept": "application/json"}, method="GET")
        with urlopen(request, timeout=4) as response:
            payload = json.loads(response.read(32_768))
        if not isinstance(payload, dict):
            return "OmniRoute: risposta non valida."
        state = str(payload.get("status", "risposta ricevuta"))[:80]
        return f"OmniRoute: {state}."
    except Exception as exc:
        return f"OmniRoute: verifica fallita ({type(exc).__name__})."
