"""Constraint-aware question paper generation for the Evalvia mini assignment.

Hard constraints: subject/syllabus eligibility, unique question IDs, no duplicate or
near-duplicate question text, and never exceeding the requested marks.
Soft constraints: requested difficulty/topic/question-type distributions (by marks).
"""
from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache
import random
import re
import math
from typing import Any

DIMENSIONS = ("difficulty", "topic", "question_type")
VALID_SUBJECTS = {"Maths", "Science"}
MAX_STATES_PER_MARK_TOTAL = 6


def _paper_order_key(q: dict[str, Any]) -> tuple[int, int, int, str]:
    """Order papers into ascending mark sections, then question type/difficulty."""
    type_order = {"MCQ": 0, "Short Answer": 1, "Long Answer": 2}
    difficulty_order = {"Easy": 0, "Medium": 1, "Hard": 2}
    return (int(q.get("marks", 0)), type_order.get(q.get("question_type"), 9),
            difficulty_order.get(q.get("difficulty"), 9), str(q.get("id", "")))


def _normalize_mix(mix: dict[str, float] | None, available: set[str]) -> dict[str, float]:
    """Normalize a requested mix, retaining only categories available in the pool."""
    if not available:
        return {}
    if not mix:
        return {key: 1 / len(available) for key in sorted(available)}
    cleaned: dict[str, float] = {}
    recognized = {str(key): value for key, value in mix.items() if str(key) in available}
    # A caller may pass a subject-independent default blueprint; if none of its
    # categories apply, use an even mix for the actual subject rather than fail.
    if not recognized:
        return {key: 1 / len(available) for key in sorted(available)}
    unknown = sorted(set(map(str, mix)) - available)
    if unknown:
        raise ValueError(f"Unknown category value(s): {', '.join(unknown)}. Available: {', '.join(sorted(available))}.")
    for key, value in recognized.items():
        category = str(key)
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid percentage for {key}: {value!r}.") from exc
        if not math.isfinite(number) or number < 0 or number > 100:
            raise ValueError(f"Percentage for {key} must be between 0 and 100.")
        cleaned[category] = number
    total = sum(cleaned.values())
    if total <= 0:
        raise ValueError("Each non-empty mix must have at least one percentage greater than zero.")
    return {key: value / total for key, value in cleaned.items() if value > 0}


def _targets(total_marks: int, mix: dict[str, float]) -> dict[str, float]:
    return {key: total_marks * fraction for key, fraction in mix.items()}


def _question_text(q: dict[str, Any]) -> str:
    return str(q.get("question", "")).strip()


