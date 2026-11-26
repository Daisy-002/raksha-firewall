import csv
import hashlib
import io
import json
import os
import re
import time
from pathlib import Path

from .discovery import discover_files, is_supported
from .ingestion import read_file
from .linkage import canonical_patient_key
from .pseudonymization import pseudonym
from .dates import shift_date_string
from .generalization import generalize_value
from .risk import safe_filename
from .reconstruction import write_csv, write_json
from .quarantine import quarantine_reason
from .reporting import write_report
from .validation import find_residual_identifiers
from .detection import PATTERNS, is_date_field, sanitize_value
from .normalization import normalize_key


PRIVATE_INDEX_FIELDS = {
    "byname", "byuhid", "bypatientname", "bypatientid", "nameindex",
}
GENERIC_HEADER_WORDS = {
    "address", "admission", "age", "amount", "bed", "blood", "body",
    "claim", "clinic", "code", "date", "department", "diagnosis",
    "discharge", "doctor", "dose", "duration", "email", "family",
    "first", "frequency", "full", "gender", "general", "given",
    "height", "heart", "history", "hospital", "insurance", "lab",
    "last", "management", "medical", "medication", "middle", "mobile",
    "name", "no", "notes", "number", "oxygen", "patient", "phone",
    "pin", "policy", "postal", "pressure", "pulse", "rate", "record",
    "reference", "remarks", "respiratory", "result", "sample", "sex",
    "state", "status", "saturation", "temperature", "test", "time",
    "total", "type", "unit", "value", "visit", "ward", "weight",
}
PERSON_LIKE_HEADER = re.compile(
    r"^[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3}$"
)


class PipelineStats:
    def __init__(self):
        self.identifiers = 0
        self.generalized = 0
        self.entities = {}


def _peak_memory_mb():
    try:
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if os.uname().sysname == "Darwin":
            return round(value / 1024 / 1024, 2)
        return round(value / 1024, 2)
    except Exception:
        return 0.0


def _safe_relative_path(relative: str, digest: str):
    parts = Path(relative).parts
    safe_parts = []

    for index, part in enumerate(parts):
        safe_parts.append(safe_filename(part, digest + str(index)))

    return Path(*safe_parts)


def _safe_csv_header(value, index):
    header = str(value).strip()
    if any(pattern.search(header) for pattern in PATTERNS.values()):
        return f"column_{index + 1}"

    words = header.split()
    if (
        PERSON_LIKE_HEADER.fullmatch(header)
        and not any(word.casefold() in GENERIC_HEADER_WORDS for word in words)
    ):
        return f"column_{index + 1}"

    return value


