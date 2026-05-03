#!/usr/bin/env python3
"""Bootstrap Uptime Kuma: create admin if needed, add monitors, wire SendGrid
notification, build a public status page. Idempotent — safe to re-run.

Reads creds from ~/83rr-poweredge/.env. Talks to Kuma over Socket.IO via
the uptime-kuma-api package.

Run after `docker compose up -d uptime-kuma`. Requires:
    source venv/bin/activate
    pip install uptime-kuma-api  # already installed in the project venv
"""
import json
import os
import sys
import time
from pathlib import Path

from uptime_kuma_api import UptimeKumaApi, MonitorType, NotificationType


def load_env() -> dict:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    out: dict[str, str] = {}
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


# Public + LAN endpoints to monitor. (name, url, kind)
# Public ones: ICMP-style HTTP probe with status code 200-399 acceptable.
# LAN-only ones: Kuma container is on the LAN, so it can reach them directly.
# Public monitors hit the actual public URL — that's what visitors care about.
# A few use specific paths that don't 401/404 at the root.
PUBLIC_MONITORS = [
    ("Personal website", "https://www.markcheli.com"),
    ("Cookbook", "https://cookbook.markcheli.com"),
    ("Flask API", "https://flask.markcheli.com/health"),
    ("Plex", "https://videos.markcheli.com/identity"),
    ("Seafile", "https://files.markcheli.com"),
    ("Home Assistant", "https://home.markcheli.com"),
    ("Tallied", "https://money.markcheli.com"),
    ("Tasks", "https://tasks.markcheli.com"),
]

# External SaaS dependencies — failing one of these means our alerts may not
# arrive even if the homelab is fine. Probed at the public API endpoint.
SAAS_MONITORS = [
    # SendGrid scopes endpoint requires Bearer auth and confirms our key works
    ("SendGrid API", "https://api.sendgrid.com/v3/scopes"),
]

# LAN monitors probe the *backend* over the docker bridge so we bypass
# nginx basic-auth and the LAN allowlist (Kuma is on the same network as
# the targets). Reports "is the service running" semantics rather than
# "is it reachable through nginx", which is more useful for ops.
LAN_MONITORS = [
    ("Grafana", "http://grafana:3000/api/health"),
    ("Prometheus", "http://prometheus:9090/-/healthy"),
    ("OpenSearch Dashboards", "http://opensearch-dashboards:5601/api/status"),
    ("OpenSearch API", "http://opensearch:9200/_cluster/health"),
    ("Energy Monitor", "http://energy-monitor:8000/api/health"),
    ("Daily Report", "http://daily-report:8080/health"),
    ("cAdvisor", "http://cadvisor:8080/healthz"),
    # Postgres DBs intentionally not directly monitored — if any DB is
    # unhealthy its dependent app monitor will go down anyway, so DB-level
    # monitors would just produce duplicate alerts.
]