@lru_cache(maxsize=50000)
def _canonical(text: str) -> str:
    # Preserve mathematical operators so x+3 and x-3 are not collapsed together.
    text = (text.casefold().replace("²", "^2").replace("³", "^3")
            .replace("≤", "<=").replace("≥", ">=").replace("×", "*")
            .replace("÷", "/").replace("−", "-").replace("π", "pi"))
    text = re.sub(r"[^a-z0-9+*/=<>^%-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _are_similar(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Detect exact duplicates and very close text matches (not semantic equivalence)."""
    group_a, group_b = a.get("similarity_group"), b.get("similarity_group")
    if group_a and group_b and group_a == group_b:
        return True
    text_a, text_b = _canonical(_question_text(a)), _canonical(_question_text(b))
    if not text_a or not text_b:
        return False
    if text_a == text_b:
        return True
    # Only compare substantial questions; short questions often share generic wording.
    if min(len(text_a), len(text_b)) >= 24:
        longest = max(len(text_a), len(text_b))
        shortest = min(len(text_a), len(text_b))
        if shortest / longest < 0.82:
            return False
        if longest > 1200:
            # For unusually long prompts, use a bounded comparison to avoid a
            # pathological import causing quadratic text-comparison cost.
            text_a, text_b = text_a[:1200], text_b[:1200]
        return SequenceMatcher(None, text_a, text_b, autojunk=True).ratio() >= 0.93
    return False


def _validate_bank(question_bank: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for index, q in enumerate(question_bank):
        qid = q.get("id")
        if not isinstance(qid, str) or not qid.strip():
            raise ValueError(f"Question at bank position {index + 1} has a missing or invalid ID.")
        canonical_id = qid.strip().casefold()
        if canonical_id in seen:
            raise ValueError(f"Question bank contains duplicate ID {qid!r}; IDs must be unique ignoring case.")
        seen.add(canonical_id)
        raw_marks = q.get("marks", 0)
        if isinstance(raw_marks, bool) or not isinstance(raw_marks, int):
            raise ValueError(f"Question {qid} must have a positive whole-number integer mark value.")
        marks = raw_marks
        if marks <= 0 or marks > 100:
            raise ValueError(f"Question {qid} marks must be between 1 and 100.")
        if len(_question_text(q)) > 5000:
            raise ValueError(f"Question {qid} text exceeds the 5000-character limit.")
        if not _question_text(q):
            raise ValueError(f"Question {qid} has empty question text.")
        for field in ("subject", "topic", "difficulty", "question_type"):
            if not isinstance(q.get(field), str) or not q[field].strip():
                raise ValueError(f"Question {qid} is missing required field {field!r}.")
        if q["subject"] not in VALID_SUBJECTS:
            raise ValueError(f"Question {qid} has unsupported subject {q['subject']!r}.")
        if q["difficulty"] not in {"Easy", "Medium", "Hard"}:
            raise ValueError(f"Question {qid} has unsupported difficulty {q['difficulty']!r}.")
        if q["question_type"] not in {"MCQ", "Short Answer", "Long Answer"}:
            raise ValueError(f"Question {qid} has unsupported question type {q['question_type']!r}.")
        if q["question_type"] == "MCQ":
            options = q.get("options")
            if not isinstance(options, list) or len(options) < 2 or any(not str(o).strip() for o in options):
                raise ValueError(f"MCQ {qid} must have at least two non-empty options.")
            if len({re.sub(r"\s+", " ", str(o).casefold().strip()) for o in options}) != len(options):
                raise ValueError(f"MCQ {qid} contains duplicate options.")


def _distribution_distance(selected: list[dict[str, Any]], total_marks: int,
                           mixes: dict[str, dict[str, float]]) -> float:
    """Sum normalized absolute errors against the requested full-paper mark targets."""
    if total_marks <= 0:
        return float("inf")
    score = 0.0
    for dimension, mix in mixes.items():
        targets = _targets(total_marks, mix)
        actual = Counter()
        for q in selected:
            actual[q[dimension]] += int(q["marks"])
        all_categories = set(targets) | set(actual)
        score += sum(abs(actual.get(k, 0) - targets.get(k, 0.0)) for k in all_categories) / total_marks
    return score


def _compatible_with_selection(candidate: dict[str, Any], selected: list[dict[str, Any]]) -> bool:
    return all(candidate.get("id") != q.get("id") and not _are_similar(candidate, q) for q in selected)


def _choose_questions(pool: list[dict[str, Any]], total_marks: int,
                      mixes: dict[str, dict[str, float]], seed: int | None) -> list[dict[str, Any]]:
    """Mark-total dynamic programming with precomputed similarity conflicts.

    Similarity is computed once per question pair rather than repeatedly for every
    candidate selection. States preserve several mix-diverse options per reachable
    mark total while keeping generation responsive for larger uploaded banks.
    """
    from functools import lru_cache

    rng = random.Random(seed)
    questions = [q.copy() for q in pool]
    rng.shuffle(questions)
    count = len(questions)
    conflicts: list[set[int]] = [set() for _ in questions]
    for i in range(count):
        for j in range(i):
            if _are_similar(questions[i], questions[j]):
                conflicts[i].add(j)
                conflicts[j].add(i)

    @lru_cache(maxsize=50000)
    def score(indices: tuple[int, ...]) -> float:
        return _distribution_distance([questions[i] for i in indices], total_marks, mixes)

    states: dict[int, list[tuple[int, ...]]] = {0: [()]}
    for idx, q in enumerate(questions):
        qmarks = int(q["marks"])
        updates: dict[int, list[tuple[int, ...]]] = {}
        for marks, selections in list(states.items()):
            new_marks = marks + qmarks
            if new_marks > total_marks:
                continue
            for selection in selections:
                if any(prev in conflicts[idx] for prev in selection):
                    continue
                updates.setdefault(new_marks, []).append(selection + (idx,))
        for marks, new_selections in updates.items():
            merged = list(dict.fromkeys(states.get(marks, []) + new_selections))
            merged.sort(key=lambda inds: (score(inds), len(inds), inds))
            states[marks] = merged[:MAX_STATES_PER_MARK_TOTAL]
    best_marks = max(states)
    target_marks = total_marks if total_marks in states else best_marks
    chosen = min(states[target_marks], key=lambda inds: (score(inds), len(inds), inds))
    return [questions[i] for i in chosen]


def _build_breakdown(selected: list[dict[str, Any]], requested_marks: int,
                     mixes: dict[str, dict[str, float]]) -> dict[str, Any]:
    achieved_marks = sum(int(q["marks"]) for q in selected)
    breakdown: dict[str, Any] = {}
    for dimension, mix in mixes.items():
        targets = _targets(requested_marks, mix)
        actual = Counter()
        for q in selected:
            actual[q[dimension]] += int(q["marks"])
        categories = set(targets) | set(actual)
        breakdown[dimension] = {
            key: {
                "target_marks": round(targets.get(key, 0.0), 2),
                "actual_marks": actual.get(key, 0),
                "target_percent": round(100 * targets.get(key, 0.0) / requested_marks, 1),
                "actual_percent": round(100 * actual.get(key, 0) / max(achieved_marks, 1), 1),
                "difference_percentage_points": round(
                    100 * actual.get(key, 0) / max(achieved_marks, 1)
                    - 100 * targets.get(key, 0.0) / requested_marks, 1
                ),
            }
            for key in sorted(categories)
        }
    return breakdown


def generate_paper(*, subject: str, total_marks: int, mixes: dict[str, dict[str, float]],
                   question_bank: list[dict[str, Any]], seed: int | None = None,
                   exclude_ids: set[str] | None = None) -> dict[str, Any]:
    if isinstance(total_marks, bool) or not isinstance(total_marks, int) or not 1 <= total_marks <= 300:
        raise ValueError("Total marks must be a whole number between 1 and 300.")
    subject = str(subject).strip().title()
    if subject not in VALID_SUBJECTS:
        raise ValueError("Subject must be Maths or Science.")
    _validate_bank(question_bank)
    excluded = exclude_ids or set()
    supplied_mixes = mixes or {}
    zero_exclusions: dict[str, set[str]] = {}
    for dimension in DIMENSIONS:
        raw_mix = supplied_mixes.get(dimension) or {}
        zero_exclusions[dimension] = {
            str(category) for category, value in raw_mix.items()
            if float(value) == 0.0
        }
    pool = [q.copy() for q in question_bank
            if q.get("subject") == subject and q.get("id") not in excluded
            and all(str(q.get(dim)) not in categories for dim, categories in zero_exclusions.items())]
    if not pool:
        raise ValueError(f"No questions available for {subject} with the current exclusions.")

    normalized: dict[str, dict[str, float]] = {}
    for dimension in DIMENSIONS:
        available = {str(q[dimension]) for q in pool}
        raw_mix = (mixes or {}).get(dimension)
        # A supplied zero is an explicit exclusion, not merely a low-weight target.
        if raw_mix:
            positive_mix = {k: v for k, v in raw_mix.items() if float(v) > 0}
            if not positive_mix:
                raise ValueError(f"At least one {dimension} percentage must be greater than zero.")
            normalized[dimension] = _normalize_mix(positive_mix, available)
            normalized[dimension].update({str(k): 0.0 for k, v in raw_mix.items() if float(v) == 0.0})
        else:
            normalized[dimension] = _normalize_mix(raw_mix, available)

    selected = _choose_questions(pool, total_marks, normalized, seed)
    # Keep the paper aligned by marks; this ordering is also reapplied after swaps.
    selected.sort(key=_paper_order_key)
    achieved_marks = sum(int(q["marks"]) for q in selected)
    breakdown = _build_breakdown(selected, total_marks, normalized)

    warnings: list[str] = []
    if achieved_marks != total_marks:
        warnings.append(
            f"Exact total not achievable with the eligible, non-duplicate questions: "
            f"generated {achieved_marks} of {total_marks} marks. Add eligible questions or adjust the requested total."
        )
    for dimension, categories in breakdown.items():
        off = [(name, values) for name, values in categories.items()
               if abs(values["difference_percentage_points"]) > 10]
        if off:
            labels = ", ".join(
                f"{name} (target {v['target_percent']}%, achieved {v['actual_percent']}%)"
                for name, v in off
            )
            warnings.append(f"{dimension.replace('_', ' ').title()} mix differs from the requested distribution: {labels}.")

    missing_answers = [q.get("id", "?") for q in selected if not str(q.get("answer", "")).strip()]
    if missing_answers:
        warnings.append(f"Answer key missing for {len(missing_answers)} selected question(s): {', '.join(map(str, missing_answers[:8]))}{'…' if len(missing_answers) > 8 else ''}. Teacher review required before publishing.")

    for dimension, mix in normalized.items():
        available_marks = Counter()
        for q in pool:
            available_marks[q[dimension]] += int(q["marks"])
        for category, fraction in mix.items():
            desired = total_marks * fraction
            if desired > available_marks[category]:
                warnings.append(
                    f"Limited {dimension.replace('_', ' ')} pool: requested about {desired:.0f} marks "
                    f"for {category}, but the entire available pool contains {available_marks[category]} marks."
                )

    return {
        "subject": subject,
        "requested_marks": total_marks,
        "achieved_marks": achieved_marks,
        "questions": selected,
        "breakdown": breakdown,
        "warnings": list(dict.fromkeys(warnings)),
        "exact_marks": achieved_marks == total_marks,
        "status": "success" if achieved_marks == total_marks else "partial",
        "requested_mixes": normalized,
        "quality_gate": {
            "ready_for_teacher_review": achieved_marks == total_marks,
            "answer_key_complete": not missing_answers,
            "teacher_review_required": True,
            "publishable": False,
            "publication_status": "draft_requires_teacher_review",
            "notes": ["Answer presence is checked, but mathematical correctness is not automatically proven.",
                      "Difficulty labels and marking schemes require teacher review.",
                      "Similarity checks compare normalized text and explicit similarity groups; they do not prove semantic originality."],
        },
        "constraints": {
            "subject_eligible": True,
            "unique_question_ids": len({q["id"] for q in selected}) == len(selected),
            "duplicate_question_text_checked": True,
            "zero_weight_categories_excluded": True,
            "mixes_are_soft_targets": True,
            "mix_basis": "marks",
        },
    }


def swap_question(paper: dict[str, Any], question_id: str,
                  question_bank: list[dict[str, Any]], seed: int | None = None,
                  allow_adjustment: bool = False) -> dict[str, Any]:
    """Swap one question only; preserve marks and every other selected question.

    Prefer exact attribute matches. If none exist, use the closest same-mark candidate
    and return explicit adjustment metadata rather than silently changing the paper.
    """
    questions = paper.get("questions", [])
    old_index = next((i for i, q in enumerate(questions) if q.get("id") == question_id), None)
    if old_index is None:
        raise ValueError("Question to replace was not found in this paper.")
    old = questions[old_index]
    _validate_bank(question_bank)
    current_ids_list = [q.get("id") for q in questions]
    if len(current_ids_list) != len(set(current_ids_list)):
        raise ValueError("This paper contains duplicate question IDs. Regenerate or repair it before swapping.")
    bank_by_id = {q["id"]: q for q in question_bank}
    for selected_q in questions:
        source = bank_by_id.get(selected_q.get("id"))
        if source is None:
            raise ValueError(f"Question {selected_q.get('id')} is not present in the active question bank.")
        for field in ("subject", "topic", "difficulty", "question_type", "marks", "question"):
            if selected_q.get(field) != source.get(field):
                raise ValueError(f"Question {selected_q.get('id')} has been modified outside the active bank ({field} mismatch). Regenerate before swapping.")
    current_ids = set(current_ids_list)
    selected_without_old = [q for i, q in enumerate(questions) if i != old_index]
    candidates = [q for q in question_bank
                  if q.get("subject") == paper.get("subject")
                  and q.get("id") not in current_ids
                  and int(q.get("marks", 0)) == int(old.get("marks", 0))
                  and _compatible_with_selection(q, selected_without_old)]
    if not candidates:
        raise ValueError(
            f"No unused, non-duplicate {paper.get('subject')} question worth {old.get('marks')} marks "
            "is available. No other questions were changed."
        )

    def attribute_match_count(q: dict[str, Any]) -> int:
        return sum(q.get(field) == old.get(field) for field in ("topic", "difficulty", "question_type"))

    exact = [q for q in candidates if attribute_match_count(q) == 3]
    if not exact and not allow_adjustment:
        suggestions = sorted(candidates, key=lambda q: (-attribute_match_count(q), str(q["id"])))[:5]
        unchanged = dict(paper)
        unchanged["swap_info"] = {
            "status": "adjustment_required",
            "replaced_id": question_id,
            "preserved_marks": True,
            "message": "No replacement preserves all question attributes. Review these same-mark alternatives before approving a change.",
            "suggested_replacements": [{"id": q["id"], "topic": q["topic"], "difficulty": q["difficulty"], "question_type": q["question_type"]} for q in suggestions],
        }
        return unchanged
    candidate_pool = exact or candidates
    rng = random.Random(seed)
    best_score = max(attribute_match_count(q) for q in candidate_pool)
    best = [q for q in candidate_pool if attribute_match_count(q) == best_score]
    replacement = rng.choice(sorted(best, key=lambda q: str(q["id"]))).copy()

    updated = dict(paper)
    updated_questions = list(questions)
    updated_questions[old_index] = replacement
    # A swap must never leave a replacement stranded in the wrong mark section.
    updated_questions.sort(key=_paper_order_key)
    updated["questions"] = updated_questions
    updated["achieved_marks"] = sum(int(q["marks"]) for q in updated_questions)
    updated["exact_marks"] = updated["achieved_marks"] == updated.get("requested_marks", updated["achieved_marks"])
    changed_attributes = [field for field in ("topic", "difficulty", "question_type")
                          if replacement.get(field) != old.get(field)]
    updated["swap_info"] = {
        "status": "swapped",
        "replaced_id": question_id,
        "replacement_id": replacement["id"],
        "preserved_marks": True,
        "changed_attributes": changed_attributes,
        "exact_attribute_match": not changed_attributes,
        "message": ("Replacement preserves marks, topic, difficulty, and question type."
                    if not changed_attributes else
                    "No exact attribute match was available; the closest same-mark replacement was used. "
                    "Only the requested question changed."),
    }
    # Recalculate distribution values after a swap; old warnings must not remain stale.
    requested_mixes = updated.get("requested_mixes")
    if isinstance(requested_mixes, dict):
        updated["breakdown"] = _build_breakdown(updated_questions, int(updated.get("requested_marks", updated["achieved_marks"])), requested_mixes)
        updated["warnings"] = []
        if not updated["exact_marks"]:
            updated["warnings"].append(f"Paper remains incomplete: {updated['achieved_marks']} of {updated.get('requested_marks')} marks.")
        missing_after_swap = [q.get("id", "?") for q in updated_questions if not str(q.get("answer", "")).strip()]
        if missing_after_swap:
            updated["warnings"].append(f"Answer key missing for {len(missing_after_swap)} selected question(s). Teacher review required before publishing.")
        for dimension, categories in updated["breakdown"].items():
            off = [(name, values) for name, values in categories.items()
                   if abs(values["difference_percentage_points"]) > 10]
            if off:
                labels = ", ".join(f"{name} (target {v['target_percent']}%, achieved {v['actual_percent']}%)" for name, v in off)
                updated["warnings"].append(f"{dimension.replace('_', ' ').title()} mix differs after replacement: {labels}.")
    if isinstance(updated.get("quality_gate"), dict):
        updated["quality_gate"]["answer_key_complete"] = all(bool(str(q.get("answer", "")).strip()) for q in updated_questions)
    return updated
