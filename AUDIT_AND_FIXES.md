# Evalvia audit and fixes applied

## Implemented in this build

- Strict input validation for subject, marks, percentage ranges, mix values, instruction lengths, supported question taxonomy, question IDs, and MCQ structure.
- Zero-weight categories are excluded; positive mix targets are normalized and remain soft targets.
- Distribution reporting includes explicitly zero-weight categories so a 0% target can be compared with the achieved result.
- Exact mark totals are enforced when feasible. Infeasible papers remain partial drafts with a requested-versus-achieved report; no question is duplicated to fill the gap.
- Mark-weighted distribution scoring and warnings for category shortages and missing answer keys.
- Similarity checks preserve math operators during normalization and bound comparisons for unusually long questions. Similarity detection is heuristic, not semantic proof.
- Question-bank import validation endpoint (`/api/validate-bank`) is separate from activation (`/api/upload-bank`). Uploads have byte, row-count, field-length, taxonomy, option, and answer-consistency checks.
- Approved uploaded banks are written atomically and persist across server restarts. `/api/reset-bank` restores the bundled bank.
- Textbook PDF upload checks file signature, size, page count, and extraction length; image-only PDFs are reported as unsupported.
- Question replacement validates that the submitted paper matches the active bank. If an exact same-mark attribute match is unavailable, it returns suggestions first and requires explicit approval before using a changed topic/difficulty/type.
- Added review-only Medium-question pairing proposals. Proposals are not automatically inserted or labelled Hard.
- Student paper export and teacher answer-key export are separate. PDF/print and text output mark incomplete papers clearly and group questions by type.
- Exam details are passed through to generated paper metadata.
- Added regression tests for exact totals, zero-weight exclusions, invalid values, import validation, persistence, PDF validation, synthesis proposals, swap approval, and tampered swap payloads.

## Remaining limitations that are intentionally not claimed as solved

- The app is a local demo without authentication or multi-user isolation; do not expose it directly to the public internet.
- Similarity detection is text-based and can miss semantic duplicates or flag some legitimate variants. It does not understand whether two questions assess the same learning outcome.
- Pairing Medium questions from the same topic is only a candidate generator. It cannot prove that a compound question is genuinely Hard or conceptually integrated. Teacher approval is mandatory.
- Answer-key presence and MCQ answer membership are validated, but mathematical correctness, fairness, grade appropriateness, and marking-rubric quality still need human review or specialized verification.
- Scanned PDF OCR, automatic textbook-to-question generation, server-side PDF rendering, persistent textbook extraction, and a full audit-history database are not included.
- The capacity mark sum is an upper bound, not an exact solver proof of the maximum possible marks under all similarity conflicts.
