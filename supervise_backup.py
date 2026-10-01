"""Supervise (or unsupervise) an already-set-up iPhone without erasing it.

Takes a backup, rewrites the one settings file that records supervision so it
names this computer's key as supervisor, and restores the backup.

    python supervise_backup.py               supervise
    python supervise_backup.py --unsupervise  remove supervision
"""
import argparse
import hashlib
import plistlib
import shutil
import sqlite3
import sys

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

import mbdb
from blocker import DATA_DIR, KEYBAG, ORGANIZATION, pmd3

BACKUP_DIR = DATA_DIR / "backup"
CONFIG_PATH = "Library/ConfigurationProfiles/CloudConfigurationDetails.plist"
LEGACY_DOMAIN = "HomeDomain"  # iOS 5-9; later versions are looked up in Manifest.db


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


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--unsupervise", action="store_true")
    args = parser.parse_args()
    if not args.unsupervise and not KEYBAG.exists():
        sys.exit("No supervision keybag found. Run `python blocker.py setup` first.")
    if BACKUP_DIR.exists():
        shutil.rmtree(BACKUP_DIR)
    BACKUP_DIR.mkdir(parents=True)
    if pmd3("backup2", "backup", "--full", BACKUP_DIR).returncode != 0:
        sys.exit("Backup failed.")
    device_dir = next(p for p in BACKUP_DIR.iterdir() if p.is_dir())
    patch_backup(device_dir, supervised=not args.unsupervise)
    print("Restoring the edited backup; the phone will restart...")
    if pmd3("backup2", "restore", "--system", "--settings", "--reboot", BACKUP_DIR).returncode != 0:
        sys.exit("Restore failed (is Find My turned off?).")
    print("Done. After the restart, check Settings > General > About.")


if __name__ == "__main__":
    main()
