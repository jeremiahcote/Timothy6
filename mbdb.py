"""Read and rewrite Manifest.mbdb, the file index of iOS 5-9 backups."""
import struct

MAGIC = b"mbdb\x05\x00"
FIXED = ">HQIIIIIQBB"  # mode, inode, uid, gid, mtime, atime, ctime, length, flags, property count
STRINGS = ("domain", "path", "target", "digest", "key")


def _read_str(data, pos):
    (length,) = struct.unpack_from(">H", data, pos)
    pos += 2
    if length == 0xFFFF:
        return None, pos
    return data[pos : pos + length], pos + length


def _write_str(value):
    if value is None:
        return b"\xff\xff"
    return struct.pack(">H", len(value)) + value


def parse(data):
    if data[:6] != MAGIC:
        raise ValueError("not a Manifest.mbdb file")
    pos, records = 6, []
    while pos < len(data):
        rec = {}
        for name in STRINGS:
            rec[name], pos = _read_str(data, pos)
        fixed = list(struct.unpack_from(FIXED, data, pos))
        pos += struct.calcsize(FIXED)
        rec["fixed"] = fixed
        rec["props"] = []
        for _ in range(fixed[9]):
            name, pos = _read_str(data, pos)
            value, pos = _read_str(data, pos)
            rec["props"].append((name, value))
        records.append(rec)
    return records


def dump(records):
    out = [MAGIC]
    for rec in records:
        out += [_write_str(rec[name]) for name in STRINGS]
        out.append(struct.pack(FIXED, *rec["fixed"]))
        for name, value in rec["props"]:
            out += [_write_str(name), _write_str(value)]
    return b"".join(out)


def set_length(rec, length):
    rec["fixed"][7] = length
