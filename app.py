from __future__ import annotations

import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import threading
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

import streamlit as st


ROOT = Path(__file__).resolve().parent
MAIN_SCRIPT = ROOT / "main.py"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MAX_ARCHIVE_BYTES = 300 * 1024 * 1024
MAX_MEMBER_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 5000
BLOCKED_PATH_NAMES = {"truth", "attacker", "attackers", "attacker_assets"}
PSEUDONYM_PATTERN = re.compile(r"PSN-[0-9A-Z]{4}-[0-9A-Z]{4}\Z")


class DemoError(Exception):
    pass


@st.cache_resource
def _execution_lock() -> threading.Lock:
    return threading.Lock()


def _is_blocked_path_part(part: str) -> bool:
    folded = part.casefold()
    stem = PurePosixPath(folded).stem
    return (
        stem in BLOCKED_PATH_NAMES
        or folded.startswith(("attacker-", "attacker_"))
    )


def _extract_zip(payload: bytes, destination: Path) -> int:
    root = destination.resolve()
    seen: set[str] = set()
    declared_total = 0
    actual_total = 0
    file_count = 0

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if not members:
                raise DemoError("The ZIP archive is empty.")
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise DemoError("The ZIP contains too many entries.")

            for info in members:
                raw_name = info.filename
                normalized = raw_name.replace("\\", "/")
                if (
                    not raw_name
                    or "\x00" in raw_name
                    or normalized.startswith("/")
                    or re.match(r"^[A-Za-z]:", normalized)
                ):
                    raise DemoError("The ZIP contains an unsafe path.")

                raw_parts = normalized.split("/")
                if any(part == ".." for part in raw_parts):
                    raise DemoError("The ZIP contains an unsafe path.")
                parts = [part for part in raw_parts if part not in ("", ".")]
                if not parts:
                    if info.is_dir():
                        continue
                    raise DemoError("The ZIP contains an invalid entry.")
                if any(_is_blocked_path_part(part) for part in parts):
                    raise DemoError(
                        "The ZIP contains a restricted truth or attacker path."
                    )

                relative_name = "/".join(parts)
                key = relative_name.casefold()
                if key in seen:
                    raise DemoError("The ZIP contains duplicate paths.")
                seen.add(key)

                mode = (info.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode)
                if file_type == stat.S_IFLNK or file_type not in (
                    0,
                    stat.S_IFREG,
                    stat.S_IFDIR,
                ):
                    raise DemoError("The ZIP contains an unsupported file type.")
                if info.flag_bits & 0x1:
                    raise DemoError("Encrypted ZIP entries are not supported.")

                target = destination.joinpath(*parts)
                try:
                    target.resolve().relative_to(root)
                except ValueError:
                    raise DemoError("The ZIP contains an unsafe path.") from None

                if info.is_dir():
                    if file_type not in (0, stat.S_IFDIR):
                        raise DemoError("The ZIP contains an invalid directory.")
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if file_type == stat.S_IFDIR:
                    raise DemoError("The ZIP contains an invalid file entry.")
                if info.file_size < 0 or info.file_size > MAX_MEMBER_BYTES:
                    raise DemoError("A ZIP entry exceeds the permitted size.")
                declared_total += info.file_size
                if declared_total > MAX_ARCHIVE_BYTES:
                    raise DemoError("The expanded ZIP exceeds the permitted size.")

                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with archive.open(info, "r") as source, target.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        written += len(chunk)
                        actual_total += len(chunk)
                        if written > MAX_MEMBER_BYTES:
                            raise DemoError(
                                "A ZIP entry exceeds the permitted size."
                            )
                        if actual_total > MAX_ARCHIVE_BYTES:
                            raise DemoError(
                                "The expanded ZIP exceeds the permitted size."
                            )
                        output.write(chunk)
                if written != info.file_size:
                    raise DemoError("A ZIP entry failed integrity validation.")
                file_count += 1

    except zipfile.BadZipFile:
        raise DemoError("The uploaded file is not a valid ZIP archive.") from None
    except (RuntimeError, EOFError):
        raise DemoError("The ZIP archive could not be safely read.") from None

    if file_count == 0:
        raise DemoError("The ZIP archive contains no files.")
    return file_count


