#!/usr/bin/env python3
"""Create a reproducible, dependency-free Python zip application.

Fixed entry timestamps, ordering and ZIP_STORED avoid platform-dependent file
metadata and compression differences. Only the runtime package and license ship.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(destination: Path, root: Path = ROOT) -> str:
    package = root / "src" / "llm_handshake"
    entries = {
        "__main__.py": b"from llm_handshake.cli import entrypoint\nentrypoint()\n",
        "LICENSE": (root / "LICENSE").read_bytes(),
    }
    for path in sorted(package.rglob("*")):
        if path.is_symlink():
            raise ValueError("Refusing symlinks in the runtime package.")
        if path.is_file() and (path.suffix == ".py" or path.name == "py.typed"):
            entries[path.relative_to(package.parent).as_posix()] = path.read_bytes()
    if "llm_handshake/cli.py" not in entries:
        raise ValueError("The runtime package is incomplete.")
    out = io.BytesIO()
    out.write(b"#!/usr/bin/env python3\n")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    data = out.getvalue()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".handshake-build-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(temporary, 0o755)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    digest = hashlib.sha256(data).hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(
        f"{digest}  {destination.name}\n", encoding="ascii", newline="\n")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "llm-handshake.pyz")
    args = parser.parse_args()
    try:
        digest = build(args.output)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Build failed: {error}\n")
    print(f"Built {args.output.name}\nSHA256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
