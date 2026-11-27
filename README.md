# Raksha Firewall (Team Apex)

**Track 3: Secret Wards.** An offline, CPU-only privacy firewall for Indian hospital exports in English, Hindi and Hinglish. It removes personal data, keeps medical values exact, gives each patient one keyed pseudonym across files, scripts and hospitals, and refuses to export anything it cannot clean.

- Python 3.10+ **standard library only**. No LLM, no trained model, no model files, no network calls.
- Same input and same `RAKSHA_SECRET` give byte-identical output. A different secret gives different pseudonyms and date shifts.

## Results on the practice dataset

200 files, 778 records. Measured with the organizers' `check_dev.py`. We tuned on this data, so hidden-data scores will differ.

| Measure | Result |
|---|---|
| Personal data still visible | 0.1% (2 of 3,230). Latin 0.1%, Hindi 0.0%, Hinglish 0.0% |
| Hidden places (file names, keys, headers, base64, metadata) | 0.0% leaked |
| Planted canaries found | 0 of 4 |
| Medical values kept | 4,854 of 4,855 (99.98%) |
| Linking precision / recall / F0.5 | 1.00 / 0.97 / 0.99, with 0 wrong merges |
| Records linked | 769 of 778 |
| Raw copies of unsupported files | 0 |
| Run time / peak memory | 3.2 s / 24 MB. At 10x the data: 29.6 s / 67 MB (near-linear) |
| Different secret | 0 of 55 pseudonyms repeat |
| Patients unique on the fields we release (practice registry, 240 people) | 95.8% on raw fields, 39.6% on released fields, 0% for rare-diagnosis records |

## Quick start

```bash
# setup (nothing to install: standard library only)
python3 -m pip install -r requirements.txt

# run
export RAKSHA_SECRET="a-long-random-secret"
python3 main.py --input PATH_TO_INPUT --output EMPTY_OUTPUT_FOLDER

# tests
python3 -m unittest
```

On Windows PowerShell use `$env:RAKSHA_SECRET="..."` and `python`.

The output folder must be empty and must not be inside the input folder. The secret is read from the environment and never written anywhere.

Output contract:

```text
output/
  sanitized/     cleaned files, same folders and formats as the input
  report.json    every input file by SHA-256, status, reason code, totals, timing, memory
  records.jsonl  which record belongs to which pseudonym ("patient": null when unsure)
```

Optional demo UI: `pip install -r requirements-ui.txt` then `streamlit run app.py`. It calls the same command-line pipeline.

## Architecture

```text
input files
  -> 1 ingestion      decode, parse, quarantine anything doubtful
  -> 2 pass 1 (learn) field roles from labels, context cues, identity clues, name/place lexicon
  -> 3 linkage        identifiers -> phone -> name + corroboration; conflicts veto a merge
  -> 4 pseudonyms     HMAC-SHA256(secret, cluster key)
  -> 5 pass 2         redact, per-patient date shift, age band, location, rare-record widening
  -> 6 residual scan  any surviving phone/Aadhaar/e-mail/PAN quarantines the file
  -> sanitized/  report.json  records.jsonl
```

| Module | Responsibility |
|---|---|
| `ingestion.py` | UTF-8 (BOM), UTF-16, cp1252; safe reason codes for unreadable files |
| `fields.py` | Role of a column or JSON key from the words in its label |
| `detection.py` | Identifiers, address parts and names from context in free text |
| `textutil.py` | Devanagari transliteration and phonetic name matching |
| `records.py` | Record locators, nested JSON, FHIR rules, base64 |
| `linkage.py` | Conservative clustering |
| `redaction.py` | Clue harvesting (pass 1) and replacement (pass 2) |
| `dates.py` | Date formats and style-preserving shifting |
| `pseudonymization.py` | Keyed pseudonyms and date offsets |
| `engine.py` | Two-pass orchestration, file names, quarantine |
| `validation.py` | Final residual-identifier scan |
| `reporting.py` | `report.json` and `records.jsonl` (never contain source values) |

## How detection works

There is **no built-in list of names, villages or hospitals**. Names are found from structure and context, so new names and labels in unseen data go through the same rules.

