# Evalvia AI — Smart Question Paper Generator

A web-based application that helps teachers generate structured Mathematics and Science question papers based on marks, difficulty level, topic weightage, and question type.

The goal is to make question paper generation faster, more consistent, and easier to customize while respecting the teacher's requirements.

## 1. Project Overview

Creating a question paper manually can take time, especially when teachers need to balance topics, difficulty levels, question types, and total marks.

This application provides a question paper generation system where teachers specify their requirements and receive a structured question paper with a distribution breakdown.

**Main objectives:**

- Generate question papers for Mathematics and Science.
- Respect the requested total marks.
- Distribute questions according to difficulty, topic, and question type.
- Avoid duplicate questions.
- Handle situations where the available question bank cannot satisfy every requirement.
- Allow teachers to replace individual questions without regenerating the entire paper.

## 2. Key Features

### Custom question paper generation

Teachers can configure the paper using requirements such as:

- **Subject:** Mathematics or Science.
- **Total marks:** The required marks for the examination.
- **Difficulty distribution:** Easy, Medium, and Hard.
- **Topic weightage:** The percentage of marks assigned to each topic.
- **Question type distribution:** MCQs, short-answer questions, and long-answer questions.

### Structured question paper

The generator organizes selected questions into a readable examination paper with question numbering, marks, and appropriate instructions.

### Distribution breakdown

The application provides a breakdown of the generated paper so teachers can review how the marks and questions are distributed.

### Constraint handling

The question bank may not always contain enough questions to satisfy every requested condition. The system should identify these limitations and communicate them clearly rather than silently presenting an incomplete paper as fully valid.

### Individual question replacement

Teachers can replace an unsuitable question with an alternative while preserving the rest of the paper. The replacement must be checked against applicable requirements, including marks, topic, difficulty, question type, and duplicate prevention.

*Note: The exact behavior of these features depends on the current implementation. Any unsupported feature should be described as planned work rather than an existing capability.*

## 3. Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, FastAPI |
| API server | Uvicorn |
| Frontend | HTML, CSS, JavaScript |
| Question bank | JSON |
| Automated testing | Pytest |
| HTTP testing | HTTPX |
| PDF support | pypdf |
| Hosting | Render |

The application uses a Python-based backend to process generation requests and a browser-based frontend for teacher interaction.

## 4. How It Works

The application follows a rule-based question selection approach.

1. **Collect requirements:** Read the selected subject, total marks, difficulty mix, topic weightage, and question type mix.
2. **Validate inputs:** Check whether the requested values and distributions are valid.
3. **Evaluate question availability:** Identify questions that match the requested subject and applicable constraints.
4. **Select questions:** Choose suitable questions while considering marks, topic coverage, difficulty, and question type.
5. **Validate the result:** Check the total marks, duplicate questions, and distribution requirements.
6. **Generate the paper:** Present the selected questions in an organized format with a breakdown.
7. **Allow refinement:** Where supported, replace individual questions and revalidate the updated paper.

The approach prioritizes explicit rules and predictable behavior rather than relying on an AI model to make every selection decision.

## 5. Constraint Handling

Constraint handling is one of the most important parts of this project.

For example, a teacher may request 20% hard questions and 40% Algebra weightage. If the question bank does not contain enough hard Algebra questions, the generator cannot honestly claim that every requested condition has been satisfied.

A robust solution should:

- Identify which requirement cannot be satisfied.
- Explain the shortage in understandable language.
- Suggest adding suitable questions or adjusting the requirements.
- Preserve the valid constraints wherever possible.
- Clearly identify incomplete results rather than presenting them as fully valid papers.

The system should not silently replace a missing hard Algebra question with an easy Geometry question and report that the original requirements were met.

### Handling percentages and marks

Percentage-based allocations may produce fractional marks or question counts. A consistent rounding and allocation strategy is therefore necessary.

The generator should prioritize the exact total marks and explicitly report any distribution that cannot be matched exactly.

## 6. Individual Question Replacement

Regenerating an entire paper whenever a teacher dislikes one question is inefficient.

The intended replacement workflow is:

1. Identify the question selected for replacement.
2. Find an unused alternative that satisfies the applicable requirements.
3. Check whether the replacement preserves the total marks and relevant distributions.
4. Replace only the selected question.
5. Validate the updated paper.
6. If no valid alternative exists, explain why the replacement cannot be completed and preserve the original paper.

This approach gives teachers greater control over the final question paper.

## 7. Project Structure

The main project files are organized as follows:

```text
Evalvia AI/
├── main.py
├── engine.py
├── questions.json
├── static/
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   └── paper.html
├── tests/
├── requirements.txt
├── render.yaml
└── README.md
```

