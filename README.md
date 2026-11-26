
# Raksha Firewall

An offline, deterministic privacy firewall for heterogeneous Indian
healthcare exports.

## Features

- CSV, TSV, JSON and TXT ingestion
- UTF-8, UTF-8 BOM, UTF-16 and CP1252 decoding
- Indian phone, Aadhaar, PAN, ABHA and email detection
- Explicitly labelled patient and relative name detection
- Conservative identity resolution using strong identifiers
- HMAC-SHA256 pseudonymisation
- Deterministic per-patient date shifting
- Age generalisation
- Safe filename handling
- Quarantine of unsupported or unprocessable files
- Machine-readable report and record index

## Requirements

Python 3.10 or newer.

## Run

Set a secret before execution.

### macOS/Linux

```bash
export RAKSHA_SECRET="replace-with-a-long-random-secret"
python3 main.py --input PATH_TO_INPUT --output PATH_TO_OUTPUT
```

### Windows PowerShell

```powershell
$env:RAKSHA_SECRET = "replace-with-a-long-random-secret"
python main.py --input PATH_TO_INPUT --output PATH_TO_OUTPUT
```

The output directory must be empty or must not exist.

## Output

- `sanitized/`: transformed research release
- `report.json`: file-level processing report
- `records.jsonl`: record-level identity index

## Safety

The system does not use generative models or external services during
processing. It does not use names or phone numbers alone to link patients.
Unprocessable inputs are quarantined rather than copied into the release.
