from pathlib import Path


SUPPORTED = {".csv", ".tsv", ".json", ".txt"}


def discover_files(input_dir: Path):
    """Return all input files in deterministic order."""
    return sorted(
        (p for p in input_dir.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(input_dir).as_posix().casefold()
    )


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED