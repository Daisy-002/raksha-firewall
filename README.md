# Raksha Firewall

An offline, deterministic privacy firewall for Indian hospital exports in English,
Hindi and Hinglish. Python 3.10+ standard library only: no models, no network.

## Run

```bash
export RAKSHA_SECRET="a-long-random-secret"
python3 main.py --input PATH_TO_INPUT --output EMPTY_OUTPUT_FOLDER
python3 -m unittest
```

On Windows PowerShell use `$env:RAKSHA_SECRET="..."` and `python`.

## Architecture

```text
input -> ingestion (decode, parse, quarantine)
      -> pass 1: records -> field roles + context detection -> clues + name lexicon
      -> linkage (identifiers, then name + corroboration) -> keyed pseudonyms
      -> pass 2: redact, shift dates, generalise
      -> residual identifier scan (fail closed) -> sanitized/, report.json, records.jsonl
```

| Module | Responsibility |
|---|---|
| `ingestion.py` | UTF-8, UTF-16, cp1252; safe reason codes for unreadable files |
| `fields.py` | Role of a column or key from the words in its label |
| `detection.py` | Identifiers, address parts and names from context in free text |
| `textutil.py` | Devanagari transliteration and phonetic name matching |
| `records.py` | Record locators, nested JSON, FHIR rules, base64 |
| `linkage.py` | Conservative clustering |
| `redaction.py` | Clue harvesting and replacement |
| `dates.py` | Date formats and style-preserving shifting |
| `engine.py` | Two-pass orchestration and file names |
| `validation.py` | Final residual scan |

## How detection works

Names are never taken from a built-in name list. They are found from structure
(column and key labels) and context (labels, `S/o`, `W/o`, `C/O`, honorifics, Hinglish
and Hindi particles, chat senders, contacts beside phone numbers). Every name found
anywhere is then searched for in all files, across spellings and scripts. Doctor
names, eponymous diseases and ASHA workers are protected.

## Linking

1. Shared identity number (Aadhaar, ABHA, hospital number, PAN, insurance, email)
   with compatible names.
2. Shared phone with compatible names.
3. Same name plus a relative, date of birth, or village and age.
4. "Name, W/o X" fragments join only when exactly one candidate fits.

Conflicting names, birth dates or Aadhaar numbers veto a merge. Weak evidence gives
`"patient": null`.

## Privacy decisions

| Data | Treatment |
|---|---|
| Names, phones, identity numbers | removed or replaced with the pseudonym |
| Date of birth | removed |
| Dates | one secret offset per patient (15 to 180 days); intervals unchanged |
| Age | 5-year band; 90 and above becomes `90+` |
| House, locality, landmark, village, tehsil | removed |
| District, 3-digit PIN prefix | kept |
| Rare diagnosis (2 patients or fewer) | 20-year age band, district and PIN removed |
| Clinical values, doctors, hospitals | kept |

Rules are configured in `config/policy.yaml`.

## Security design

- Keys: `RAKSHA_SECRET` is read from the environment and never written.
- Pseudonyms and date offsets are HMAC-SHA256 with separate domains.
- Intermediate data stays in memory; no temporary files are written.
- Logs contain only counts. Errors become fixed reason codes.
- Quarantined files are not copied anywhere.
- The pipeline does not encrypt the input at rest. A deployment should keep raw data
  on an encrypted volume, keep the key in a separate secret store, and rotate the key
  for each release.

## Known limitations

- A name that appears only in unlabelled free text, with no contextual cue and no
  occurrence elsewhere, can be missed.
- Transliteration is rule based and covers Devanagari and Latin only.
- XML, PDF and images are quarantined.
- Rarity suppression uses ICD codes found in the same release; it is not a formal
  k-anonymity guarantee.
- Rare diagnoses and exact stay lengths remain, so targeted attacks are reduced,
  not eliminated.
- Scores measured on the practice data overstate performance on unseen data.
