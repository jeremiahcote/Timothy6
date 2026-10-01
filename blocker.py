#!/usr/bin/env python3
"""Timothy6: lock an adult-content filter onto an iPhone from a computer.

The filter is a configuration profile marked non-removable. iOS only honours
that on a supervised device, and only the computer holding the supervision
keybag can install or remove it -- so the phone cannot switch it off.

    python blocker.py setup     one-time: supervise the phone (USB)
    python blocker.py enable    install the filter
    python blocker.py disable   remove the filter
    python blocker.py status    show whether the filter is installed
"""
import argparse
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

PROFILE_ID = "com.timothy6.filter"
ORGANIZATION = "Timothy6"

# Kept outside any synced folder so the key never reaches the phone.
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "Timothy6"
KEYBAG = DATA_DIR / "supervision-keybag.pem"
CONFIG = Path(__file__).with_name("config.json")

DEFAULTS = {
    # CleanBrowsing Adult filter: blocks porn, forces SafeSearch, blocks
    # proxy/VPN domains. Alternative: https://family.cloudflare-dns.com/dns-query
    "doh_url": "https://doh.cleanbrowsing.org/doh/adult-filter/",
    # Apple's built-in adult-website limiter, on top of DNS.
    "apple_web_filter": True,
    # Apps to hide: names from KNOWN_APPS below, or raw bundle IDs. Each known
    # app's websites are blocked along with it.
    "blocked_apps": ["reddit", "twitter", "instagram"],
    # Extra websites to block (needs apple_web_filter).
    "blocked_websites": [],
    # Remove the App Store so no new apps can be downloaded.
    "block_app_store": False,
    # Stops a VPN app from tunnelling around the DNS filter.
    "block_vpn": False,
    # Stops wiping the phone from Settings to shed supervision.
    "block_erase_from_phone": True,
    # Highest App Store age rating allowed: 1000 = no limit, 300 = 12+
    # (300 hides 17+ apps, which includes third-party browsers, Reddit, X).
    "max_app_rating": 1000,
}


# name: (bundle ID, websites)
KNOWN_APPS = {
    "reddit": ("com.reddit.Reddit", ["reddit.com"]),
    "twitter": ("com.atebits.Tweetie2", ["twitter.com", "x.com"]),
    "instagram": ("com.burbn.instagram", ["instagram.com"]),
    "tiktok": ("com.zhiliaoapp.musically", ["tiktok.com"]),
    "youtube": ("com.google.ios.youtube", ["youtube.com"]),
    "snapchat": ("com.toyopagroup.picaboo", ["snapchat.com"]),
    "facebook": ("com.facebook.Facebook", ["facebook.com"]),
    "telegram": ("ph.telegra.Telegraph", ["telegram.org", "t.me"]),
    "discord": ("com.hammerandchisel.discord", ["discord.com"]),
}


def resolve_blocks(cfg):
    """Return (bundle IDs to hide, websites to block) from the config."""
    bundle_ids, sites = [], list(cfg["blocked_websites"])
    for app in cfg["blocked_apps"]:
        if app.lower() in KNOWN_APPS:
            bundle_id, app_sites = KNOWN_APPS[app.lower()]
            bundle_ids.append(bundle_id)
            sites += app_sites
        elif "." in app:
            bundle_ids.append(app)
        else:
            sys.exit(f"Unknown app '{app}'. Use one of {sorted(KNOWN_APPS)} or a bundle ID.")
    return bundle_ids, sites


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text()))
    return cfg


def stable_uuid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name)).upper()


