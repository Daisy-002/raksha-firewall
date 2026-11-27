"""report.json and records.jsonl. Neither ever contains source values."""
import json
import sys


def peak_memory_mb():
    try:
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except ImportError:
        return 0.0
    return round(value / (1024 * 1024 if sys.platform == "darwin" else 1024), 2)


def write_report(output_dir, files, records, entities, generalized, seconds):
    status = [f["status"] for f in files]
    report = {
        "schema": "raksha-report/1",
        "files": files,
        "counts": {
            "files_total": len(files),
            "files_sanitized": status.count("sanitized"),
            "files_quarantined": status.count("quarantined"),
            "records_processed": len(records),
            "identifiers_detected": sum(entities.values()),
            "records_linked": sum(r["patient"] is not None for r in records),
            "records_generalized": generalized,
            "records_suppressed": 0,
            "records_quarantined": 0,
        },
        "entities": dict(sorted(entities.items())),
        "timing": {"seconds": round(seconds, 3)},
        "resources": {"peak_rss_mb": peak_memory_mb()},
    }
    (output_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (output_dir / "records.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