**File responsibilities:**

- `main.py` — FastAPI application and API endpoints.
- `engine.py` — Question paper generation and selection logic.
- `questions.json` — Bundled question bank.
- `static/index.html` — Main application interface.
- `static/app.js` — Frontend interactions and API communication.
- `static/styles.css` — Application styling.
- `static/paper.html` — Question paper presentation.
- `tests/` — Automated tests.
- `requirements.txt` — Python dependencies.
- `render.yaml` — Render deployment configuration.

## 8. Installation and Local Setup

### Prerequisites

- Python 3.11 or a compatible Python version.
- Git (optional, for cloning the repository).
- A modern web browser.

### Step 1: Clone the repository

```bash
git clone https://github.com/s74289335-cmyk/Questionera.git
cd Questionera
```

Alternatively, open your existing local project folder.

### Step 2: Create a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, you can use the appropriate activation method for your environment.

### Step 3: Install dependencies

```bash
python -m pip install -r requirements.txt
```

### Step 4: Start the application

```bash
python -m uvicorn main:app --reload
```

### Step 5: Open the application

Visit:

- **Application:** http://127.0.0.1:8000
- **API documentation:** http://127.0.0.1:8000/docs
- **Health check:** http://127.0.0.1:8000/api/health

## 9. Running Tests

Run the automated test suite from the project root:

```bash
python -m pytest -q
```

Tests help verify application behavior and catch regressions in generation, validation, and API functionality.

A previously recorded test run reported **29 passed**. Run the tests against the current version before reporting that result in a submission.

Passing tests do not, by themselves, prove that every possible combination of constraints is supported. Important edge cases should also be tested.

## 10. Live Deployment

The application is deployed on Render.

- **Live application:** https://questionera.onrender.com
- **API documentation:** https://questionera.onrender.com/docs
- **Health check:** https://questionera.onrender.com/api/health

The health endpoint can be used to check whether the backend is responding.

Deployment availability and application functionality should be verified before sharing the link for evaluation.

## 11. Design Decisions

### Why rule-based generation?

Question paper generation involves explicit constraints such as total marks, topic coverage, difficulty distribution, and question types.

A rule-based approach is suitable because:

- The selection process can be inspected and tested.
- The system can validate whether the result matches the requirements.
- Constraint failures can be explained to the teacher.
- Individual question replacement can be implemented without regenerating everything.

The current architecture uses a question bank and selection logic rather than requiring a generative AI model for every paper.

### Why is validation important?

A paper that looks well formatted is not necessarily a valid paper. It must also satisfy its numerical and content requirements.

Validation helps identify issues such as incorrect total marks, unavailable question combinations, duplicate questions, and mismatched distributions.

## 12. Limitations and Future Improvements

Potential improvements include:

- Expanding the question bank across more topics and difficulty levels.
- Improving selection algorithms for conflicting constraints.
- Adding more comprehensive tests for infeasible requirements and question replacement.
- Supporting teacher-uploaded question banks with stronger validation.
- Adding persistent database storage for questions and generated papers.
- Improving answer-key generation and export options.
- Providing more detailed explanations when requested distributions cannot be matched.
- Adding user authentication and teacher-specific paper history if required.

Uploaded or modified question banks should be validated before they are used for generation.

## 13. Strengths and Weaknesses

### Strengths

- Reduces the manual effort involved in preparing question papers.
- Uses configurable requirements instead of completely random selection.
- Provides a structured and readable output.
- Uses a modular Python backend and browser-based frontend.
- Supports automated testing and a hosted demonstration.

### Weaknesses

- The quality and variety of generated papers depend on the question bank.
- Some combinations of marks, topics, difficulty, and question types may be infeasible.
- Exact percentage distributions may not always be achievable with discrete questions and fixed marks.
- The reliability of individual question replacement depends on the availability of suitable alternatives.
- Persistent storage and advanced teacher-management features may require additional infrastructure.

## 14. Conclusion

Evalvia AI — Smart Question Paper Generator is designed to simplify the creation of structured Mathematics and Science question papers.

Its central goal is to combine configurable requirements with systematic question selection, transparent validation, and teacher control.

The project also highlights an important challenge in automated generation: a useful system must not only produce an output but also recognize when the requested conditions cannot all be satisfied.

Future development will focus on expanding the question bank, strengthening constraint handling, improving validation, and making the application more reliable for everyday teaching use.

---

**Repository:** https://github.com/s74289335-cmyk/Questionera

**Live application:** https://questionera.onrender.com
