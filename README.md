# Evalvia — Smart Question Paper Generator

Evalvia is a local FastAPI demo for creating Maths and Science assessment drafts from a reviewed question bank. The bundled sample bank contains 148 questions (71 Maths and 77 Science) and supports a feasible 100-mark paper for either subject under the default blueprint. It is designed to expose constraint conflicts instead of silently claiming that every requested paper is feasible.

## Run locally (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Open http://127.0.0.1:8000

## Features

- Generate Maths or Science papers with a requested total from 1–300 marks.
- Configure exam title, class/grade, duration, instructions, difficulty mix, topic weights, and question-type mix.
- Mixes are measured by marks and normalized automatically. A category explicitly set to 0% is excluded; positive distribution targets remain soft preferences.
- Report requested versus achieved marks, distribution mismatch, limited category pools, and missing answer keys.
- Keep a draft marked **INCOMPLETE — DO NOT PUBLISH** when the exact total is not achievable.
- Preview import validation before activating a JSON or CSV question bank. Import checks required fields, supported categories, whole-number marks, MCQ options/answer consistency, case-insensitive unique IDs, and size limits.
- Persist a validated uploaded question bank across server restarts in `data/active_questions.json`. Use **Restore sample bank** to reset it.
- Display available question counts and the sum of marks for the selected subject. This sum is an upper bound, not a guarantee that every total can be formed.
- Extract selectable text from an optional PDF as reference material, with size/page/text limits. It does not automatically create questions; scanned PDFs need OCR, which is not included.
- Propose same-topic Medium-question pairings as **review-only compound-question candidates**. They are not automatically inserted or labelled Hard; a teacher must check conceptual connection, marks, answer, syllabus fit, and reasoning demand.
- Replace a question while preserving other question contents. If no exact attribute match exists, show same-mark alternatives and ask for approval before changing difficulty/topic/type.
- Group the assessment by question type in the preview and printable paper.
- Keep student exports separate from the teacher answer-key export. PDF output uses the browser print dialog: choose **Save as PDF**.
- Include a final quality-gate report. A complete mark total does not prove that answers are correct or that difficulty labels are valid; teacher review remains required.

## Question bank format

Required fields: `id`, `subject`, `topic`, `difficulty`, `question_type`, `marks`, `question`.

- Subjects: `Maths`, `Science`
- Difficulties: `Easy`, `Medium`, `Hard`
- Types: `MCQ`, `Short Answer`, `Long Answer`
- Marks: whole number from 1 to 100 per question
- MCQs: at least two unique options. For CSV, separate options with `|`.
- `answer` is optional for imports, but missing answers trigger a warning. For MCQs, the answer should match an option value or its letter label (A, B, C, ...).
- Maximum upload: 5 MB and 300 questions.

A starter schema is included in `question_bank_template.csv`.

## API routes

- `GET /api/health`
- `GET /api/options`
- `GET /api/capacity/{subject}`
- `POST /api/generate`
- `POST /api/swap`
- `POST /api/synthesis-proposals`
- `POST /api/validate-bank` (preview validation; does not activate)
- `POST /api/upload-bank` (validate and persist)
- `POST /api/reset-bank`
- `POST /api/upload-textbook`
- `GET /api/textbook-status`

## Important limitations

- This is a local demo without user authentication or multi-user isolation. Do not expose it directly to the public internet without adding appropriate access control and deployment hardening.
- Similarity checks use explicit similarity groups and normalized text comparison. They are not a semantic proof that two questions test different skills.
- Synthesis proposals pair Medium questions from the same topic only as a starting point. The system cannot infer that they form a genuinely integrated Hard question without additional concept metadata and teacher review.
- Answer-key presence and MCQ option membership are checked, but mathematical correctness, fairness, grade appropriateness, and marking-scheme quality are not fully automatable here.
- Uploaded textbook text is kept in memory for the current server process. Question banks persist locally; keep `data/active_questions.json` private if the bank contains proprietary material.
- PDF output uses browser print. OCR and server-side PDF generation are not included.

## Tests

```powershell
python -m pytest -q
```
