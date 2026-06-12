#!/usr/bin/env python3
"""Polls session state on Evens's Mac Studio and posts Slack updates when
someone starts, idles, resumes, or ends a remote Tailscale SSH session."""

import ipaddress
import json
import os
import re
import subprocess
import sys
import urllib.request

CONFIG_PATH = os.environ.get("MONITOR_CONFIG", "/usr/local/etc/mac-studio-monitor/config.json")
STATE_PATH = os.environ.get("MONITOR_STATE", "/usr/local/etc/mac-studio-monitor/state.json")

TAILSCALE_CGNAT = ipaddress.ip_network("100.64.0.0/10")
TAILSCALE_HOSTNAME_RE = re.compile(r"^([\w-]+)\.[\w.-]*\.ts\.net$", re.IGNORECASE)


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def parse_idle_seconds(idle_str):
    if idle_str == "-":
        return 0
    m = re.match(r"^(\d+)days?$", idle_str)
    if m:
        return int(m.group(1)) * 86400
    m = re.match(r"^(\d+):(\d+)$", idle_str)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60
    m = re.match(r"^(\d+)$", idle_str)
    if m:
        return int(m.group(1)) * 60
    return 0


def parse_w():
    """Return a list of dicts for each logged-in session via `w`."""
    lines = run(["w"]).splitlines()
    sessions = []
    for line in lines[2:]:  # skip load-average line and column header
        parts = line.split(None, 5)
        if len(parts) < 5:
            continue
        user, tty, from_field, login_at, idle = parts[:5]
        sessions.append({
            "user": user,
            "tty": tty,
            "from": from_field,
            "login_at": login_at,
            "idle_seconds": parse_idle_seconds(idle),
        })
    return sessions


def tailscale_device(from_field):
    """Return a device identifier for a Tailscale-sourced session, or None."""
    if from_field in ("-", ""):
        return None
    m = TAILSCALE_HOSTNAME_RE.match(from_field)
    if m:
        return m.group(1).lower()
    try:
        if ipaddress.ip_address(from_field) in TAILSCALE_CGNAT:
            return from_field
    except ValueError:
        pass
    return None


def person_name(device, config):
    return config.get("device_names", {}).get(device, device)


def notify(config, text):
    webhook = config.get("slack_webhook_url")
    if not webhook:
        return
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(webhook, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Slack post failed: {e}", file=sys.stderr)


def main():
    config = load_json(CONFIG_PATH, {})
    state = load_json(STATE_PATH, {"sessions": {}, "initialized": False})
    sessions = state.setdefault("sessions", {})
    first_run = not state.get("initialized", False)

    idle_threshold = config.get("idle_threshold_seconds", 600)

    current = {}
    for s in parse_w():
        device = tailscale_device(s["from"])
        if device is None:
            continue
        session_id = f"{s['tty']}|{s['login_at']}"
        current[session_id] = {
            "idle_seconds": s["idle_seconds"],
            "person": person_name(device, config),
        }

    # New sessions
    for sid, info in current.items():
        if sid not in sessions:
            initial_status = "idle" if info["idle_seconds"] >= idle_threshold else "active"
            if not first_run:
                notify(config, f":red_circle: *{info['person']}* started a session on Evens's Mac Studio")
            sessions[sid] = {"person": info["person"], "status": initial_status}

    # Idle / active transitions
    for sid, info in current.items():
        st = sessions.get(sid)
        if not st:
            continue
        if info["idle_seconds"] >= idle_threshold and st["status"] == "active":
            notify(config, f":crescent_moon: *{st['person']}* has gone idle on the Mac Studio")
            st["status"] = "idle"
        elif info["idle_seconds"] < idle_threshold and st["status"] == "idle":
            notify(config, f":red_circle: *{st['person']}* is active again on the Mac Studio")
            st["status"] = "active"

    # Disconnected sessions
    for sid in list(sessions.keys()):
        if sid not in current:
            st = sessions.pop(sid)
            if not first_run:
                notify(config, f":large_green_circle: *{st['person']}* disconnected from the Mac Studio")

    state["initialized"] = True
    save_json(STATE_PATH, state)


if __name__ == "__main__":
    main()
