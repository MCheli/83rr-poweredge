#!/usr/bin/env python3
"""Point OpenSearch alerting at the self-hosted ntfy (replaced SendGrid on 2026-10-31).

- Creates or updates the notification channel `ntfy-homelab`: a webhook to
  http://ntfy/ on the infrastructure network, authorised with the write-only
  token in .env (NTFY_PUBLISH_TOKEN).
- Rewrites every monitor action that still sends SendGrid mail JSON into an
  ntfy JSON publish (topic "homelab"), in the live monitors and in
  monitors/*.json. Title = old subject, message = old body, priority from the
  trigger severity (1 -> 5 ... 5 -> 1).
- --test fires a one-off monitor whose trigger is always true through the
  channel, i.e. the same path a real alert takes. (The Notifications
  "send test message" button cannot work: its body isn't ntfy JSON.)

Run from the repo root:  python3 infrastructure/opensearch/config/alerting/wire-ntfy.py [--dry-run] [--test | --test-only]
(--test-only sends the test and changes nothing; scripts/alert-test.sh uses it.)
Never prints the token.
"""
import glob
import json
import os
import subprocess
import sys

CHANNEL_ID = "ntfy-homelab"
TOPIC = "homelab"
HERE = os.path.dirname(os.path.abspath(__file__))
PRIORITY = {"1": 5, "2": 4, "3": 3, "4": 2, "5": 1}


def os_api(method, path, body=None):
    cmd = ["docker", "exec", "-i", "opensearch", "curl", "-s", "-X", method,
           f"http://localhost:9200{path}", "-H", "Content-Type: application/json"]
    if body is not None:
        cmd += ["--data-binary", "@-"]
    out = subprocess.run(cmd, input=json.dumps(body) if body is not None else None,
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out) if out else {}


def publish_token():
    for line in open(".env"):
        if line.startswith("NTFY_PUBLISH_TOKEN="):
            return line.split("=", 1)[1].strip().strip("'\"")
    sys.exit("NTFY_PUBLISH_TOKEN missing from .env")


def ensure_channel(dry_run):
    config = {"name": "ntfy-homelab",
              "description": "Homelab alerts -> self-hosted ntfy, topic homelab (write-only token)",
              "config_type": "webhook", "is_enabled": True,
              "webhook": {"url": "http://ntfy/", "method": "POST",
                          "header_params": {"Authorization": f"Bearer {publish_token()}",
                                            "Content-Type": "application/json"}}}
    exists = os_api("GET", f"/_plugins/_notifications/configs/{CHANNEL_ID}").get("config_list")
    print(f"channel {CHANNEL_ID}: {'update' if exists else 'create'}{' (dry run)' if dry_run else ''}")
    if dry_run:
        return
    if exists:
        r = os_api("PUT", f"/_plugins/_notifications/configs/{CHANNEL_ID}", {"config": config})
    else:
        r = os_api("POST", "/_plugins/_notifications/configs", {"config_id": CHANNEL_ID, "config": config})
    if r.get("config_id") != CHANNEL_ID:
        sys.exit(f"channel write failed: {json.dumps(r)[:300]}")


def to_ntfy(action, severity):
    """Return the action rewritten for ntfy, or None if it's already done / not SendGrid JSON."""
    src = (action.get("message_template") or {}).get("source", "")
    try:
        mail = json.loads(src)
    except ValueError:
        return None
    if "personalizations" not in mail:
        return None
    body = "\n\n".join(c.get("value", "") for c in mail.get("content", []))
    message = {"topic": TOPIC, "title": mail.get("subject", "[homelab] alert"), "message": body,
               "priority": PRIORITY.get(str(severity), 3), "tags": ["rotating_light"]}
    new = dict(action)
    new["destination_id"] = CHANNEL_ID
    new["name"] = "ntfy-homelab"
    new["message_template"] = {**action["message_template"], "source": json.dumps(message, ensure_ascii=False)}
    return new


def rewrite_monitor(monitor):
    changed = 0
    for t in monitor.get("triggers", []):
        trig = t.get("query_level_trigger") or t.get("bucket_level_trigger") or t.get("document_level_trigger") or t
        acts = trig.get("actions", [])
        for i, a in enumerate(acts):
            new = to_ntfy(a, trig.get("severity"))
            if new:
                acts[i] = new
                changed += 1
    return changed


