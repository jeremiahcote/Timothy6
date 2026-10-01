"""Supervise an already-set-up iPhone without erasing it (iOS 5-9 backups).

Takes a backup, rewrites the one settings file that records supervision so it
names this computer's key as supervisor, and restores the backup.
"""
import hashlib
import plistlib
import shutil
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

import mbdb
from blocker import DATA_DIR, KEYBAG, ORGANIZATION, pmd3

BACKUP_DIR = DATA_DIR / "backup"
CONFIG_DOMAIN = b"HomeDomain"
CONFIG_PATH = b"Library/ConfigurationProfiles/CloudConfigurationDetails.plist"


def supervised_config():
    cert = x509.load_pem_x509_certificate(KEYBAG.read_bytes())
    return plistlib.dumps(
        {
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
        },
        fmt=plistlib.FMT_BINARY,
    )


def patch_backup(device_dir):
    manifest = device_dir / "Manifest.mbdb"
    if not manifest.exists():
        sys.exit("This backup is not in the iOS 5-9 format; this method does not support it yet.")
    records = mbdb.parse(manifest.read_bytes())
    matches = [r for r in records if r["domain"] == CONFIG_DOMAIN and r["path"] == CONFIG_PATH]
    if not matches:
        sys.exit("The backup has no CloudConfigurationDetails.plist to edit.")
    content = supervised_config()
    file_id = hashlib.sha1(CONFIG_DOMAIN + b"-" + CONFIG_PATH).hexdigest()
    (device_dir / file_id).write_bytes(content)
    matches[0]["digest"] = hashlib.sha1(content).digest()
    mbdb.set_length(matches[0], len(content))
    manifest.write_bytes(mbdb.dump(records))


def main():
    if not KEYBAG.exists():
        sys.exit("No supervision keybag found. Run `python blocker.py setup` first.")
    if BACKUP_DIR.exists():
        shutil.rmtree(BACKUP_DIR)
    BACKUP_DIR.mkdir(parents=True)
    if pmd3("backup2", "backup", "--full", BACKUP_DIR).returncode != 0:
        sys.exit("Backup failed.")
    device_dir = next(p for p in BACKUP_DIR.iterdir() if p.is_dir())
    shutil.copytree(device_dir, DATA_DIR / "backup-original", dirs_exist_ok=True)
    patch_backup(device_dir)
    print("Restoring the edited backup; the phone will restart...")
    if pmd3("backup2", "restore", "--system", "--settings", "--reboot", BACKUP_DIR).returncode != 0:
        sys.exit("Restore failed (is Find My turned off?).")
    print("Done. After the restart, check Settings > General > About for the supervision notice.")


if __name__ == "__main__":
    main()
