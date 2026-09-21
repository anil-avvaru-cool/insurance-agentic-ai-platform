# Synthetic AWS policy coverage corpus

Implements steps 1 and 2 of [the AWS POC plan](../../docs/PHASE_1_AWS_POC_PLAN.md).
All identities and policy terms are fictional test data. Each PDF is one page,
uses a declarations layout with a coverage schedule and policy provisions,
contains selectable text, and includes consistently labeled metadata in a compact
document reference block for deterministic metadata extraction. A discreet
footer identifies each PDF as a sample document. Dates use ISO format; LOB values are
`auto` and `property`. The owner IDs match the existing local synthetic identities.

| Owner | Synthetic name | Auto PDF | Property PDF |
|---|---|---|---|
| `customer_one` (User 1) | Avery Sample | [Standard Auto](auto_user_1_v1.pdf) | [Standard Property](property_user_1_v1.pdf) |
| `customer_two` (User 2) | Jordan Example | [Standard Auto](auto_user_2_v1.pdf) | [Standard Property](property_user_2_v1.pdf) |

| Value | User 1 | User 2 |
|---|---|---|
| Auto bodily injury liability, per person / accident | $100,000 / $300,000 | $250,000 / $500,000 |
| Auto property damage liability, per accident | $50,000 | $100,000 |
| Collision deductible | $500 | $1,000 |
| Comprehensive deductible | $250 | $500 |
| Building limit, per covered loss | $300,000 | $500,000 |
| Personal belongings limit, per covered loss | $150,000 | $250,000 |
| Property deductible, per covered loss | $1,000 | $2,500 |

Auto liability has no deductible. Collision and comprehensive limits are the
vehicle's actual cash value less the applicable deductible. The Property
deductible applies once to combined building and belongings damage from the
same covered loss. Each document defines its covered events and exclusions.
Auto property damage liability covers other people's property; it is distinct
from the building and belongings coverage in the Property documents.

## Source and regeneration

[documents.json](documents.json) is the editable source for the PDFs, with
metadata and named passages. From the repository root:

```sh
uv sync --locked
uv run --locked python scripts/generate_poc_policies.py
```

Generation uses ReportLab, a development dependency, and produces reproducible
PDF bytes with fixed PDF metadata. `pypdf` is available for text verification.
After editing source content, regenerate the PDFs and update the expected
answers and exact supporting passages in the question fixtures together.

## Evaluation fixtures

[questions.json](questions.json) contains 36 cases: 24 supported questions,
eight unsupported questions, and four attempts to request another owner's
policy. Supported cases include exact passages and document IDs for citation
review. All passages are on page 1 of the corresponding PDF. `pair_id` groups
the same question across both owners; deductible and limit answers deliberately
differ. Unsupported cases have no supporting passage and must return
`insufficient_information`, without inventing a value.

A future evaluation runner should simulate or authenticate the case's owner,
select its LOB, compare answers semantically, and verify every citation against
`allowed_document_ids` and the supporting passages. Owner IDs in this file
are test inputs, not trusted authorization in a deployed API. Other-owner
cases must disclose no other owner's information. These fixtures specify
expected behavior; they do not establish that retrieval isolation works.

## Metadata extraction and validation

Run from the repository root after generating or changing PDFs:

```sh
PYTHONPATH=src uv run --locked python scripts/prepare_poc_metadata.py
PYTHONPATH=src uv run --locked python scripts/prepare_poc_metadata.py --check
PYTHONPATH=src:. uv run --locked python -m unittest discover -s tests/unit -p 'test_poc_metadata.py' -v
```

The first command parses the actual PDFs with `pypdf`, extracts exact labels in
`DOCUMENT REFERENCE`, and validates the entire corpus before writing any
sidecars. The second command performs the same validation and rejects missing
or stale sidecars without writing. Errors identify the document and correction
needed and exit nonzero. Existing sidecars must not be ingested after a failed
validation; run `--check` immediately before any future upload.

PDF parsing lives in `src/ingestion/pdf.py`; deterministic extraction and
validation live in `src/ingestion/metadata.py` and consume only text. No LLM or
AWS calls are involved. `documents.json` supplies the expected document values;
an independent policy-to-owner/LOB/product allowlist validates assignments.
Changing the POC policy inventory requires an explicit allowlist update.

| Field | Type and validation |
|---|---|
| `document_id` | Nonempty identifier; unique, matches PDF filename and reviewed source |
| `owner_id` | Stable owner identifier; must match the policy allowlist |
| `policy_id` | Unique policy identifier; one of the four approved policies |
| `product_name` | Nonempty string; Standard Auto or Standard Property for the policy |
| `lob` | Exact lowercase `auto` or `property`, matching the policy |
| `version` | Positive integer encoded as a string |
| `effective_date` | Valid calendar date in exact `YYYY-MM-DD` format |

All seven fields are required; duplicate or unknown labels fail validation.
Each `*.pdf.metadata.json` contains these string values under
`metadataAttributes`, following the
[AWS S3 metadata sidecar format](https://docs.aws.amazon.com/bedrock/latest/userguide/s3-data-source-connector.html).
Upload each sidecar alongside its matching PDF in the same S3 prefix in step 3.
Do not upload this README, the review record, or the JSON source/question fixtures.
The `owner_id` and `lob` attributes are prepared for mandatory combined retrieval
filters; extraction itself does not implement retrieval authorization.

### Metadata review record

On 2026-09-19, the extracted document reference values from all four PDFs were
compared against the following expected values and `documents.json`. All seven
fields matched. This was a review of selectable PDF text, not a rendered-page
visual review. All four have version `1` and effective date `2026-01-01`.

| Document ID | Owner ID | Policy ID | Product name | LOB |
|---|---|---|---|---|
| auto_user_1_v1 | customer_one | POC_AUTO_001 | Standard Auto | auto |
| property_user_1_v1 | customer_one | POC_PROPERTY_001 | Standard Property | property |
| auto_user_2_v1 | customer_two | POC_AUTO_002 | Standard Auto | auto |
| property_user_2_v1 | customer_two | POC_PROPERTY_002 | Standard Property | property |

For each future revision, compare every extracted field printed by the command
against the corresponding PDF's document reference block, correct mismatches,
and update this review record before ingestion. Automated source comparison
supplements that review.

The [offline ingestion command](../../docs/OFFLINE_INGESTION.md) implements step 3.
Successful AWS ingestion and step 4 retrieval checks remain deployment acceptance gates.