def main() -> int:
    env = load_env()
    user = env.get("UPTIME_KUMA_ADMIN_USER", "admin")
    pw = env.get("UPTIME_KUMA_ADMIN_PASSWORD") or sys.exit(
        "UPTIME_KUMA_ADMIN_PASSWORD not in .env"
    )
    sg_key = env.get("SENDGRID_API_KEY") or sys.exit("SENDGRID_API_KEY not in .env")

    # Talk to Kuma directly on the docker bridge so we don't depend on
    # nginx / DNS being healthy (this script is the bootstrap, after all).
    kuma_url = "http://uptime-kuma:3001"
    try:
        kuma_url = "http://" + os.popen(
            "docker inspect uptime-kuma --format "
            "'{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'"
        ).read().strip() + ":3001"
    except Exception:
        pass

    print(f"connecting to {kuma_url}")
    api = UptimeKumaApi(kuma_url, wait_events=2)

    # First-run setup: try setup(), ignore failure if admin already exists.
    try:
        api.setup(user, pw)
        print("first-run setup — admin created")
        time.sleep(1)
    except Exception as e:
        if "already" in str(e).lower() or "setup" in str(e).lower() or "exist" in str(e).lower():
            pass  # admin already exists, fine
        else:
            print(f"setup attempt: {e}")
    api.login(user, pw)
    print("login: ok")

    # SendGrid notification — the email channel doesn't exist directly in
    # Kuma; we use the SMTP type with SendGrid's relay creds.
    existing = {n["name"]: n for n in api.get_notifications()}
    sg_name = "SendGrid → mpcheli7@gmail.com"
    sg_payload = {
        "type": NotificationType.SMTP,
        "name": sg_name,
        "isDefault": True,
        "applyExisting": True,
        "smtpHost": "smtp.sendgrid.net",
        "smtpPort": 587,
        "smtpSecure": False,
        "smtpIgnoreTLSError": False,
        "smtpDkimDomain": "",
        "smtpDkimKeySelector": "",
        "smtpDkimPrivateKey": "",
        "smtpDkimHashAlgo": "",
        "smtpDkimheaderFieldNames": "",
        "smtpDkimskipFields": "",
        "smtpUsername": "apikey",
        "smtpPassword": sg_key,
        "customSubject": "[homelab] {{NAME}} {{STATUS}}",
        "smtpFrom": "status@markcheli.com",
        "smtpTo": "mpcheli7@gmail.com",
    }
    if sg_name in existing:
        api.edit_notification(existing[sg_name]["id"], **sg_payload)
        sg_id = existing[sg_name]["id"]
        print(f"notification updated: {sg_name} (id={sg_id})")
    else:
        sg_id = api.add_notification(**sg_payload)["id"]
        print(f"notification created: {sg_name} (id={sg_id})")

    # Tags: 'public' vs 'lan' vs 'saas' so the status page can group them.
    existing_tags = {t["name"]: t for t in api.get_tags()}
    tag_ids = {}
    for tag, color in [("public", "#0096FF"), ("lan", "#888888"), ("saas", "#A020F0")]:
        if tag in existing_tags:
            tag_ids[tag] = existing_tags[tag]["id"]
        else:
            tag_ids[tag] = api.add_tag(name=tag, color=color)["id"]
        print(f"tag: {tag} (id={tag_ids[tag]})")

    # Monitors. Idempotent on monitor name.
    existing_monitors = {m["name"]: m for m in api.get_monitors()}

    def upsert_monitor(name, url, tag_id):
        common = {
            "type": MonitorType.HTTP,
            "name": name,
            "url": url,
            "interval": 60,
            "retryInterval": 60,
            "maxretries": 2,
            "method": "GET",
            "timeout": 30,
            "accepted_statuscodes": ["200-299", "300-399"],
            "ignoreTls": False,
            "notificationIDList": {sg_id: True},
        }
        if name in existing_monitors:
            mid = existing_monitors[name]["id"]
            api.edit_monitor(mid, **common)
            print(f"  monitor updated: {name} (id={mid})")
        else:
            mid = api.add_monitor(**common)["monitorID"]
            print(f"  monitor created: {name} (id={mid})")
        # Tag (best-effort; idempotency is OK to crash on)
        try:
            api.add_monitor_tag(tag_id=tag_id, monitor_id=mid, value="")
        except Exception:
            pass
        return mid

    def upsert_monitor_authed(name, url, tag_id, headers):
        """Variant for monitors that need an Authorization header."""
        common = {
            "type": MonitorType.HTTP,
            "name": name,
            "url": url,
            "interval": 300,
            "retryInterval": 60,
            "maxretries": 2,
            "method": "GET",
            "timeout": 30,
            "accepted_statuscodes": ["200-299", "300-399"],
            "ignoreTls": False,
            "headers": headers,
            "notificationIDList": {sg_id: True},
        }
        if name in existing_monitors:
            mid = existing_monitors[name]["id"]
            api.edit_monitor(mid, **common)
            print(f"  monitor updated: {name} (id={mid})")
        else:
            mid = api.add_monitor(**common)["monitorID"]
            print(f"  monitor created: {name} (id={mid})")
        try:
            api.add_monitor_tag(tag_id=tag_id, monitor_id=mid, value="")
        except Exception:
            pass
        return mid

    print("public monitors:")
    public_ids = [upsert_monitor(n, u, tag_ids["public"]) for n, u in PUBLIC_MONITORS]
    print("lan monitors:")
    lan_ids = [upsert_monitor(n, u, tag_ids["lan"]) for n, u in LAN_MONITORS]
    print("saas monitors:")
    saas_ids = []
    for n, u in SAAS_MONITORS:
        if n == "SendGrid API":
            saas_ids.append(upsert_monitor_authed(
                n, u, tag_ids["saas"],
                json.dumps({"Authorization": f"Bearer {sg_key}"}),
            ))
        else:
            saas_ids.append(upsert_monitor(n, u, tag_ids["saas"]))

    # Public status page bundling all monitors.
    sp_slug = "homelab"
    pages = {p["slug"]: p for p in api.get_status_pages()}
    sp_payload = {
        "title": "homelab status",
        "description": (
            "Real-time health of public + LAN services running on the "
            "83rr-poweredge homelab. Probed every 60s by Uptime Kuma."
        ),
        "theme": "auto",
        "publicGroupList": [
            {
                "name": "Public services",
                "weight": 1,
                "monitorList": [
                    {"id": mid, "weight": idx} for idx, mid in enumerate(public_ids)
                ],
            },
            {
                "name": "LAN-only services",
                "weight": 2,
                "monitorList": [
                    {"id": mid, "weight": idx} for idx, mid in enumerate(lan_ids)
                ],
            },
            {
                "name": "External SaaS dependencies",
                "weight": 3,
                "monitorList": [
                    {"id": mid, "weight": idx} for idx, mid in enumerate(saas_ids)
                ],
            },
        ],
    }
    if sp_slug in pages:
        api.save_status_page(slug=sp_slug, **sp_payload)
        print(f"status page updated: /{sp_slug}")
    else:
        api.add_status_page(sp_slug, sp_payload["title"])
        api.save_status_page(slug=sp_slug, **sp_payload)
        print(f"status page created: /{sp_slug}")

    api.disconnect()
    print("\nall done. open https://status.markcheli.com/status/homelab")
    return 0


if __name__ == "__main__":
    sys.exit(main())
