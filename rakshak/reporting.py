import json
from pathlib import Path


def write_report(output_dir: Path, files, records, stats, seconds, peak_mb):
    sanitized = sum(x["status"] == "sanitized" for x in files)
    quarantined = sum(x["status"] == "quarantined" for x in files)
    suppressed = sum(x["status"] == "suppressed" for x in files)

    report = {
        "schema": "raksha-report/1",
        "files": files,
        "counts": {
            "files_total": len(files),
            "files_sanitized": sanitized,
            "files_quarantined": quarantined,
            "records_processed": len(records),
            "identifiers_detected": stats.get("identifiers", 0),
            "records_linked": sum(r.get("patient") is not None for r in records),
            "records_generalized": stats.get("generalized", 0),
            "records_suppressed": suppressed,
            "records_quarantined": quarantined,
        },
        "entities": stats.get("entities", {}),
        "timing": {"seconds": round(seconds, 3)},
        "resources": {"peak_rss_mb": peak_mb},
    }

    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    with (output_dir / "records.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(
                json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            )