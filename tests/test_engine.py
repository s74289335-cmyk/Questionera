import json
from pathlib import Path
import pytest
from engine import generate_paper, swap_question

BANK = json.loads((Path(__file__).parents[1] / "questions.json").read_text(encoding="utf-8"))
MIXES = {
    "difficulty": {"Easy": .3, "Medium": .5, "Hard": .2},
    "topic": {"Algebra": .4, "Geometry": .3, "Trigonometry": .3},
    "question_type": {"MCQ": .4, "Short Answer": .4, "Long Answer": .2},
}


def test_generation_is_deterministic_and_no_duplicate_ids():
    a = generate_paper(subject="Maths", total_marks=20, mixes=MIXES, question_bank=BANK, seed=12)
    b = generate_paper(subject="Maths", total_marks=20, mixes=MIXES, question_bank=BANK, seed=12)
    assert [q["id"] for q in a["questions"]] == [q["id"] for q in b["questions"]]
    ids = [q["id"] for q in a["questions"]]
    assert len(ids) == len(set(ids))


def test_generation_reaches_exact_marks_when_possible():
    paper = generate_paper(subject="Maths", total_marks=20, mixes=MIXES, question_bank=BANK, seed=3)
    assert paper["achieved_marks"] == sum(q["marks"] for q in paper["questions"])
    assert paper["achieved_marks"] == 20
    assert paper["exact_marks"] is True


def test_unreachable_total_reports_partial_without_exceeding_target():
    tiny_bank = [q for q in BANK if q["subject"] == "Science" and q["id"] in {"S001", "S002"}]
    paper = generate_paper(subject="Science", total_marks=4, mixes={}, question_bank=tiny_bank, seed=1)
    assert paper["achieved_marks"] <= 4
    assert paper["exact_marks"] is False
    assert paper["status"] == "partial"
    assert paper["warnings"]


def test_invalid_subject_raises():
    with pytest.raises(ValueError):
        generate_paper(subject="History", total_marks=20, mixes=MIXES, question_bank=BANK)


def test_duplicate_bank_ids_are_rejected():
    with pytest.raises(ValueError, match="duplicate ID"):
        generate_paper(subject="Maths", total_marks=5, mixes=MIXES, question_bank=BANK + [BANK[0]])


def test_swap_preserves_marks_and_other_questions():
    paper = generate_paper(subject="Maths", total_marks=20, mixes=MIXES, question_bank=BANK, seed=5)
    current_ids = {q["id"] for q in paper["questions"]}
    old = next((q for q in paper["questions"] if any(
        candidate["subject"] == paper["subject"] and candidate["id"] not in current_ids
        and candidate["marks"] == q["marks"] for candidate in BANK)), None)
    if old is None:
        pytest.skip("This generated paper has no unused same-mark replacement candidate")
    index = next(i for i, q in enumerate(paper["questions"]) if q["id"] == old["id"])
    swapped = swap_question(paper, old["id"], BANK, seed=15, allow_adjustment=True)
    assert swapped["achieved_marks"] == paper["achieved_marks"]
    assert len(swapped["questions"]) == len(paper["questions"])
    assert all(a["id"] == b["id"] for i, (a, b) in enumerate(zip(paper["questions"], swapped["questions"])) if i != index)
    assert swapped["questions"][index]["id"] != old["id"]
    assert swapped["swap_info"]["preserved_marks"] is True


def test_science_paper_only_uses_science_questions():
    paper = generate_paper(subject="Science", total_marks=10, mixes=MIXES, question_bank=BANK, seed=8)
    assert all(q["subject"] == "Science" for q in paper["questions"])


def test_breakdown_is_by_marks_and_reports_all_actual_categories():
    paper = generate_paper(subject="Maths", total_marks=20, mixes=MIXES, question_bank=BANK, seed=2)
    for dimension, categories in paper["breakdown"].items():
        assert categories
        assert all("target_marks" in v and "actual_marks" in v and "difference_percentage_points" in v for v in categories.values())


def test_zero_weight_topic_is_excluded():
    mixes = {
        "difficulty": {"Easy": .3, "Medium": .5, "Hard": .2},
        "topic": {"Algebra": 1.0, "Geometry": 0, "Trigonometry": 0, "Statistics": 0},
        "question_type": {"MCQ": .4, "Short Answer": .4, "Long Answer": .2},
    }
    paper = generate_paper(subject="Maths", total_marks=10, mixes=mixes, question_bank=BANK, seed=22)
    assert all(q["topic"] == "Algebra" for q in paper["questions"])
    assert paper["breakdown"]["topic"]["Statistics"]["target_percent"] == 0
    assert paper["breakdown"]["topic"]["Statistics"]["actual_percent"] == 0


def test_boolean_marks_are_rejected():
    bad = [dict(BANK[0], id="BOOLMARK", marks=True)]
    with pytest.raises(ValueError, match="whole-number integer"):
        generate_paper(subject="Maths", total_marks=1, mixes={}, question_bank=bad)


def test_synthesis_proposal_does_not_change_bank():
    from main import _validate_uploaded_bank
    original_count = len(BANK)
    valid = _validate_uploaded_bank(BANK)
    assert len(valid) == original_count
    assert valid == BANK


def test_swap_requires_approval_when_attributes_must_change():
    tiny_bank = [
        {"id": "X1", "subject": "Maths", "topic": "Algebra", "difficulty": "Easy", "question_type": "MCQ", "marks": 1,
         "question": "What is 1 + 1?", "options": ["1", "2", "3"], "answer": "2"},
        {"id": "X2", "subject": "Maths", "topic": "Geometry", "difficulty": "Hard", "question_type": "Short Answer", "marks": 1,
         "question": "Name a quadrilateral with four equal sides.", "answer": "Rhombus"},
    ]
    paper = generate_paper(subject="Maths", total_marks=1, mixes={}, question_bank=tiny_bank, seed=1)
    old = paper["questions"][0]
    preview = swap_question(paper, old["id"], tiny_bank, seed=15)
    assert preview["swap_info"]["status"] == "adjustment_required"
    assert [q["id"] for q in preview["questions"]] == [q["id"] for q in paper["questions"]]
    approved = swap_question(paper, old["id"], tiny_bank, seed=15, allow_adjustment=True)
    assert approved["swap_info"]["status"] == "swapped"


def test_swap_rejects_tampered_question_payload():
    paper = generate_paper(subject="Maths", total_marks=20, mixes=MIXES, question_bank=BANK, seed=5)
    paper["questions"][0]["marks"] += 10
    with pytest.raises(ValueError, match="modified outside the active bank"):
        swap_question(paper, paper["questions"][0]["id"], BANK)


def test_math_operator_differences_are_not_collapsed_by_duplicate_normalization():
    from engine import _are_similar
    a = {"question": "Solve x + 3 = 9"}
    b = {"question": "Solve x - 3 = 9"}
    assert not _are_similar(a, b)