- **Rules:** phones in any grouping (including Devanagari digits), Aadhaar (full and masked), ABHA, PAN, UHID/MRN/IPD, insurance IDs, e-mail, PIN, house, locality, landmark, village, tehsil.
- **Field roles:** the words of a column or JSON key decide its meaning, so labels such as "Next of Kin", "Gram/Mohalla" or "Contact#" still resolve.
- **Context cues:** `S/o`, `D/o`, `W/o`, `C/O`, honorifics (ji, sahab, didi), Hinglish and Hindi particles, chat senders, contacts beside phone numbers.
- **Learned lexicon:** every name found anywhere is searched in all files, across spellings and scripts (Mohammad / Mohd / Md. / the Devanagari spelling), using phonetic keys and rule-based Devanagari to Latin transliteration.
- **Meaning traps:** "C/O fever" is kept and "C/O Baldev" is removed. Names after Dr., eponymous diseases (Parkinson's) and ASHA workers are protected. Doses such as "Dolo 650" and frequencies such as "1-0-1" are never read as IDs.
- **Hidden places:** JSON keys, CSV headers, file names and base64 payloads (including FHIR attachments) are cleaned too. A file name carrying a name or long number is renamed and the new name is recorded in the report.

## Linking

1. Shared identity number (Aadhaar, ABHA, hospital number, PAN, insurance, e-mail) with compatible names.
2. Shared phone with compatible names.
3. Same name plus a relative, date of birth, or village and age. Name blocking uses phonetic keys.
4. "Name, W/o X" fragments join only when exactly one candidate fits.

Conflicting names, birth dates or Aadhaar numbers veto a merge. Records that name several people (logs, indexes) are never linked. Weak evidence gives `"patient": null`, because a wrong link costs more than no link.

## Privacy decisions

| Data | Treatment |
|---|---|
| Names, phones, identity numbers | removed, or replaced by the pseudonym |
| Date of birth | removed |
| Dates | one secret offset per patient (15 to 180 days, either direction); intervals and stay lengths unchanged |
| Age | 5-year band, always containing the true age; 90 and above becomes `90+` |
| House, locality, landmark, village, tehsil | removed |
| District, 3-digit PIN prefix | kept |
| Rare diagnosis (ICD-10 code held by 2 patients or fewer) | 20-year age band; district and PIN removed |
| Clinical values, doctors, hospitals | kept exactly |

All rules are in `config/policy.yaml` (`age_band_years`, `wide_age_band_years`, `date_shift_min_days`, `date_shift_max_days`, `rare_diagnosis_max_patients`, `pin_digits_kept`, and limits). An operator can trade utility for privacy without touching code.

## Security design

- **Key handling:** `RAKSHA_SECRET` lives only in the environment. Pseudonyms, date offsets and renamed files use HMAC-SHA256 with separate domains, so pseudonyms cannot be inverted by hashing known IDs.
- **Nothing staged on disk:** both passes run in memory and no temporary files are written, so a breached server holds no intermediate data.
- **Raw data stays raw:** input is read-only and never copied out. Quarantined files are not copied anywhere.
- **PII-free logs:** one summary line of counts; errors print only an exception class or a fixed reason code.
- **Fail closed:** a final scan re-checks every output; any surviving phone, Aadhaar, e-mail or PAN quarantines that file instead of exporting it.
- **Cross-release safety:** a new secret changes every pseudonym and date shift.
- **Deployment note:** the pipeline does not encrypt the raw input store. Keep raw data on an encrypted volume, keep the key in a separate secret store, and rotate the key for each release.

## Quarantine reason codes

`unsupported_format`, `undecodable_text`, `binary_or_corrupt`, `empty_file`, `format_mismatch`, `malformed_json`, `malformed_table`, `excessive_nesting`, `file_too_large`, `symbolic_link`, `residual_identifier_detected`, `processing_error`.

## Declared models and ground rules

| Rule | Status |
|---|---|
| No LLM or generative model | None used |
| Trained models | None. Detection is rules, field-role logic and a lexicon learned from the input itself |
| Offline, CPU-only | Standard library only; no network access anywhere in `rakshak/` |
| No hardcoding | No patient, village or hospital names in code, only language-level words (stop words, honorifics, generic name parts such as Kumar and Devi) |
| Synthetic data only | Practice data from the organizers; our tests use made-up records |
| Reproducible | Same input and secret give identical output |

## Known limitations

- A name that appears only in unlabelled free text, with no cue and no mention elsewhere, can be missed.
- Ages in free text are banded only in recognised patterns ("52/M", "Age: 52", Hindi "47-year-old" forms). A bare Hindi "47 years." phrase can keep an exact age.
- Transliteration is rule-based and covers Devanagari and Latin only. There is no trained NER.
- XML, PDF and images are quarantined, not parsed.
- Rarity uses ICD-10 codes found in the same release. It is not a formal k-anonymity guarantee.
- Generalisation alone is not anonymity: on the practice registry, 39.6% of patients are still unique on the released fields. Exact stay length and rare diagnoses keep targeted attacks possible (reduced, not eliminated).
- Scores on the practice data overstate performance on unseen data.

## Repository layout

```text
raksha.toml  requirements.txt  main.py  app.py (optional demo UI)
config/policy.yaml
rakshak/     the pipeline modules above
tests/       unit and end-to-end tests
docs/        architecture notes (put brief.pdf here)
```
