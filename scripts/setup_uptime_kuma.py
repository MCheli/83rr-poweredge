#!/usr/bin/env python3
"""Bootstrap Uptime Kuma: create admin if needed, add monitors, wire the ntfy
notification (self-hosted ntfy, topic homelab), build a public status page. Idempotent — safe to re-run.

This file is the source of truth for Kuma's monitors: a re-run overwrites
settings edited in the UI, and monitors that exist only in the UI drop off
the status page. Add new monitors here (including ARK and Minecraft below).

Reads creds from ~/83rr-poweredge/.env. Talks to Kuma over Socket.IO via
the uptime-kuma-api package.

Run after `docker compose up -d uptime-kuma`. Requires:
    source venv/bin/activate
    pip install uptime-kuma-api  # already installed in the project venv
"""
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
    # ntfy.sh relays the APNs wake-ups our self-hosted ntfy uses for iOS pushes
    ("ntfy.sh (iOS push relay)", "https://ntfy.sh/v1/health"),
]

# Retries before a monitor reports DOWN (one retry per minute). LAN monitors
# probe containers by Docker DNS name; right after Watchtower recreates a
# container that name can briefly resolve to the old IP, which another
# container may already hold (2026-11-13 and 11-20: Energy Monitor "404" for
# ~7 min, answered by tallied). 8 retries rides that out; a real LAN outage
# still pages after ~9 min.
PUBLIC_MAXRETRIES = 2
LAN_MAXRETRIES = 8

# ARK is checked as a container state (UDP game port, no HTTP); the docker
# host is the Kuma "Docker host" entry pointing at the local socket.
ARK_DOCKER_HOST = "Local Docker"

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


def save_status_page(api: UptimeKumaApi, slug: str, publicGroupList: list, **config_changes) -> dict:
    """Save a status page through Kuma's own socket event.

    uptime-kuma-api 1.2.1's save_status_page() first re-reads the page from
    Kuma's public JSON (/api/status-page/<slug>) and expects an "incident" key;
    Uptime Kuma 2.x returns "incidents", so it raises KeyError before saving
    anything (seen 2026-11-22 on Kuma 2.5.12). This sends the same
    [slug, config, imgDataUrl, publicGroupList] payload the library builds, but
    starts from the config Kuma itself reports so 2.x-only fields
    (autoRefreshInterval, rssTitle, ...) are kept.
    """
    config = api._call("getStatusPage", slug)["config"]
    config.update(config_changes)
    icon = config.get("icon") or "/icon.svg"
    return api._call("saveStatusPage", [slug, config, icon, publicGroupList])

def main() -> int:
    env = load_env()
    user = env.get("UPTIME_KUMA_ADMIN_USER", "admin")
    pw = env.get("UPTIME_KUMA_ADMIN_PASSWORD") or sys.exit(
        "UPTIME_KUMA_ADMIN_PASSWORD not in .env"
    )
    ntfy_token = env.get("NTFY_PUBLISH_TOKEN") or sys.exit("NTFY_PUBLISH_TOKEN not in .env")

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

    # Alerts go to the self-hosted ntfy (replaced SendGrid on 2026-10-31, which
    # had run out of credits). Kuma reaches it over the docker network and
    # authenticates with the write-only "alerts" user's token.
    existing = {n["name"]: n for n in api.get_notifications()}
    sg_name = "ntfy → homelab"
    sg_payload = {
        "type": NotificationType.NTFY,
        "name": sg_name,
        "isDefault": True,
        "applyExisting": True,
        "ntfyserverurl": "http://ntfy",
        "ntfytopic": "homelab",
        "ntfyPriority": 4,
        "ntfyAuthenticationMethod": "accessToken",
        "ntfyaccesstoken": ntfy_token,
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

    def tag_once(name, mid, tag_id):
        """Tag a monitor unless it already carries that tag. add_monitor_tag
        adds another copy every time, so each re-run used to stack a duplicate
        (Grafana had six 'lan' tags by 2026-11-22). Best-effort."""
        have = {t.get("tag_id") for t in existing_monitors.get(name, {}).get("tags", [])}
        if tag_id in have:
            return
        try:
            api.add_monitor_tag(tag_id=tag_id, monitor_id=mid, value="")
        except Exception:
            pass

    def upsert_raw(name, common, tag_id):
        """Create or update one monitor by name, then tag it."""
        if name in existing_monitors:
            mid = existing_monitors[name]["id"]
            api.edit_monitor(mid, **common)
            print(f"  monitor updated: {name} (id={mid})")
        else:
            mid = api.add_monitor(**common)["monitorID"]
            print(f"  monitor created: {name} (id={mid})")
        tag_once(name, mid, tag_id)
        return mid

    def upsert_monitor(name, url, tag_id, maxretries=PUBLIC_MAXRETRIES):
        common = {
            "type": MonitorType.HTTP,
            "name": name,
            "url": url,
            "interval": 60,
            "retryInterval": 60,
            "maxretries": maxretries,
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
        tag_once(name, mid, tag_id)
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
        tag_once(name, mid, tag_id)
        return mid

    print("public monitors:")
    public_ids = [upsert_monitor(n, u, tag_ids["public"]) for n, u in PUBLIC_MONITORS]
    print("lan monitors:")
    lan_ids = [
        upsert_monitor(n, u, tag_ids["lan"], maxretries=LAN_MAXRETRIES)
        for n, u in LAN_MONITORS
    ]
    print("game servers:")
    game_common = {
        "interval": 60,
        "retryInterval": 60,
        "maxretries": PUBLIC_MAXRETRIES,
        "notificationIDList": {sg_id: True},
        # ARK and Minecraft were first created in the Kuma UI, which stores
        # dns_resolve_type as null. edit_monitor() merges the live record with
        # these fields and then validates dns_resolve_type for every monitor
        # type, so without this it raises "Unknown dns_resolve_type value: None"
        # (2026-11-22). "A" is the library's own default for new monitors.
        "dns_resolve_type": "A",
    }
    docker_hosts = {h["name"]: h["id"] for h in api.get_docker_hosts()}
    if ARK_DOCKER_HOST in docker_hosts:
        public_ids.append(upsert_raw("ARK Server", {
            **game_common,
            "type": MonitorType.DOCKER,
            "name": "ARK Server",
            "docker_container": "asa",
            "docker_host": docker_hosts[ARK_DOCKER_HOST],
        }, tag_ids["public"]))
    else:
        print(f"  skipped ARK Server: no docker host named {ARK_DOCKER_HOST!r} in Kuma")
    public_ids.append(upsert_raw("Minecraft Server", {
        **game_common,
        "type": MonitorType.GAMEDIG,
        "name": "Minecraft Server",
        "game": "minecraft",
        "hostname": "minecraft.markcheli.com",
        "port": 25565,
    }, tag_ids["public"]))
    print("saas monitors:")
    saas_ids = []
    for n, u in SAAS_MONITORS:
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
        save_status_page(api, sp_slug, **sp_payload)
        print(f"status page updated: /{sp_slug}")
    else:
        api.add_status_page(sp_slug, sp_payload["title"])
        save_status_page(api, sp_slug, **sp_payload)
        print(f"status page created: /{sp_slug}")

    api.disconnect()
    print("\nall done. open https://status.markcheli.com/status/homelab")
    return 0


if __name__ == "__main__":
    sys.exit(main())
