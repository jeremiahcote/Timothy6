"""Supervise (or unsupervise) an already-set-up iPhone without erasing it.

Restores a tiny backup containing only the settings file that records
supervision, rewritten to name this computer's key as supervisor. With --full
it instead backs up the whole phone, edits that file in place and restores it.

    python supervise_backup.py               supervise
    python supervise_backup.py --unsupervise  remove supervision
"""
import argparse
import hashlib
import json
import plistlib
import shutil
import sqlite3
import sys

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

import mbdb
import minimal_backup
from blocker import DATA_DIR, KEYBAG, ORGANIZATION, pmd3

BACKUP_DIR = DATA_DIR / "backup"
CONFIG_PATH = "Library/ConfigurationProfiles/CloudConfigurationDetails.plist"
LEGACY_DOMAIN = "HomeDomain"  # iOS 5-9
MODERN_DOMAIN = "SysSharedContainerDomain-systemgroup.com.apple.configurationprofiles"


def cloud_config(supervised):
    if not supervised:
        config = {
            "AllowPairing": True,
            "CloudConfigurationUIComplete": True,
            "IsSupervised": False,
            "PostSetupProfileWasInstalled": False,
        }
    else:
        cert = x509.load_pem_x509_certificate(KEYBAG.read_bytes())
        config = {
            "AllowPairing": True,
            "CloudConfigurationUIComplete": True,
            "ConfigurationSource": 2,
            "ConfigurationWasApplied": True,
            "IsMDMUnremovable": False,
            "IsMandatory": False,
            "IsMultiUser": False,
            "IsSupervised": True,
            "OrganizationName": ORGANIZATION,
            "PostSetupProfileWasInstalled": True,
            "SupervisorHostCertificates": [cert.public_bytes(Encoding.DER)],
        }
    return plistlib.dumps(config, fmt=plistlib.FMT_BINARY)


def patch_legacy(device_dir, content):
    """iOS 5-9: flat files indexed by Manifest.mbdb."""
    manifest = device_dir / "Manifest.mbdb"
    records = mbdb.parse(manifest.read_bytes())
    domain, path = LEGACY_DOMAIN.encode(), CONFIG_PATH.encode()
    matches = [r for r in records if r["domain"] == domain and r["path"] == path]
    if not matches:
        sys.exit("The backup has no CloudConfigurationDetails.plist to edit.")
    file_id = hashlib.sha1(domain + b"-" + path).hexdigest()
    (device_dir / file_id).write_bytes(content)
    matches[0]["digest"] = hashlib.sha1(content).digest()
    mbdb.set_length(matches[0], len(content))
    manifest.write_bytes(mbdb.dump(records))


def patch_modern(device_dir, content):
    """iOS 10+: files under two-character folders, indexed by Manifest.db."""
    db = sqlite3.connect(device_dir / "Manifest.db")
    row = db.execute("SELECT fileID, file FROM Files WHERE relativePath = ?", (CONFIG_PATH,)).fetchone()
    if not row:
        sys.exit("The backup has no CloudConfigurationDetails.plist to edit.")
    file_id, blob = row
    (device_dir / file_id[:2] / file_id).write_bytes(content)
    meta = plistlib.loads(blob)
    info = meta["$objects"][1]
    info["Size"] = len(content)
    if "Digest" in info:
        meta["$objects"][info["Digest"].data] = hashlib.sha1(content).digest()
    db.execute(
        "UPDATE Files SET file = ? WHERE fileID = ?",
        (plistlib.dumps(meta, fmt=plistlib.FMT_BINARY), file_id),
    )
    db.commit()
    db.close()


def patch_backup(device_dir, supervised):
    if plistlib.loads((device_dir / "Manifest.plist").read_bytes()).get("IsEncrypted"):
        sys.exit("Backup encryption is on for this phone; encrypted backups are not supported yet.")
    content = cloud_config(supervised)
    if (device_dir / "Manifest.mbdb").exists():
        patch_legacy(device_dir, content)
    else:
        patch_modern(device_dir, content)


LOCKDOWN_KEYS = ("ProductVersion", "BuildVersion", "DeviceName", "SerialNumber", "ProductType", "UniqueDeviceID")


def lockdown_values():
    result = pmd3("lockdown", "info", capture=True)
    if result.returncode != 0:
        sys.exit("Could not reach the phone (plugged in, unlocked, trusted?).")
    info = json.loads(result.stdout)
    return {key: info[key] for key in LOCKDOWN_KEYS}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--unsupervise", action="store_true")
    parser.add_argument("--full", action="store_true", help="back up and restore the whole phone, not one file")
    parser.add_argument("--dry-run", action="store_true", help="build the backup but do not restore it")
    args = parser.parse_args()
    if not args.unsupervise and not KEYBAG.exists():
        sys.exit("No supervision keybag found. Run `python blocker.py setup` first.")
    if BACKUP_DIR.exists():
        shutil.rmtree(BACKUP_DIR)
    BACKUP_DIR.mkdir(parents=True)
    restore = ["backup2", "restore", "--system", "--settings", "--reboot"]
    if args.full:
        if pmd3("backup2", "backup", "--full", BACKUP_DIR).returncode != 0:
            sys.exit("Backup failed.")
        device_dir = next(p for p in BACKUP_DIR.iterdir() if p.is_dir())
        patch_backup(device_dir, supervised=not args.unsupervise)
    else:
        lockdown = lockdown_values()
        domain = LEGACY_DOMAIN if int(lockdown["ProductVersion"].split(".")[0]) < 10 else MODERN_DOMAIN
        content = cloud_config(not args.unsupervise)
        minimal_backup.write(BACKUP_DIR / "minimal", domain, CONFIG_PATH, content, lockdown)
        restore += ["--source", "minimal"]
    if args.dry_run:
        print(f"Backup built at {BACKUP_DIR}; nothing was restored.")
        return
    print("Restoring; the phone will restart...")
    if pmd3(*restore, BACKUP_DIR).returncode != 0:
        sys.exit("Restore failed (is Find My turned off?).")
    print("Done. After the restart, check Settings > General > About.")


if __name__ == "__main__":
    main()
