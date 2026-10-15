from __future__ import annotations

import csv
import io
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from engine import generate_paper, swap_question

BASE = Path(__file__).resolve().parent
DEFAULT_BANK_PATH = BASE / "questions.json"
BANK_STORAGE_PATH = Path(os.getenv("EVALVIA_BANK_PATH", str(BASE / "data" / "active_questions.json")))
MAX_BANK_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_BANK_QUESTIONS = 300
MAX_PDF_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_EXTRACTED_TEXT = 100_000

with DEFAULT_BANK_PATH.open(encoding="utf-8") as f:
    QUESTION_BANK: list[dict[str, Any]] = json.load(f)


def _load_active_bank() -> list[dict[str, Any]]:
    if BANK_STORAGE_PATH.exists():
        try:
            candidate = json.loads(BANK_STORAGE_PATH.read_text(encoding="utf-8"))
            return _validate_uploaded_bank(candidate)
        except (OSError, json.JSONDecodeError, ValueError):
            return list(QUESTION_BANK)
    return list(QUESTION_BANK)


ACTIVE_QUESTION_BANK: list[dict[str, Any]] = list(QUESTION_BANK)
TEXTBOOK_SOURCE: dict[str, Any] | None = None

app = FastAPI(
    title="Evalvia Smart Question Paper Generator",
    version="2.0.0",
    description="Constraint-aware Maths and Science question paper generation.",
)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


class Mixes(BaseModel):
    difficulty: dict[str, float] = Field(default_factory=lambda: {"Easy": 30, "Medium": 50, "Hard": 20})
    topic: dict[str, float] = Field(default_factory=dict)
    question_type: dict[str, float] = Field(default_factory=lambda: {"MCQ": 40, "Short Answer": 40, "Long Answer": 20})

    @field_validator("difficulty", "topic", "question_type", mode="before")
    @classmethod
    def reject_boolean_mix_values(cls, value: Any) -> Any:
        if isinstance(value, dict) and any(isinstance(number, bool) for number in value.values()):
            raise ValueError("Mix percentages must be numeric percentages, not booleans.")
        return value

    @field_validator("difficulty", "topic", "question_type")
    @classmethod
    def validate_mix_values(cls, value: dict[str, float]) -> dict[str, float]:
        for category, number in value.items():
            if not math.isfinite(number) or number < 0 or number > 100:
                raise ValueError(f"Percentage for {category} must be between 0 and 100.")
        if value and not any(number > 0 for number in value.values()):
            raise ValueError("Each non-empty mix must have at least one percentage greater than zero.")
        return value


class GenerateRequest(BaseModel):
    subject: str = "Maths"
    total_marks: int = Field(default=40, ge=1, le=300, strict=True)
    mixes: Mixes = Field(default_factory=Mixes)
    seed: int | None = 42
    exam_title: str = Field(default="Question Paper", max_length=160)
    class_name: str = Field(default="", max_length=100)
    duration: str = Field(default="2 hours", max_length=100)
    instructions: list[str] = Field(default_factory=lambda: ["Answer all questions.", "Write answers clearly."])

    @field_validator("subject")
    @classmethod
    def normalize_subject(cls, value: str) -> str:
        normalized = value.strip().title()
        if normalized not in {"Maths", "Science"}:
            raise ValueError("Subject must be Maths or Science.")
        return normalized

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, value: list[str]) -> list[str]:
        if len(value) > 20:
            raise ValueError("Use no more than 20 general instructions.")
        if any(len(line) > 500 for line in value):
            raise ValueError("Each instruction must be 500 characters or fewer.")
        return [line.strip() for line in value if line and line.strip()]


class SwapRequest(BaseModel):
    paper: dict[str, Any]
    question_id: str
    seed: int | None = 42
    allow_adjustment: bool = False


class SynthesisRequest(BaseModel):
    subject: str = "Maths"
    topic: str | None = None
    max_pairs: int = Field(default=10, ge=1, le=30)


