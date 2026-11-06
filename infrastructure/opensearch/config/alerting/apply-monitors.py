#!/usr/bin/env python3
"""Create or update OpenSearch alerting monitors from monitors/*.json, matched by name.

- Default: for each file, PUT over the live monitor with the same name (keeping its id,
  so alert history stays attached), or POST it if there is none. Never deletes.
- --dry-run: change nothing; run every monitor once through
  _plugins/_alerting/monitors/_execute?dryrun=true and print, per trigger, whether it
  fired and the rendered ntfy message (or the error). Use it to check queries and
  trigger scripts compile before applying.
- Positional names limit it to those monitors, e.g. `nginx-5xx-burst container-died`.
- --ssh HOST runs the docker commands on HOST over ssh (e.g. from the Mac mini:
  --ssh 83rr-poweredge). Without it, run on the server from the repo root.

  python3 infrastructure/opensearch/config/alerting/apply-monitors.py [--dry-run] [--ssh HOST] [name ...]
"""
import glob
import json
import os
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SSH = None


def os_api(method, path, body=None):
    cmd = ["docker", "exec", "-i", "opensearch", "curl", "-s", "-X", method,
           f"http://localhost:9200{path}", "-H", "Content-Type: application/json"]
    if body is not None:
        cmd += ["--data-binary", "@-"]
    if SSH:
        cmd = ["ssh", SSH, shlex.join(cmd)]
    out = subprocess.run(cmd, input=json.dumps(body) if body is not None else None,
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out) if out else {}


def live_by_name():
    hits = os_api("POST", "/_plugins/_alerting/monitors/_search",
                  {"size": 200, "query": {"match_all": {}}})["hits"]["hits"]
    return {h["_source"].get("monitor", h["_source"])["name"]: h for h in hits}


def dry_run(name, monitor):
    r = os_api("POST", "/_plugins/_alerting/monitors/_execute?dryrun=true", monitor)
    ok = True
    if r.get("error") or (r.get("input_results") or {}).get("error"):
        print(f"{name}: FAILED {r.get('error') or r['input_results']['error']}")
        return False
    for res in r["input_results"]["results"]:
        print(f"{name}: input hits={res['hits']['total']['value']}")
    for trig in r.get("trigger_results", {}).values():
        err = trig.get("error")
        print(f"  trigger {trig['name']}: {'ERROR ' + str(err) if err else ('FIRED' if trig.get('triggered') else 'not triggered')}")
        ok = ok and not err
        for a in trig.get("action_results", {}).values():
            if a.get("error"):
                print(f"    action ERROR: {a['error']}")
                ok = False
                continue
            msg = (a.get("output") or {}).get("message", "")
            try:
                n = json.loads(msg)   # the ntfy publish body must stay valid JSON
                print(f"    priority {n.get('priority')} tags {n.get('tags')}\n    title: {n.get('title')}")
                print("    " + n.get("message", "").replace("\n", "\n    "))
            except ValueError as e:
                print(f"    rendered message is NOT valid JSON ({e}):\n{msg}")
                ok = False
    return ok


def main():
    global SSH
    args = sys.argv[1:]
    if "--ssh" in args:
        i = args.index("--ssh")
        SSH = args[i + 1]
        del args[i:i + 2]
    dry = "--dry-run" in args
    names = [a for a in args if not a.startswith("--")]
    files = sorted(glob.glob(os.path.join(HERE, "monitors", "*.json")))
    if names:
        files = [f for f in files if os.path.basename(f)[:-5] in names]
    live = {} if dry else live_by_name()
    failed = False
    for f in files:
        m = json.load(open(f, encoding="utf-8"))
        name = m["name"]
        if dry:
            failed |= not dry_run(name, m)
            continue
        h = live.get(name)
        if h:
            r = os_api("PUT", f"/_plugins/_alerting/monitors/{h['_id']}"
                       f"?if_seq_no={h['_seq_no']}&if_primary_term={h['_primary_term']}", m)
        else:
            r = os_api("POST", "/_plugins/_alerting/monitors", m)
        print(f"{name}: {'updated' if h else 'created'} {r.get('_id', 'FAILED ' + json.dumps(r)[:300])}")
        failed |= "_id" not in r
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
