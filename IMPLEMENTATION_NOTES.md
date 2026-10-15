# Evalvia engine update

## Files
- `engine.py`: replacement generation and swap logic; keeps `generate_paper()` and `swap_question()` signatures compatible with `main.py`.
- `tests/test_engine.py`: engine tests for determinism, exact marks where possible, partial status, duplicate IDs, swaps, and mark-based breakdown.
- `tests/test_api.py`: API tests for health, exact-mark generation, and invalid subjects.

## Apply
1. Back up your current `engine.py` and `tests` folder.
2. Copy the new `engine.py` into the project root, replacing the existing file.
3. Copy the two tests into your project's `tests` folder.
4. From the project root, run `python -m pytest -q`.

The engine treats the requested distributions as soft targets and measures them by marks. It prevents duplicate IDs, exact duplicate question text, and very close text matches from appearing together. Similarity detection is heuristic and cannot guarantee detection of every semantically equivalent question.

Question swaps preserve marks and all other selected questions. They prefer a replacement with the same topic, difficulty, and question type. If no exact attribute match exists, the closest same-mark replacement is selected and `swap_info` reports any changed attributes.