def _clean_record(
    record,
    patient_key,
    stats,
    maximum_shift,
    name_context=False,
    reference_context=False,
    narrative_context=False,
):
    cleaned = {}
    patient_id = pseudonym(patient_key) if patient_key else None

    for key, value in record.items():
        key_string = str(key)
        original_value = value
        normalized = normalize_key(key_string)

        # These maps expose direct name-to-identifier relationships.
        if normalized in PRIVATE_INDEX_FIELDS:
            continue

        safe_key = key_string
        nested_name_context = name_context or normalized == "name"
        nested_reference_context = reference_context or normalized == "subject"
        nested_narrative_context = narrative_context or normalized == "text"
        if reference_context and normalized == "display":
            field_to_clean = "name"
        elif reference_context and normalized == "reference":
            field_to_clean = "patientref"
        elif narrative_context and normalized == "div":
            field_to_clean = "fhir_narrative"
        elif name_context and normalized in {
            "text", "given", "family", "prefix", "suffix"
        }:
            field_to_clean = "name"
        else:
            field_to_clean = key_string

        if isinstance(value, dict):
            value = _clean_record(
                value,
                patient_key,
                stats,
                maximum_shift,
                nested_name_context,
                nested_reference_context,
                nested_narrative_context,
            )

        elif isinstance(value, list):
            value = [
                _clean_record(
                    x,
                    patient_key,
                    stats,
                    maximum_shift,
                    nested_name_context,
                    nested_reference_context,
                    nested_narrative_context,
                )
                if isinstance(x, dict)
                else sanitize_value(field_to_clean, x, stats)
                for x in value
            ]

        elif isinstance(value, str):
            value = sanitize_value(field_to_clean, value, stats)

            if patient_key and is_date_field(key_string):
                value = shift_date_string(value, patient_key, maximum_shift)

            generalized = generalize_value(key_string, value)
            if generalized != value:
                stats.generalized += 1
            value = generalized

        else:
            generalized = generalize_value(key_string, value)
            if generalized != value:
                stats.generalized += 1
            value = generalized

        if (
            reference_context
            and normalized == "reference"
            and isinstance(value, str)
            and isinstance(original_value, str)
        ):
            patient_reference = re.match(
                r"^Patient/([^/]+)", original_value
            )
            identifier = (
                patient_reference.group(1)
                if patient_reference
                else original_value
            )
            reference_key = canonical_patient_key(
                {"patientref": identifier}
            )
            if reference_key:
                value = pseudonym(patient_key or reference_key)
            else:
                value = "[REDACTED_ID]"

        # Replace an existing strong patient identifier with its pseudonym.
        if patient_id and normalized in {
            "patientid", "uhid", "mrn", "medicalrecordnumber",
            "patientref", "patientreference", "registrationid",
            "registrationnumber", "registrationno", "regno",
            "healthid", "abhaid", "रोगीआईडी", "पंजीकरणसंख्या",
            "आधारसंख्या", "आभाआईडी"
        }:
            value = patient_id

        cleaned[safe_key] = value

    return cleaned


def _extract_records(data):
    """
    Yield (locator, record) pairs.
    Handles common top-level arrays and FHIR Bundle entries.
    """
    if isinstance(data, dict):
        if data.get("resourceType") == "Bundle":
            entries = data.get("entry", [])
            for index, entry in enumerate(entries):
                if isinstance(entry, dict) and isinstance(entry.get("resource"), dict):
                    yield f"/entry/{index}/resource", entry["resource"]
            return

        found = False
        for key, value in data.items():
            if isinstance(value, list):
                for index, item in enumerate(value):
                    if isinstance(item, dict):
                        escaped = str(key).replace("~", "~0").replace("/", "~1")
                        yield f"/{escaped}/{index}", item
                        found = True

        if not found:
            yield "doc", data

    elif isinstance(data, list):
        for index, item in enumerate(data):
            if isinstance(item, dict):
                yield f"/{index}", item

    else:
        yield "doc", None


def _process_csv(text, delimiter, relative, records, stats, maximum_shift):
    parsed = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))

    if not parsed:
        raise ValueError("empty_file")

    header = parsed[0]
    safe_header = [
        _safe_csv_header(column, index)
        for index, column in enumerate(header)
    ]
    output_rows = [safe_header]

    for index, row in enumerate(parsed[1:]):
        record = {
            header[i]: row[i] if i < len(row) else ""
            for i in range(len(header))
        }

        key = canonical_patient_key(record)
        cleaned = _clean_record(record, key, stats, maximum_shift)

        output_row = [cleaned.get(column, "") for column in header]
        output_rows.append(output_row)

        records.append({
            "file": f"sanitized/{relative}",
            "loc": f"row:{index}",
            "patient": pseudonym(key) if key else None,
        })

    return write_csv(output_rows, delimiter)


