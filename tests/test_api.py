import json
from pathlib import Path

from fastapi.testclient import TestClient
import main

client = TestClient(main.app)


def test_health():
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'
    assert response.json()['question_count'] >= 1


def test_generate_endpoint_reports_exact_marks_when_possible():
    response = client.post('/api/generate', json={
        'subject': 'Maths', 'total_marks': 20, 'seed': 5,
        'mixes': {
            'difficulty': {'Easy': 30, 'Medium': 50, 'Hard': 20},
            'topic': {'Algebra': 40, 'Geometry': 30, 'Trigonometry': 30, 'Statistics': 0},
            'question_type': {'MCQ': 40, 'Short Answer': 40, 'Long Answer': 20},
        },
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['requested_marks'] == 20
    assert data['achieved_marks'] == 20
    assert data['exact_marks'] is True
    assert all(q['topic'] != 'Statistics' for q in data['questions'])
    assert data['quality_gate']['teacher_review_required'] is True


def test_invalid_subject_returns_422():
    response = client.post('/api/generate', json={'subject': 'History', 'total_marks': 20})
    assert response.status_code == 422


def test_all_zero_mix_is_rejected():
    response = client.post('/api/generate', json={
        'subject': 'Maths', 'total_marks': 20,
        'mixes': {'difficulty': {'Easy': 0, 'Medium': 0, 'Hard': 0}}
    })
    assert response.status_code == 422


def test_generate_accepts_exam_details():
    response = client.post('/api/generate', json={
        'subject': 'Maths', 'total_marks': 20,
        'exam_title': 'Unit Test', 'class_name': 'Grade 10',
        'duration': '90 minutes', 'instructions': ['Answer all questions.'],
    })
    assert response.status_code == 200, response.text
    assert response.json()['exam_details']['exam_title'] == 'Unit Test'
    assert response.json()['exam_details']['class_name'] == 'Grade 10'


def test_upload_bank_rejects_unknown_file_type():
    response = client.post('/api/upload-bank', files={'file': ('bank.txt', b'hello', 'text/plain')})
    assert response.status_code == 422
    assert 'json or .csv' in response.json()['detail']


def test_upload_bank_loads_and_persists_valid_json_bank(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'BANK_STORAGE_PATH', tmp_path / 'active_questions.json')
    bank = json.loads((Path(__file__).parents[1] / 'questions.json').read_text(encoding='utf-8'))
    response = client.post('/api/upload-bank', files={
        'file': ('bank.json', json.dumps(bank).encode(), 'application/json')
    })
    assert response.status_code == 200, response.text
    assert response.json()['question_count'] == len(bank)
    assert (tmp_path / 'active_questions.json').exists()
    assert len(main._load_active_bank()) == len(bank)


def test_validate_bank_does_not_activate_or_persist(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'BANK_STORAGE_PATH', tmp_path / 'active_questions.json')
    bank = json.loads((Path(__file__).parents[1] / 'questions.json').read_text(encoding='utf-8'))
    before_count = len(main.ACTIVE_QUESTION_BANK)
    response = client.post('/api/validate-bank', files={
        'file': ('bank.json', json.dumps(bank).encode(), 'application/json')
    })
    assert response.status_code == 200, response.text
    assert response.json()['valid'] is True
    assert not (tmp_path / 'active_questions.json').exists()
    assert len(main.ACTIVE_QUESTION_BANK) == before_count


def test_upload_rejects_boolean_marks(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'BANK_STORAGE_PATH', tmp_path / 'active_questions.json')
    bad = [{
        'id': 'BAD1', 'subject': 'Maths', 'topic': 'Algebra', 'difficulty': 'Easy',
        'question_type': 'Short Answer', 'marks': True, 'question': 'What is 1 + 1?', 'answer': '2'
    }]
    response = client.post('/api/upload-bank', files={
        'file': ('bank.json', json.dumps(bad).encode(), 'application/json')
    })
    assert response.status_code == 422
    assert not (tmp_path / 'active_questions.json').exists()


def test_upload_rejects_mcq_answer_not_in_options(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'BANK_STORAGE_PATH', tmp_path / 'active_questions.json')
    bad = [{
        'id': 'BAD2', 'subject': 'Maths', 'topic': 'Algebra', 'difficulty': 'Easy',
        'question_type': 'MCQ', 'marks': 1, 'question': 'What is 1 + 1?',
        'options': ['1', '2', '3'], 'answer': '4'
    }]
    response = client.post('/api/upload-bank', files={
        'file': ('bank.json', json.dumps(bad).encode(), 'application/json')
    })
    assert response.status_code == 422
    assert 'answer must match' in response.json()['detail']


def test_textbook_rejects_non_pdf_signature():
    response = client.post('/api/upload-textbook', files={'file': ('fake.pdf', b'not a pdf', 'application/pdf')})
    assert response.status_code == 422


def test_synthesis_proposals_are_review_only():
    response = client.post('/api/synthesis-proposals', json={'subject': 'Maths', 'max_pairs': 3})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['status'] == 'review_required'
    assert len(data['proposals']) <= 3
    assert all(item['status'] == 'proposal_only' for item in data['proposals'])
    assert all(item['difficulty'] == 'Needs teacher review' for item in data['proposals'])


def test_boolean_total_marks_is_rejected():
    response = client.post('/api/generate', json={'subject': 'Maths', 'total_marks': True})
    assert response.status_code == 422


def test_boolean_mix_values_are_rejected():
    response = client.post('/api/generate', json={
        'subject': 'Maths', 'total_marks': 20,
        'mixes': {'difficulty': {'Easy': True, 'Medium': 50, 'Hard': 20}}
    })
    assert response.status_code == 422


def test_both_subjects_can_generate_100_mark_papers_from_sample_bank():
    for subject in ('Maths', 'Science'):
        response = client.post('/api/generate', json={
            'subject': subject, 'total_marks': 100,
            'mixes': {
                'difficulty': {'Easy': 30, 'Medium': 50, 'Hard': 20},
                'topic': {},
                'question_type': {'MCQ': 40, 'Short Answer': 40, 'Long Answer': 20},
            },
        })
        assert response.status_code == 200, response.text
        paper = response.json()
        assert paper['exact_marks'] is True
        assert paper['achieved_marks'] == 100
        assert sum(question['marks'] for question in paper['questions']) == 100
        assert paper['quality_gate']['teacher_review_required'] is True
