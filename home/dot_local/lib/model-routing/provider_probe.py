"""Read-only provider diagnostics. No inference, billing writes, or retries."""
import json
import os
import re
import sys
import urllib.error
import urllib.request

URLS = {
    "https://api.typesafe.ai/v1/models",
    "https://api.anthropic.com/v1/models",
    "https://api.anthropic.com/v1/organizations/spend_limits",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def get(url, headers):
    if url not in URLS:
        raise ValueError("Endpoint is outside the read-only diagnostic allowlist")
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=12) as response:
            raw = response.read(1048577)
            if len(raw) > 1048576:
                return {"status": "oversized_response"}, None
            return {"http_status": response.status}, json.loads(raw)
    except urllib.error.HTTPError as exc:
        return {"http_status": exc.code, "error_body_suppressed": True}, None
    except Exception:
        return {"status": "read_failed", "error_body_suppressed": True}, None


def model_names(data, field, name_key, pattern):
    if not isinstance(data, dict) or not isinstance(data.get(field), list):
        return []
    return sorted({item[name_key] for item in data[field] if isinstance(item, dict)
                   and isinstance(item.get(name_key), str)
                   and re.fullmatch(pattern, item[name_key]) is not None})


def probe(provider):
    if provider == "typesafe":
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key:
            return [{"provider": provider, "status": "missing_key", "paid_requests": 0}]
        report, data = get("https://api.typesafe.ai/v1/models", {"Authorization": "Bearer " + key})
        models = model_names(data, "models", "name", r"jev-[a-z0-9.-]{1,64}")
        report.update(provider=provider, operation="GET /v1/models", model_ids=models,
                      provider_cap_verified=False, auto_refill_verified_off=False,
                      billing_api_documented=False, paid_requests=0)
        return [report]
    if provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return [{"provider": provider, "status": "missing_key", "paid_requests": 0}]
        headers = {"x-api-key": key, "anthropic-version": "2026-10-21"}
        report, data = get("https://api.anthropic.com/v1/models", headers)
        models = model_names(data, "data", "id", r"claude-[a-z0-9.-]{1,80}")
        report.update(provider=provider, operation="GET /v1/models", paid_requests=0,
                      available={name: name in models for name in ["claude-opus-5-5", "claude-fable-5-1", "claude-sonnet-5-5"]})
        reports = [report]
        headers["anthropic-beta"] = "spend-limit-reads-2026-09-26"
        report, data = get("https://api.anthropic.com/v1/organizations/spend_limits", headers)
        report.update(provider=provider, operation="GET /v1/organizations/spend_limits",
                      provider_cap_verified=False, auto_refill_verified_off=False, paid_requests=0)
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            # Seeing some limits does not prove key scope, auto-refill, or a combined cap.
            report["limit_rows_seen"] = len(data["data"])
            report["pagination_incomplete"] = bool(data.get("has_more") or data.get("next_page"))
        return reports + [report]
    raise ValueError("Unsupported provider")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("typesafe", "anthropic"):
        return 2
    for report in probe(sys.argv[1]):
        print(json.dumps(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
