"""Bundled PDF page extraction helper (benign demo)."""

from pathlib import Path


def extract_pages(source: Path, pages: list[int], out: Path) -> Path:
    # demo implementation: copy bytes as-is (stand-in for a real PDF lib)
    data = source.read_bytes()
    out.write_bytes(data)
    return out


if __name__ == "__main__":
    print("usage: extract_pages(source, pages, out)")
