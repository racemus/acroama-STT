#!/usr/bin/env python3
"""Write manifest.json for the module-build workflow (see README.md).

Usage:
  update_manifest.py <file> --checked-only
  update_manifest.py <file> --module <id> --version <v> --target <triple>
                     --url <https url> --sha256 <64 hex> --size <bytes>

Both modes set checkedAt to the current UTC time. Exits 2 and writes nothing
when an argument or the file is not valid.
"""

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlsplit

SHA256_RE = re.compile(r"[0-9a-fA-F]{64}")
SIZE_RE = re.compile(r"[0-9]+")
BUILD_ARGS = ("module", "version", "target", "url", "sha256", "size")


class Refusal(Exception):
    pass


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="update_manifest.py")
    parser.add_argument("file")
    parser.add_argument("--checked-only", action="store_true")
    for name in BUILD_ARGS:
        parser.add_argument(f"--{name}")
    args = parser.parse_args(argv)
    given = [name for name in BUILD_ARGS if getattr(args, name) is not None]
    if args.checked_only and given:
        parser.error("--checked-only takes no other option")
    if not args.checked_only and len(given) != len(BUILD_ARGS):
        missing = ", ".join(f"--{name}" for name in BUILD_ARGS if name not in given)
        parser.error(f"missing {missing} (or use --checked-only)")
    return args


def validate_build(args):
    if args.module == "":
        raise Refusal("module is empty")
    if args.version == "":
        raise Refusal("version is empty")
    if args.target == "":
        raise Refusal("target is empty")
    parts = urlsplit(args.url)
    if parts.scheme != "https" or not parts.netloc:
        raise Refusal(f"url is not https://: {args.url!r}")
    if not SHA256_RE.fullmatch(args.sha256):
        raise Refusal("sha256 is not 64 hex characters")
    if not SIZE_RE.fullmatch(args.size) or int(args.size) <= 0:
        raise Refusal(f"size is not a positive integer: {args.size!r}")
    return {
        "version": args.version,
        "builds": {args.target: {"url": args.url, "sha256": args.sha256, "size": int(args.size)}},
    }


def read_manifest(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as err:
        raise Refusal(f"cannot read {path}: {err}") from err
    if not isinstance(data, dict):
        raise Refusal(f"{path} is not a manifest")
    version = data.get("version")
    # bool is an int in Python, so `true` would otherwise pass as version 1.
    if type(version) is not int or version != 1:
        raise Refusal(f"{path} is not a manifest of \"version\": 1")
    if not isinstance(data.get("modules"), dict):
        raise Refusal(f"{path} has no \"modules\" object")
    return data


def updated(data, checked_at, module=None, entry=None):
    modules = dict(data["modules"])
    if module is not None:
        modules[module] = entry
    result = {"version": 1, "checkedAt": checked_at, "modules": modules}
    for key, value in data.items():
        if key not in result:
            result[key] = value
    return result


def write_atomically(path, data):
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    folder = os.path.dirname(os.path.abspath(path))
    mode = stat.S_IMODE(os.stat(path).st_mode)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".manifest-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv):
    args = parse_args(argv)
    try:
        entry = None if args.checked_only else validate_build(args)
        data = read_manifest(args.file)
    except Refusal as err:
        print(f"update_manifest.py: {err}", file=sys.stderr)
        return 2
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if args.checked_only:
        new_data = updated(data, checked_at)
    else:
        new_data = updated(data, checked_at, args.module, entry)
    write_atomically(args.file, new_data)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