@app.get("/")
def home():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/paper")
def paper_page():
    return FileResponse(BASE / "static" / "paper.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "question_count": len(ACTIVE_QUESTION_BANK), "subjects": sorted({q["subject"] for q in ACTIVE_QUESTION_BANK})}


@app.get("/api/options")
def options():
    result = {}
    for subject in ("Maths", "Science"):
        pool = [q for q in ACTIVE_QUESTION_BANK if q["subject"] == subject]
        result[subject] = {
            "topics": sorted({q["topic"] for q in pool}),
            "difficulties": sorted({q["difficulty"] for q in pool}),
            "question_types": sorted({q["question_type"] for q in pool}),
        }
    return result


@app.get("/api/capacity/{subject}")
def capacity(subject: str):
    normalized = subject.strip().title()
    if normalized not in {"Maths", "Science"}:
        raise HTTPException(status_code=422, detail="Subject must be Maths or Science.")
    pool = [q for q in ACTIVE_QUESTION_BANK if q["subject"] == normalized]
    return {
        "subject": normalized,
        "question_count": len(pool),
        "available_marks_sum": sum(int(q["marks"]) for q in pool),
        "largest_question_marks": max((int(q["marks"]) for q in pool), default=0),
        "topics": sorted({q["topic"] for q in pool}),
        "note": "The sum is an upper bound. Unique-question, duplicate, topic, and zero-weight exclusions can lower the feasible total.",
    }


@app.post("/api/generate")
def generate(req: GenerateRequest):
    try:
        subject_pool = [q for q in ACTIVE_QUESTION_BANK if q["subject"] == req.subject]
        if not subject_pool:
            raise ValueError(f"No questions are available for {req.subject}. Upload an eligible question bank.")
        raw = req.mixes.model_dump()
        mixes: dict[str, dict[str, float]] = {}
        available = {
            "difficulty": {q["difficulty"] for q in subject_pool},
            "topic": {q["topic"] for q in subject_pool},
            "question_type": {q["question_type"] for q in subject_pool},
        }
        for dimension, mix in raw.items():
            if mix:
                unknown = sorted(set(mix) - available[dimension])
                if unknown:
                    raise ValueError(f"Unknown {dimension.replace('_', ' ')} value(s): {', '.join(unknown)}.")
                total = sum(float(v) for v in mix.values())
                if total <= 0:
                    raise ValueError(f"At least one {dimension} percentage must be greater than zero.")
                mixes[dimension] = {k: float(v) / total for k, v in mix.items()}
        paper = generate_paper(
            subject=req.subject,
            total_marks=req.total_marks,
            mixes=mixes,
            question_bank=ACTIVE_QUESTION_BANK,
            seed=req.seed,
        )
        paper["exam_details"] = {
            "exam_title": req.exam_title.strip() or "Question Paper",
            "class_name": req.class_name.strip(),
            "duration": req.duration.strip() or "Not specified",
            "instructions": req.instructions,
        }
        return paper
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/swap")
def swap(req: SwapRequest):
    try:
        return swap_question(req.paper, req.question_id, ACTIVE_QUESTION_BANK, seed=req.seed,
                             allow_adjustment=req.allow_adjustment)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/synthesis-proposals")
def synthesis_proposals(req: SynthesisRequest):
    """Suggest review-only compound-question pairings; never insert them automatically."""
    subject = req.subject.strip().title()
    if subject not in {"Maths", "Science"}:
        raise HTTPException(status_code=422, detail="Subject must be Maths or Science.")
    pool = [q for q in ACTIVE_QUESTION_BANK if q["subject"] == subject and q["difficulty"] == "Medium"]
    if req.topic:
        pool = [q for q in pool if q["topic"].casefold() == req.topic.casefold()]
    proposals: list[dict[str, Any]] = []
    for i, first in enumerate(pool):
        for second in pool[i + 1:]:
            if first["topic"] != second["topic"]:
                continue
            if first.get("id") == second.get("id"):
                continue
            from engine import _are_similar
            if _are_similar(first, second):
                continue
            proposals.append({
                "proposal_id": f"PAIR-{first['id']}-{second['id']}",
                "subject": subject,
                "topic": first["topic"],
                "question_type": "Long Answer",
                "proposed_marks": int(first["marks"]) + int(second["marks"]),
                "source_ids": [first["id"], second["id"]],
                "parts": [
                    {"label": "(a)", "question": first["question"], "marks": int(first["marks"]), "answer": first.get("answer", "")},
                    {"label": "(b)", "question": second["question"], "marks": int(second["marks"]), "answer": second.get("answer", "")},
                ],
                "draft_question": f"Answer both parts. (a) {first['question']} (b) {second['question']}",
                "difficulty": "Needs teacher review",
                "status": "proposal_only",
                "review_notes": [
                    "Same topic is not proof that the parts are conceptually connected.",
                    "Do not label this Hard until a teacher verifies increased reasoning demand.",
                    "Review the combined mark value, solution, syllabus eligibility, and similarity before use.",
                ],
            })
            if len(proposals) >= req.max_pairs:
                return {"status": "review_required", "proposals": proposals, "message": "Pairings are suggestions only; none have been added to the question bank or paper."}
    return {"status": "review_required", "proposals": proposals, "message": "Pairings are suggestions only; none have been added to the question bank or paper."}


@app.get("/api/sample-paper")
def sample_paper():
    mixes = {
        "difficulty": {"Easy": .3, "Medium": .5, "Hard": .2},
        "topic": {"Algebra": .3, "Geometry": .25, "Trigonometry": .25, "Statistics": .2},
        "question_type": {"MCQ": .4, "Short Answer": .4, "Long Answer": .2},
    }
    try:
        return generate_paper(subject="Maths", total_marks=40, mixes=mixes, question_bank=ACTIVE_QUESTION_BANK, seed=7)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _validate_uploaded_bank(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(records, list) or not records:
        raise ValueError("The uploaded question bank must contain at least one question.")
    if len(records) > MAX_BANK_QUESTIONS:
        raise ValueError(f"The bank has {len(records)} questions; the limit is {MAX_BANK_QUESTIONS}.")
    required = {"id", "subject", "topic", "difficulty", "question_type", "marks", "question"}
    normalized: list[dict[str, Any]] = []
    for i, row in enumerate(records, 1):
        if not isinstance(row, dict):
            raise ValueError(f"Row {i} must be a JSON object.")
        q = dict(row)
        missing = sorted(required - set(q))
        if missing:
            raise ValueError(f"Row {i} is missing required fields: {', '.join(missing)}.")
        q["id"] = str(q["id"]).strip()
        q["subject"] = str(q["subject"]).strip().title()
        q["topic"] = str(q["topic"]).strip()
        q["difficulty"] = str(q["difficulty"]).strip().title()
        type_value = str(q["question_type"]).strip().casefold()
        type_map = {"mcq": "MCQ", "short answer": "Short Answer", "long answer": "Long Answer"}
        q["question_type"] = type_map.get(type_value, str(q["question_type"]).strip())
        if isinstance(q["marks"], bool):
            raise ValueError(f"Row {i} has invalid marks; use a whole number from 1 to 100.")
        try:
            numeric_marks = float(q["marks"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Row {i} has invalid marks; use a whole number from 1 to 100.") from exc
        if not math.isfinite(numeric_marks) or not numeric_marks.is_integer() or not 1 <= numeric_marks <= 100:
            raise ValueError(f"Row {i} has invalid marks; use a whole number from 1 to 100.")
        q["marks"] = int(numeric_marks)
        q["question"] = str(q["question"]).strip()
        if q["subject"] not in {"Maths", "Science"}:
            raise ValueError(f"Row {i}: subject must be Maths or Science.")
        if q["difficulty"] not in {"Easy", "Medium", "Hard"}:
            raise ValueError(f"Row {i}: difficulty must be Easy, Medium, or Hard.")
        if q["question_type"] not in {"MCQ", "Short Answer", "Long Answer"}:
            raise ValueError(f"Row {i}: unsupported question_type.")
        if not q["id"] or len(q["id"]) > 120 or not q["topic"] or len(q["topic"]) > 120 or not q["question"]:
            raise ValueError(f"Row {i} needs an ID, topic, question text, and positive marks.")
        if len(q["question"]) > 5000:
            raise ValueError(f"Row {i}: question text exceeds 5000 characters.")
        if isinstance(q.get("options"), str):
            q["options"] = [v.strip() for v in q["options"].split("|") if v.strip()]
        if q["question_type"] == "MCQ":
            if not isinstance(q.get("options"), list) or len(q["options"]) < 2:
                raise ValueError(f"Row {i}: MCQ questions need at least two options; CSV options should be separated by |.")
            q["options"] = [str(option).strip() for option in q["options"]]
            if len(q["options"]) > 12 or any(not option or len(option) > 500 for option in q["options"]):
                raise ValueError(f"Row {i}: MCQ options must be non-empty, at most 500 characters each, and no more than 12 options.")
            if len({option.casefold() for option in q["options"]}) != len(q["options"]):
                raise ValueError(f"Row {i}: MCQ options contain duplicates.")
        if q.get("answer") is not None:
            q["answer"] = str(q["answer"]).strip()
            if len(q["answer"]) > 5000:
                raise ValueError(f"Row {i}: answer exceeds 5000 characters.")
            if q["question_type"] == "MCQ" and q["answer"]:
                option_values = {option.casefold() for option in q["options"]}
                option_labels = {chr(65 + index).casefold() for index in range(len(q["options"]))}
                if q["answer"].casefold() not in option_values | option_labels:
                    raise ValueError(f"Row {i}: MCQ answer must match an option value or its letter label (A, B, C, ...).")
        normalized.append(q)
    ids = [q["id"].casefold() for q in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("Question IDs must be unique, ignoring letter case.")
    from engine import _validate_bank
    _validate_bank(normalized)
    return normalized

ACTIVE_QUESTION_BANK = _load_active_bank()


def _parse_bank_upload(name: str, raw: bytes) -> list[dict[str, Any]]:
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("File must use UTF-8 text encoding.") from exc
    if name.endswith(".json"):
        records = json.loads(decoded)
    elif name.endswith(".csv"):
        records = list(csv.DictReader(io.StringIO(decoded, newline="")))
        if not records:
            raise ValueError("CSV file has no question rows or headers are missing.")
    else:
        raise ValueError("Upload a .json or .csv question bank.")
    return _validate_uploaded_bank(records)


def _persist_bank(records: list[dict[str, Any]]) -> None:
    BANK_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="active_questions_", suffix=".tmp", dir=BANK_STORAGE_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(records, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, BANK_STORAGE_PATH)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _bank_quality_warnings(records: list[dict[str, Any]]) -> list[str]:
    from engine import _are_similar
    warnings: list[str] = []
    missing_answers = sum(not str(q.get("answer", "")).strip() for q in records)
    if missing_answers:
        warnings.append(f"{missing_answers} question(s) have no answer key; they will require teacher review.")
    similar_pairs = 0
    for index, question in enumerate(records):
        for other in records[index + 1:]:
            if _are_similar(question, other):
                similar_pairs += 1
                if similar_pairs >= 20:
                    break
        if similar_pairs >= 20:
            break
    if similar_pairs:
        suffix = "+" if similar_pairs >= 20 else ""
        warnings.append(f"Found {similar_pairs}{suffix} likely duplicate/similar question pair(s). Review them; generation prevents detected similar questions appearing together.")
    return warnings


@app.post("/api/validate-bank")
async def validate_bank(file: UploadFile = File(...)):
    raw = await file.read(MAX_BANK_UPLOAD_BYTES + 1)
    await file.close()
    if len(raw) > MAX_BANK_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Question bank must be 5 MB or smaller.")
    try:
        records = _parse_bank_upload((file.filename or "").lower(), raw)
        by_subject = {subject: sum(q["subject"] == subject for q in records) for subject in ("Maths", "Science")}
        return {"valid": True, "question_count": len(records), "subject_counts": by_subject,
                "available_marks": {subject: sum(q["marks"] for q in records if q["subject"] == subject) for subject in by_subject},
                "warnings": _bank_quality_warnings(records),
                "message": "Validation passed. Upload again using Load bank to activate this bank."}
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/upload-bank")
async def upload_bank(file: UploadFile = File(...)):
    global ACTIVE_QUESTION_BANK
    raw = await file.read(MAX_BANK_UPLOAD_BYTES + 1)
    await file.close()
    if len(raw) > MAX_BANK_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Question bank must be 5 MB or smaller.")
    try:
        records = _parse_bank_upload((file.filename or "").lower(), raw)
        _persist_bank(records)
        ACTIVE_QUESTION_BANK = records
        return {"status": "ok", "question_count": len(ACTIVE_QUESTION_BANK),
                "subjects": sorted({q["subject"] for q in ACTIVE_QUESTION_BANK}),
                "warnings": _bank_quality_warnings(ACTIVE_QUESTION_BANK),
                "message": "Question bank validated and saved for future server runs."}
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Bank validated but could not be saved. The active bank was not changed.") from exc


@app.post("/api/reset-bank")
def reset_bank():
    global ACTIVE_QUESTION_BANK
    try:
        if BANK_STORAGE_PATH.exists():
            BANK_STORAGE_PATH.unlink()
        ACTIVE_QUESTION_BANK = list(QUESTION_BANK)
        return {"status": "ok", "question_count": len(ACTIVE_QUESTION_BANK), "message": "Restored the bundled sample bank."}
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Could not reset the saved question bank.") from exc


@app.post("/api/upload-textbook")
async def upload_textbook(file: UploadFile = File(...)):
    global TEXTBOOK_SOURCE
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Upload a PDF textbook.")
    raw = await file.read(MAX_PDF_UPLOAD_BYTES + 1)
    await file.close()
    if len(raw) > MAX_PDF_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF must be 20 MB or smaller.")
    if not raw.startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="The uploaded file does not have a valid PDF signature.")
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw), strict=True)
        if len(reader.pages) > MAX_PDF_PAGES:
            raise HTTPException(status_code=413, detail=f"PDF must contain {MAX_PDF_PAGES} pages or fewer.")
        extracted_parts: list[str] = []
        total_chars = 0
        for page in reader.pages:
            part = page.extract_text() or ""
            remaining = MAX_EXTRACTED_TEXT - total_chars
            if remaining <= 0:
                break
            extracted_parts.append(part[:remaining])
            total_chars += min(len(part), remaining)
        text = "\n".join(extracted_parts).strip()
    except HTTPException:
        raise
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="PDF support is not installed. Install requirements.txt.") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Could not read this PDF. Try a valid text-based PDF rather than a scanned image.") from exc
    if not text:
        raise HTTPException(status_code=422, detail="No selectable text found. Scanned PDFs need OCR and are not supported in this demo.")
    TEXTBOOK_SOURCE = {"filename": Path(file.filename or "textbook.pdf").name, "pages": len(reader.pages), "characters": len(text), "text": text}
    return {"status": "ok", "filename": TEXTBOOK_SOURCE["filename"], "pages": len(reader.pages),
            "characters_extracted": len(text), "preview": text[:1800],
            "message": "Text extracted as reference material. It does not automatically generate questions; add reviewed questions to the bank."}


@app.get("/api/textbook-status")
def textbook_status():
    if not TEXTBOOK_SOURCE:
        return {"loaded": False}
    return {"loaded": True, "filename": TEXTBOOK_SOURCE["filename"],
            "pages": TEXTBOOK_SOURCE["pages"], "characters": TEXTBOOK_SOURCE["characters"]}