def build_profile(cfg):
    def payload(ptype, name, **body):
        return {
            "PayloadType": ptype,
            "PayloadIdentifier": f"{PROFILE_ID}.{name}",
            "PayloadUUID": stable_uuid(f"{PROFILE_ID}.{name}"),
            "PayloadDisplayName": name,
            "PayloadVersion": 1,
            **body,
        }

    bundle_ids, sites = resolve_blocks(cfg)
    restrictions = {
        "blockedAppBundleIDs": bundle_ids,
        "allowAppInstallation": not cfg["block_app_store"],
        "allowExplicitContent": False,
        "allowCloudPrivateRelay": False,
        "allowVPNCreation": not cfg["block_vpn"],
        "allowEraseContentAndSettings": not cfg["block_erase_from_phone"],
        "allowUIConfigurationProfileInstallation": False,
        "ratingRegion": "us",
        "ratingApps": cfg["max_app_rating"],
        "ratingMovies": 300,  # PG-13
        "ratingTVShows": 500,  # TV-14
    }
    payloads = [
        payload(
            "com.apple.dnsSettings.managed",
            "dns",
            DNSSettings={"DNSProtocol": "HTTPS", "ServerURL": cfg["doh_url"]},
            ProhibitDisablement=True,
        ),
        payload("com.apple.applicationaccess", "restrictions", **restrictions),
    ]
    if cfg["apple_web_filter"]:
        payloads.append(
            payload(
                "com.apple.webcontent-filter",
                "webfilter",
                FilterType="BuiltIn",
                AutoFilterEnabled=True,
                DenyListURLs=sites,
            )
        )
    return plistlib.dumps(
        {
            "PayloadType": "Configuration",
            "PayloadIdentifier": PROFILE_ID,
            "PayloadUUID": stable_uuid(PROFILE_ID),
            "PayloadDisplayName": "Timothy6",
            "PayloadDescription": "Installed by Timothy6. Removable only from the computer.",
            "PayloadOrganization": ORGANIZATION,
            "PayloadVersion": 1,
            "PayloadRemovalDisallowed": True,
            "PayloadContent": payloads,
        }
    )


def pmd3(*args, capture=False):
    cmd = [sys.executable, "-m", "pymobiledevice3", *map(str, args)]
    return subprocess.run(cmd, capture_output=capture, encoding="utf-8", errors="replace")


def installed():
    result = pmd3("profile", "list", capture=True)
    if result.returncode != 0:
        sys.exit(f"Could not reach the phone (plugged in, unlocked, trusted?):\n{result.stderr.strip()}")
    return PROFILE_ID in result.stdout


def require_keybag():
    if not KEYBAG.exists():
        sys.exit("No supervision keybag found. Run `python blocker.py setup` first.")


def cmd_setup(_):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not KEYBAG.exists():
        if pmd3("profile", "create-keybag", KEYBAG, ORGANIZATION).returncode != 0:
            sys.exit("Failed to create the supervision keybag.")
        print(f"Created supervision keybag: {KEYBAG}")
    print("Supervising the phone (Find My must be turned off for this step)...")
    if pmd3("profile", "supervise", ORGANIZATION, "--keybag", KEYBAG).returncode != 0:
        sys.exit(
            "\nSupervision failed. An iPhone that has already been set up usually refuses\n"
            "this until it is erased -- see 'If setup fails' in the README."
        )
    print("Phone is supervised. Turn Find My back on, then run: python blocker.py enable")


def cmd_enable(_):
    require_keybag()
    with tempfile.TemporaryDirectory() as tmp:
        profile = Path(tmp) / "timothy6.mobileconfig"
        profile.write_bytes(build_profile(load_config()))
        if pmd3("profile", "install", profile, "--keybag", KEYBAG).returncode != 0:
            sys.exit("Failed to install the filter.")
    print("Filter enabled." if installed() else "Install reported success but the profile is not listed.")


def cmd_disable(_):
    require_keybag()
    if pmd3("profile", "remove", PROFILE_ID).returncode != 0 or installed():
        sys.exit("Failed to remove the filter.")
    print("Filter disabled.")


def cmd_status(_):
    print("Filter is ENABLED" if installed() else "Filter is DISABLED")


def cmd_export(args):
    Path(args.path).write_bytes(build_profile(load_config()))
    print(f"Wrote {args.path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in (("setup", cmd_setup), ("enable", cmd_enable), ("disable", cmd_disable), ("status", cmd_status)):
        sub.add_parser(name).set_defaults(fn=fn)
    export = sub.add_parser("export", help="write the profile to a file for inspection")
    export.add_argument("path")
    export.set_defaults(fn=cmd_export)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
