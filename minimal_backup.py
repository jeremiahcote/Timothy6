"""Build a tiny backup holding a single file, so a restore changes only that file.

The layout (legacy Manifest.mbdb, empty Info.plist, fixed BackupKeyBag) follows
TrollRestore's sparserestore/backup.py by JJTech0130 (MIT licence), which
current iOS versions accept.
"""
import hashlib
import plistlib
import stat
from base64 import b64decode
from datetime import datetime, timezone

import mbdb

# Placeholder keybag for an unencrypted backup, from TrollRestore.
BACKUP_KEYBAG = b64decode(
    """
VkVSUwAAAAQAAAAFVFlQRQAAAAQAAAABVVVJRAAAABDud41d1b9NBICR1BH9JfVtSE1D
SwAAACgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAV1JBUAAA
AAQAAAAAU0FMVAAAABRY5Ne2bthGQ5rf4O3gikep1e6tZUlURVIAAAAEAAAnEFVVSUQA
AAAQB7R8awiGR9aba1UuVahGPENMQVMAAAAEAAAAAVdSQVAAAAAEAAAAAktUWVAAAAAE
AAAAAFdQS1kAAAAoN3kQAJloFg+ukEUY+v5P+dhc/Welw/oucsyS40UBh67ZHef5ZMk9
UVVVSUQAAAAQgd0cg0hSTgaxR3PVUbcEkUNMQVMAAAAEAAAAAldSQVAAAAAEAAAAAktU
WVAAAAAEAAAAAFdQS1kAAAAoMiQTXx0SJlyrGJzdKZQ+SfL124w+2Tf/3d1R2i9yNj9z
ZCHNJhnorVVVSUQAAAAQf7JFQiBOS12JDD7qwKNTSkNMQVMAAAAEAAAAA1dSQVAAAAAE
AAAAAktUWVAAAAAEAAAAAFdQS1kAAAAoSEelorROJA46ZUdwDHhMKiRguQyqHukotrxh
jIfqiZ5ESBXX9txi51VVSUQAAAAQfF0G/837QLq01xH9+66vx0NMQVMAAAAEAAAABFdS
QVAAAAAEAAAAAktUWVAAAAAEAAAAAFdQS1kAAAAol0BvFhd5bu4Hr75XqzNf4g0fMqZA
ie6OxI+x/pgm6Y95XW17N+ZIDVVVSUQAAAAQimkT2dp1QeadMu1KhJKNTUNMQVMAAAAE
AAAABVdSQVAAAAAEAAAAA0tUWVAAAAAEAAAAAFdQS1kAAAAo2N2DZarQ6GPoWRgTiy/t
djKArOqTaH0tPSG9KLbIjGTOcLodhx23xFVVSUQAAAAQQV37JVZHQFiKpoNiGmT6+ENM
QVMAAAAEAAAABldSQVAAAAAEAAAAA0tUWVAAAAAEAAAAAFdQS1kAAAAofe2QSvDC2cV7
Etk4fSBbgqDx5ne/z1VHwmJ6NdVrTyWi80Sy869DM1VVSUQAAAAQFzkdH+VgSOmTj3yE
cfWmMUNMQVMAAAAEAAAAB1dSQVAAAAAEAAAAA0tUWVAAAAAEAAAAAFdQS1kAAAAo7kLY
PQ/DnHBERGpaz37eyntIX/XzovsS0mpHW3SoHvrb9RBgOB+WblVVSUQAAAAQEBpgKOz9
Tni8F9kmSXd0sENMQVMAAAAEAAAACFdSQVAAAAAEAAAAA0tUWVAAAAAEAAAAAFdQS1kA
AAAo5mxVoyNFgPMzphYhm1VG8Fhsin/xX+r6mCd9gByF5SxeolAIT/ICF1VVSUQAAAAQ
rfKB2uPSQtWh82yx6w4BoUNMQVMAAAAEAAAACVdSQVAAAAAEAAAAA0tUWVAAAAAEAAAA
AFdQS1kAAAAo5iayZBwcRa1c1MMx7vh6lOYux3oDI/bdxFCW1WHCQR/Ub1MOv+QaYFVV
SUQAAAAQiLXvK3qvQza/mea5inss/0NMQVMAAAAEAAAACldSQVAAAAAEAAAAA0tUWVAA
AAAEAAAAAFdQS1kAAAAoD2wHX7KriEe1E31z7SQ7/+AVymcpARMYnQgegtZD0Mq2U55u
xwNr2FVVSUQAAAAQ/Q9feZxLS++qSe/a4emRRENMQVMAAAAEAAAAC1dSQVAAAAAEAAAA
A0tUWVAAAAAEAAAAAFdQS1kAAAAocYda2jyYzzSKggRPw/qgh6QPESlkZedgDUKpTr4Z
Z8FDgd7YoALY1g=="""
)


def write(directory, domain, path, contents, lockdown):
    """Write a backup of one file (plus its parent folders) into `directory`.

    `lockdown` is the phone's identity (version, serial number, ...) as a real
    backup records it; older iOS versions refuse a backup without it.
    """
    directory.mkdir(parents=True, exist_ok=True)
    records = [mbdb.new_record(domain, "", stat.S_IFDIR | 0o755)]
    parts = path.split("/")
    for depth in range(1, len(parts)):
        records.append(mbdb.new_record(domain, "/".join(parts[:depth]), stat.S_IFDIR | 0o755))
    records.append(mbdb.new_record(domain, path, stat.S_IFREG | 0o644, contents))

    file_id = hashlib.sha1(f"{domain}-{path}".encode()).hexdigest()
    (directory / file_id).write_bytes(contents)
    (directory / "Manifest.mbdb").write_bytes(mbdb.dump(records))
    (directory / "Info.plist").write_bytes(plistlib.dumps({}))
    (directory / "Status.plist").write_bytes(
        plistlib.dumps(
            {
                "BackupState": "new",
                "Date": datetime(1970, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None),
                "IsFullBackup": False,
                "SnapshotState": "finished",
                "UUID": "00000000-0000-0000-0000-000000000000",
                "Version": "2.4",
            }
        )
    )
    (directory / "Manifest.plist").write_bytes(
        plistlib.dumps(
            {
                "BackupKeyBag": BACKUP_KEYBAG,
                "Lockdown": lockdown,
                "SystemDomainsVersion": "20.0",
                "Version": "9.1",
            }
        )
    )
