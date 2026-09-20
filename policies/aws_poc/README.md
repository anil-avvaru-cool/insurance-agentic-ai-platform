# Synthetic AWS policy coverage corpus

Implements step 1 of [the AWS POC plan](../../docs/PHASE_1_AWS_POC_PLAN.md).
All identities and policy terms are fictional test data. Each PDF is one page,
uses a declarations layout with a coverage schedule and policy provisions,
contains selectable text, and includes consistently labeled metadata in a compact
document reference block for the later deterministic extraction step. A discreet
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

Metadata extraction, ingestion sidecars, AWS indexing, and running answer
quality evaluations belong to the later plan steps.