def live(dry_run):
    hits = os_api("POST", "/_plugins/_alerting/monitors/_search",
                  {"size": 100, "query": {"match_all": {}}})["hits"]["hits"]
    for h in hits:
        m = h["_source"].get("monitor", h["_source"])
        n = rewrite_monitor(m)
        print(f"live  {m['name']}: {n} action(s) rewritten{' (dry run)' if dry_run and n else ''}")
        if n and not dry_run:
            for k in ("last_update_time", "enabled_time", "user", "schema_version", "owner"):
                m.pop(k, None)
            r = os_api("PUT", f"/_plugins/_alerting/monitors/{h['_id']}"
                       f"?if_seq_no={h['_seq_no']}&if_primary_term={h['_primary_term']}", m)
            if "_id" not in r:
                sys.exit(f"  update failed: {json.dumps(r)[:300]}")


def repo(dry_run):
    # The files are hand-formatted, so swap the three changed values in the text instead of
    # re-dumping the JSON, then check the result parses to exactly the rewritten monitor.
    for f in sorted(glob.glob(os.path.join(HERE, "monitors", "*.json"))):
        raw = text = open(f, encoding="utf-8").read()
        d = json.loads(raw)
        m = d.get("monitor", d)
        n = 0
        for t in m.get("triggers", []):
            trig = t.get("query_level_trigger") or t.get("bucket_level_trigger") or t.get("document_level_trigger") or t
            for a in trig.get("actions", []):
                new = to_ntfy(a, trig.get("severity"))
                if not new:
                    continue
                for old_v, new_v in ((a["message_template"]["source"], new["message_template"]["source"]),
                                     (a["destination_id"], new["destination_id"]), (a["name"], new["name"])):
                    for ascii_only in (True, False):
                        old_s = json.dumps(old_v, ensure_ascii=ascii_only)
                        if old_s in text:
                            text = text.replace(old_s, json.dumps(new_v, ensure_ascii=ascii_only), 1)
                            break
                    else:
                        sys.exit(f"{os.path.basename(f)}: can't find {old_v[:40]!r} to replace")
                n += 1
        print(f"repo  {os.path.basename(f)}: {n} action(s) rewritten")
        if n:
            rewrite_monitor(m)
            if json.loads(text) != d:
                sys.exit(f"{os.path.basename(f)}: text edit doesn't match the rewritten monitor")
            if not dry_run:
                open(f, "w", encoding="utf-8").write(text)


def test():
    msg = {"topic": TOPIC, "title": "[homelab] OpenSearch alert test",
           "message": "Test alert from OpenSearch alerting via channel ntfy-homelab "
                      "(monitor run {{ctx.periodStart}}). No action needed.",
           "priority": 2, "tags": ["white_check_mark"]}
    monitor = {"type": "monitor", "monitor_type": "query_level_monitor", "name": "ntfy-test",
               "enabled": False, "schedule": {"period": {"interval": 1, "unit": "DAYS"}},
               "inputs": [{"search": {"indices": ["logs-homelab-*"], "query": {"size": 0, "query": {"match_all": {}}}}}],
               "triggers": [{"query_level_trigger": {"name": "always", "severity": "5",
                             "condition": {"script": {"source": "return true", "lang": "painless"}},
                             "actions": [{"name": "ntfy-test", "destination_id": CHANNEL_ID,
                                          "message_template": {"source": json.dumps(msg), "lang": "mustache"},
                                          "throttle_enabled": False}]}}]}
    r = os_api("POST", "/_plugins/_alerting/monitors/_execute?dryrun=false", monitor)
    res = r.get("trigger_results", {})
    errors = [a.get("error") for t in res.values() for a in t.get("action_results", {}).values() if a.get("error")]
    if r.get("error") or errors or not res:
        sys.exit(f"test FAILED: {r.get('error') or errors or 'no trigger results'}")
    print("test sent: ntfy accepted the OpenSearch alert")


if __name__ == "__main__":
    if "--test-only" in sys.argv:   # weekly check (scripts/alert-test.sh): send, change nothing
        test()
        sys.exit(0)
    dry = "--dry-run" in sys.argv
    ensure_channel(dry)
    live(dry)
    repo(dry)
    if "--test" in sys.argv and not dry:
        test()
