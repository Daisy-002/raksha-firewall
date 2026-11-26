
# Architecture

## Pipeline

1. Deterministic input discovery
2. Format and encoding validation
3. CSV, TSV, JSON and text ingestion
4. Unicode normalization
5. Schema-aware identifier detection
6. Conservative patient identity resolution
7. HMAC-SHA256 pseudonymisation
8. Patient-specific deterministic date shifting
9. Age generalisation
10. Structured reconstruction
11. Residual identifier scan
12. Quarantine on processing failure
13. Report and record-index generation

## Identity policy

Records are linked only when a single unambiguous strong patient identifier
is present. Names, addresses, age, diagnoses and phone numbers alone do
not establish identity.

Conflicting strong identifiers cause abstention.

## Privacy policy

Pseudonyms and date shifts are derived using a secret HMAC key. The secret
is never written to output files.

## Failure policy

Unsupported formats, malformed input and failed residual scans are
quarantined. Original content is never copied into the sanitized release.