def _process_json(text, relative, records, stats, maximum_shift):
    data = json.loads(text)
    processed_top_fields = set()

    for locator, record in _extract_records(data):
        if record is None:
            records.append({
                "file": f"sanitized/{relative}",
                "loc": locator,
                "patient": None,
            })
            continue

        key = canonical_patient_key(record)
        cleaned = _clean_record(record, key, stats, maximum_shift)

        # Replace the record in its original location.
        if locator == "doc":
            data = cleaned
            if isinstance(data, dict):
                processed_top_fields.update(data)
        elif locator.startswith("/entry/") and data.get("resourceType") == "Bundle":
            parts = locator.strip("/").split("/")
            data["entry"][int(parts[1])]["resource"] = cleaned
            processed_top_fields.add("entry")
        elif isinstance(data, dict):
            parts = locator.strip("/").split("/")
            array_name = parts[0].replace("~1", "/").replace("~0", "~")
            data[array_name][int(parts[1])] = cleaned
            processed_top_fields.add(array_name)
        elif isinstance(data, list):
            data[int(locator.strip("/"))] = cleaned

        records.append({
            "file": f"sanitized/{relative}",
            "loc": locator,
            "patient": pseudonym(key) if key else None,
        })

    if isinstance(data, dict):
        for key, value in list(data.items()):
            if key not in processed_top_fields:
                data[key] = _clean_record(
                    {key: value}, None, stats, maximum_shift
                )[key]

    return write_json(data)


def _process_text(text, relative, records, stats):
    cleaned = sanitize_value("clinical_note", text, stats)

    # Text documents are not linked by name alone.
    records.append({
        "file": f"sanitized/{relative}",
        "loc": "doc",
        "patient": None,
    })

    return cleaned


def run_pipeline(input_dir: Path, output_dir: Path):
    start = time.monotonic()

    if not input_dir.exists() or not input_dir.is_dir():
        raise ValueError("invalid_input_directory")

    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output_directory_not_empty")

    output_dir.mkdir(parents=True, exist_ok=True)
    sanitized_dir = output_dir / "sanitized"
    sanitized_dir.mkdir(parents=True, exist_ok=True)

    stats = PipelineStats()
    files_report = []
    records = []

    maximum_shift = 180
    policy_path = Path("config/policy.yaml")
    if policy_path.exists():
        for line in policy_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("date_shift_max_days:"):
                try:
                    maximum_shift = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass

    for path in discover_files(input_dir):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        relative = path.relative_to(input_dir).as_posix()

        entry = {"input_sha256": digest}

        try:
            if not is_supported(path):
                raise ValueError("unsupported_format")

            if not raw.strip():
                raise ValueError("empty_file")

            text = read_file(path)
            extension = path.suffix.lower()

            if extension in {".csv", ".tsv"}:
                result = _process_csv(
                    text,
                    "\t" if extension == ".tsv" else ",",
                    relative,
                    records,
                    stats,
                    maximum_shift,
                )
            elif extension == ".json":
                result = _process_json(
                    text, relative, records, stats, maximum_shift
                )
            else:
                result = _process_text(text, relative, records, stats)

            safe_relative = _safe_relative_path(relative, digest)
            destination = sanitized_dir / safe_relative
            destination.parent.mkdir(parents=True, exist_ok=True)

            # Independent residual scan. Fail closed if a high-confidence
            # identifier remains in the reconstructed output.
            if find_residual_identifiers(result):
                raise ValueError("residual_identifier_detected")

            destination.write_text(result, encoding="utf-8", newline="")

            output_name = "sanitized/" + safe_relative.as_posix()
            entry.update(output=output_name, status="sanitized")

        except Exception as exc:
            entry.update(
                output=None,
                status="quarantined",
                reason=quarantine_reason(exc),
            )

        files_report.append(entry)

    exported = {
        item["output"]
        for item in files_report
        if item.get("output")
    }
    records = [r for r in records if r["file"] in exported]

    elapsed = time.monotonic() - start

    write_report(
        output_dir,
        files_report,
        records,
        {
            "identifiers": stats.identifiers,
            "generalized": stats.generalized,
            "entities": stats.entities,
        },
        elapsed,
        _peak_memory_mb(),
    )

    print(
        "Raksha completed:",
        len(files_report),
        "files;",
        len(records),
        "records"
    )