def _sanitized_archive(sanitized_dir: Path) -> bytes | None:
    files = sorted(path for path in sanitized_dir.rglob("*") if path.is_file())
    if not files:
        return None

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if path.is_symlink():
                raise DemoError("Sanitized output contains an unsafe file.")
            relative = path.relative_to(sanitized_dir)
            if ".." in relative.parts:
                raise DemoError("Sanitized output contains an unsafe path.")
            archive.write(path, relative.as_posix())
    return buffer.getvalue()


def _pseudonym_counts(records_data: bytes | None) -> Counter[str] | None:
    if records_data is None:
        return None

    counts: Counter[str] = Counter()
    try:
        for line in records_data.decode("utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                continue
            patient = record.get("patient")
            if isinstance(patient, str) and PSEUDONYM_PATTERN.fullmatch(patient):
                counts[patient] += 1
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return counts


def _run_cli(payload: bytes, secret: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="apex-raksha-") as temporary:
        work = Path(temporary)
        input_dir = work / "input"
        output_dir = work / "output"
        input_dir.mkdir()
        _extract_zip(payload, input_dir)

        environment = os.environ.copy()
        environment["RAKSHA_SECRET"] = secret
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MAIN_SCRIPT),
                    "--input",
                    str(input_dir),
                    "--output",
                    str(output_dir),
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=900,
            )
        except subprocess.TimeoutExpired:
            raise DemoError("The local Raksha run timed out; no results are shown.") from None

        if completed.returncode != 0:
            raise DemoError(
                f"The local Raksha CLI failed (exit code {completed.returncode}); "
                "no results are shown."
            )

        sanitized_dir = output_dir / "sanitized"
        report_path = output_dir / "report.json"
        if not sanitized_dir.is_dir() or not report_path.is_file():
            raise DemoError(
                "The CLI exited successfully but expected output files are missing."
            )

        try:
            report_bytes = report_path.read_bytes()
            report = json.loads(report_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise DemoError("The generated report is missing or invalid.") from None
        if (
            not isinstance(report, dict)
            or report.get("schema") != "raksha-report/1"
            or not isinstance(report.get("counts"), dict)
        ):
            raise DemoError("The generated report has an unsupported format.")

        records_path = output_dir / "records.jsonl"
        records_data = records_path.read_bytes() if records_path.is_file() else None
        return {
            "report": report,
            "report_download": report_bytes,
            "records_download": records_data,
            "sanitized_zip": _sanitized_archive(sanitized_dir),
            "pseudonyms": _pseudonym_counts(records_data),
        }


def _metric_value(counts: dict, key: str) -> str:
    value = counts.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return "Not reported"


def _render_results(result: dict[str, object]) -> None:
    report = result["report"]
    counts = report["counts"]
    st.markdown("### Run results")
    st.caption("Values below are read from the local pipeline report.")

    metrics = (
        ("Files processed", "files_total"),
        ("Files sanitised", "files_sanitized"),
        ("Files quarantined", "files_quarantined"),
        ("Records processed", "records_processed"),
        ("Identifiers detected", "identifiers_detected"),
        ("Records linked", "records_linked"),
    )
    for row_start in range(0, len(metrics), 3):
        columns = st.columns(3)
        for column, (label, key) in zip(columns, metrics[row_start:row_start + 3]):
            column.metric(label, _metric_value(counts, key))

    secondary = st.columns(3)
    secondary[0].metric(
        "Records generalised", _metric_value(counts, "records_generalized")
    )
    timing = report.get("timing")
    seconds = timing.get("seconds") if isinstance(timing, dict) else None
    secondary[1].metric(
        "Processing time",
        f"{seconds:g} s" if isinstance(seconds, (int, float)) else "Not reported",
    )
    resources = report.get("resources")
    peak_rss = resources.get("peak_rss_mb") if isinstance(resources, dict) else None
    secondary[2].metric(
        "Peak memory",
        f"{peak_rss:g} MB" if isinstance(peak_rss, (int, float)) else "Not reported",
    )

    entities = report.get("entities")
    st.markdown("#### Detected PII categories")
    if isinstance(entities, dict) and entities:
        st.dataframe(
            [
                {"Category": str(category), "Detections": int(amount)}
                for category, amount in sorted(entities.items())
                if isinstance(amount, int) and not isinstance(amount, bool)
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("Not reported.")

    st.markdown("#### Patient pseudonymisation")
    pseudonyms = result.get("pseudonyms")
    if isinstance(pseudonyms, Counter) and pseudonyms:
        st.caption(
            f"{sum(pseudonyms.values()):,} linked records across "
            f"{len(pseudonyms):,} pseudonyms."
        )
        st.dataframe(
            [
                {"Patient pseudonym": patient, "Records": amount}
                for patient, amount in sorted(pseudonyms.items())[:8]
            ],
            hide_index=True,
            width="stretch",
        )
    elif result.get("records_download") is None:
        st.caption("Pseudonymisation records were not generated.")
    else:
        st.caption("No patient pseudonyms were reported.")

    files = report.get("files")
    quarantined = [
        entry
        for entry in files
        if isinstance(entry, dict) and entry.get("status") == "quarantined"
    ] if isinstance(files, list) else []
    st.markdown("#### Quarantine")
    if quarantined:
        st.warning(f"{len(quarantined):,} file(s) were quarantined, not sanitised.")
        reasons = Counter(
            entry["reason"]
            for entry in quarantined
            if isinstance(entry.get("reason"), str)
        )
        if reasons:
            st.caption(
                "Reported reasons: "
                + ", ".join(
                    f"{reason} ({amount})"
                    for reason, amount in sorted(reasons.items())
                )
            )
        st.caption(
            "Source filenames are not included in this report; quarantined "
            "contents are not displayed or downloaded."
        )
    else:
        st.success("No files were quarantined.")

    st.markdown("#### Downloads")
    downloads = st.columns(3)
    sanitized_zip = result.get("sanitized_zip")
    if isinstance(sanitized_zip, bytes):
        downloads[0].download_button(
            "Sanitised output ZIP",
            sanitized_zip,
            file_name="raksha_sanitized.zip",
            mime="application/zip",
        )
    report_download = result.get("report_download")
    if isinstance(report_download, bytes):
        downloads[1].download_button(
            "report.json",
            report_download,
            file_name="report.json",
            mime="application/json",
        )
    records_download = result.get("records_download")
    if isinstance(records_download, bytes):
        downloads[2].download_button(
            "records.jsonl",
            records_download,
            file_name="records.jsonl",
            mime="application/x-ndjson",
        )


def _clear_result() -> None:
    st.session_state.pop("run_result", None)
    st.session_state["engine_status"] = "LOCAL CLI · READY"


def main() -> None:
    st.set_page_config(
        page_title="APEX | RAKSHA",
        page_icon="◆",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
        :root { color-scheme: dark; }
        .stApp, [data-testid="stAppViewContainer"] {
            background: #101113;
            color: #ece9e1;
        }
        [data-testid="stHeader"] { background: rgba(16, 17, 19, .92); }
        [data-testid="stToolbar"] { right: 1.5rem; }
        .block-container { max-width: 1160px; padding-top: 2rem; padding-bottom: 4rem; }
        h1, h2, h3 { color: #f0ede6; letter-spacing: -.025em; }
        .apex-brand { font-size: 1rem; letter-spacing: .22em; font-weight: 700; }
        .apex-brand span { color: #c9a96e; padding: 0 .45rem; }
        .apex-subtitle { color: #c9a96e; font-size: 1.15rem; margin-top: .55rem; }
        .apex-description { color: #a7a49d; margin-top: .35rem; }
        .apex-status {
            display: inline-block; border: 1px solid #494336; color: #d7bd88;
            border-radius: 999px; padding: .38rem .75rem; font-size: .75rem;
            letter-spacing: .09em; background: #191915;
        }
        .apex-rule { height: 1px; background: #343331; margin: 1.5rem 0 2rem; }
        .apex-card {
            background: #17181a; border: 1px solid #303033; border-radius: 12px;
            padding: 1rem 1.1rem; min-height: 112px; margin-bottom: .65rem;
        }
        .apex-card-title { color: #e6d3ac; font-weight: 600; margin-bottom: .35rem; }
        .apex-card-copy { color: #aaa7a0; font-size: .88rem; line-height: 1.45; }
        .stButton > button[kind="primary"] {
            background: #c9a96e; color: #161513; border: 0; font-weight: 700;
            letter-spacing: .08em; min-height: 3rem;
        }
        .stButton > button[kind="primary"]:hover { background: #ddc18d; color: #161513; }
        div[data-testid="stMetric"] {
            background: #17181a; border: 1px solid #303033; padding: .85rem;
            border-radius: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    status = st.session_state.get("engine_status", "LOCAL CLI · READY")
    left, right = st.columns([4, 1])
    with left:
        st.markdown('<div class="apex-brand">APEX <span>|</span> RAKSHA</div>', unsafe_allow_html=True)
        st.markdown('<div class="apex-subtitle">Healthcare Data Privacy Firewall</div>', unsafe_allow_html=True)
        st.markdown('<div class="apex-description">Offline. Deterministic. Privacy-preserving.</div>', unsafe_allow_html=True)
    with right:
        st.markdown(
            f'<div class="apex-status">{status}</div>',
            unsafe_allow_html=True,
        )
    st.markdown('<div class="apex-rule"></div>', unsafe_allow_html=True)

    st.markdown("### Privacy controls, applied locally")
    capabilities = (
        ("PII detection", "Identifies supported personal and healthcare identifiers."),
        ("Identity pseudonymisation", "Uses consistent patient pseudonyms where linkable."),
        ("Clinical preservation", "Retains supported clinical information during sanitisation."),
        ("Sensitive data sanitisation", "Applies the existing Raksha rules to uploaded files."),
        ("Unsupported-file quarantine", "Separates unsupported or failed files from sanitised output."),
        ("Structured output", "Generates the existing report and records formats."),
    )
    for start in range(0, len(capabilities), 3):
        columns = st.columns(3)
        for column, (title, copy) in zip(columns, capabilities[start:start + 3]):
            column.markdown(
                f'<div class="apex-card"><div class="apex-card-title">{title}</div>'
                f'<div class="apex-card-copy">{copy}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("### Run a local sanitisation")
    st.caption(
        "Upload a ZIP of healthcare export files. The archive is processed in a "
        "temporary directory and is not retained in the repository."
    )
    uploaded = st.file_uploader(
        "Healthcare export ZIP",
        type=["zip"],
        accept_multiple_files=False,
        on_change=_clear_result,
        key="input_zip",
    )
    secret = st.text_input(
        "Raksha secret",
        type="password",
        help="Passed only to the local CLI through the RAKSHA_SECRET environment variable.",
        key="raksha_secret",
        on_change=_clear_result,
    )
    run_clicked = st.button(
        "RUN PRIVACY FIREWALL",
        type="primary",
        disabled=uploaded is None or not secret,
    )

    if run_clicked:
        lock = _execution_lock()
        if not lock.acquire(blocking=False):
            st.error("A local Raksha run is already in progress. Please wait.")
        else:
            st.session_state.pop("run_result", None)
            st.session_state["engine_status"] = "LOCAL CLI · RUNNING"
            try:
                if uploaded.size > MAX_UPLOAD_BYTES:
                    raise DemoError("The ZIP exceeds the 200 MB upload limit.")
                with st.spinner("Executing the existing Raksha CLI locally…"):
                    result = _run_cli(uploaded.getvalue(), secret)
                st.session_state["run_result"] = result
                st.session_state["engine_status"] = "LOCAL CLI · COMPLETE"
                st.success("Raksha completed. Results below are from report.json.")
            except DemoError as exc:
                st.session_state["engine_status"] = "LOCAL CLI · FAILED"
                st.error(str(exc))
            except (OSError, zipfile.BadZipFile, subprocess.SubprocessError):
                st.session_state["engine_status"] = "LOCAL CLI · FAILED"
                st.error("Local processing failed. No results are presented as successful.")
            finally:
                lock.release()

    result = st.session_state.get("run_result")
    if isinstance(result, dict):
        st.markdown('<div class="apex-rule"></div>', unsafe_allow_html=True)
        _render_results(result)


if __name__ == "__main__":
    main()
