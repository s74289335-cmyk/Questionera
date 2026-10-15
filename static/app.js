"use strict";
let currentPaper = null;
let optionsData = {};

const $ = (id) => document.getElementById(id);

if ($("exam-date") && !$("exam-date").value) $("exam-date").value = new Date().toISOString().slice(0, 10);
const pct = (id) => Math.max(0, Number($(id)?.value) || 0);

async function api(url, body) {
  const response = await fetch(
    url,
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        }
      : {}
  );

  let data;

  try {
    data = await response.json();
  } catch {
    throw new Error("The server returned an invalid response.");
  }

  if (!response.ok) {
    throw new Error(data.detail || "Request failed.");
  }

  return data;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

function buildTopicFields(subject, defaults = {}) {
  const container = $("topic-fields");
  if (!container) return;

  const topics = optionsData[subject]?.topics || [];
  const divisor = Math.max(1, topics.length);

  container.innerHTML = topics.map((topic) => `
    <label>
      ${escapeHtml(topic)}
      <input
        type="number"
        min="0"
        max="100"
        data-topic="${escapeHtml(topic)}"
        value="${defaults[topic] ?? Math.round(100 / divisor)}"
      >
    </label>
  `).join("");
}

function readMixes() {
  const topic = {};

  document.querySelectorAll("[data-topic]").forEach((element) => {
    topic[element.dataset.topic] = Math.max(
      0,
      Number(element.value) || 0
    );
  });

  return {
    difficulty: {
      Easy: pct("easy"),
      Medium: pct("medium"),
      Hard: pct("hard")
    },
    topic,
    question_type: {
      MCQ: pct("mcq"),
      "Short Answer": pct("short"),
      "Long Answer": pct("long")
    }
  };
}

function showError(message) {
  $("empty-state")?.classList.add("hidden");

  const result = $("result");
  if (!result) { alert(message); return; }

  result.classList.remove("hidden");
  result.innerHTML = `
    <div class="error">${escapeHtml(message)}</div>
  `;
}

function orderedPaperQuestions(paper) {
  const typeOrder = { "MCQ": 0, "Short Answer": 1, "Long Answer": 2 };
  const difficultyOrder = { "Easy": 0, "Medium": 1, "Hard": 2 };
  return [...(paper.questions || [])].sort((a, b) =>
    (typeOrder[a.question_type] ?? 9) - (typeOrder[b.question_type] ?? 9) ||
    (difficultyOrder[a.difficulty] ?? 9) - (difficultyOrder[b.difficulty] ?? 9) ||
    String(a.id).localeCompare(String(b.id))
  );
}

function renderPaper(paper) {
  currentPaper = paper;
  try { localStorage.setItem("evalviaCurrentPaper", JSON.stringify(paper)); } catch (error) { console.warn("Could not persist the current paper", error); }

  if (!$("result")) return;

  $("empty-state")?.classList.add("hidden");
  $("result")?.classList.remove("hidden");

  if ($("export-btn")) $("export-btn").disabled = false;
  if ($("answer-key-btn")) $("answer-key-btn").disabled = false;
  if ($("view-paper-btn")) $("view-paper-btn").disabled = false;
  if ($("pdf-btn")) $("pdf-btn").disabled = false;

  const warnings = paper.warnings?.length
    ? `
      <div class="warning-list">
        <strong>⚠ Constraint notes</strong>
        <ul>
          ${paper.warnings.map((warning) => `
            <li>${escapeHtml(warning)}</li>
          `).join("")}
        </ul>
      </div>
    `
    : `
      <div class="success-note">
        ✓ Requested total marks achieved. Review the distribution below.
      </div>
    `;

  let breakdown = `
    <div class="breakdown">
      <h3>Requested vs achieved distribution</h3>
  `;

  for (const [dimension, groups] of Object.entries(paper.breakdown || {})) {
    breakdown += `
      <div class="section-label">
        ${escapeHtml(dimension.replaceAll("_", " "))}
      </div>
    `;

    for (const [name, value] of Object.entries(groups)) {
      const width = Math.min(
        100,
        Math.max(0, Number(value.actual_percent) || 0)
      );

      breakdown += `
        <div class="break-row">
          <span class="break-label">${escapeHtml(name)}</span>
          <div class="track">
            <span style="width:${width}%"></span>
          </div>
          <span class="break-values">
            ${escapeHtml(value.actual_percent)}% /
            ${escapeHtml(value.target_percent)}%
          </span>
        </div>
      `;
    }
  }

  breakdown += "</div>";

  let lastQuestionType = "";
  const questions = orderedPaperQuestions(paper).map((question, index) => {
    const section = question.question_type !== lastQuestionType
      ? `<div class="section-label question-type-section">${escapeHtml(question.question_type)} Questions</div>`
      : "";
    lastQuestionType = question.question_type;
    return `${section}
    <article class="question-card">
      <div class="q-top">
        <span class="q-number">
          QUESTION ${String(index + 1).padStart(2, "0")}
          · ${escapeHtml(question.marks)}
          MARK${Number(question.marks) === 1 ? "" : "S"}
        </span>

        <div class="q-meta">
          <span class="chip ${escapeHtml(
            String(question.difficulty || "").toLowerCase()
          )}">
            ${escapeHtml(question.difficulty)}
          </span>
          <span class="chip">${escapeHtml(question.topic)}</span>
          <span class="chip">${escapeHtml(question.question_type)}</span>
        </div>
      </div>

      <p class="q-text">${escapeHtml(question.question)}</p>

      ${Array.isArray(question.options) && question.options.length
        ? `
          <ol class="q-options" type="A">
            ${question.options.map((option) => `
              <li>${escapeHtml(option)}</li>
            `).join("")}
          </ol>
        `
        : ""
      }

      <div class="q-bottom">
        <span class="q-answer">
          Answer key: ${escapeHtml(question.answer || "Not provided")}
        </span>

        <button
          class="swap-btn"
          data-swap="${escapeHtml(question.id)}"
          type="button"
        >
          ↻ Swap question
        </button>
      </div>
    </article>
  `;
  }).join("");

  $("result").innerHTML = `
    <div class="result-summary">
      <div class="summary-pill">
        <span>REQUESTED MARKS</span>
        <strong>${escapeHtml(paper.requested_marks)}</strong>
      </div>

      <div class="summary-pill">
        <span>ACHIEVED MARKS</span>
        <strong>${escapeHtml(paper.achieved_marks)}</strong>
      </div>

      <div class="summary-pill">
        <span>QUESTIONS</span>
        <strong>${(paper.questions || []).length}</strong>
      </div>
    </div>

    ${warnings}
    ${breakdown}

    <div class="paper-heading">
      <h3>${escapeHtml(paper.exam_details?.exam_title || paper.subject + " Assessment")}</h3>
      <p>
        ${paper.exact_marks ? "Draft generated by Evalvia" : "INCOMPLETE DRAFT — DO NOT PUBLISH"}
        · ${escapeHtml(paper.subject)}
        · Total: ${escapeHtml(paper.achieved_marks)} / ${escapeHtml(paper.requested_marks)} marks
        ${paper.exam_details?.class_name ? " · " + escapeHtml(paper.exam_details.class_name) : ""}
      </p>
    </div>

    ${questions}
  `;

  $("result").querySelectorAll("[data-swap]").forEach((button) => {
    button.addEventListener("click", () => {
      doSwap(button.dataset.swap, button);
    });
  });
}

async function doSwap(id, button) {
  if (!currentPaper) return;

  button.disabled = true;
  button.textContent = "Swapping…";

  try {
    let nextPaper = await api("/api/swap", {
      paper: currentPaper,
      question_id: id,
      seed: Math.floor(Math.random() * 100000),
      allow_adjustment: false
    });
    if (nextPaper.swap_info?.status === "adjustment_required") {
      const suggestions = (nextPaper.swap_info.suggested_replacements || [])
        .map((item) => `${item.id}: ${item.topic}, ${item.difficulty}, ${item.question_type}`)
        .join("\n");
      const approved = window.confirm(`${nextPaper.swap_info.message}\n\nSuggested same-mark alternatives:\n${suggestions || "No candidates available."}\n\nApprove the best available alternative? Other questions will remain unchanged.`);
      if (!approved) return;
      nextPaper = await api("/api/swap", {
        paper: currentPaper,
        question_id: id,
        seed: Math.floor(Math.random() * 100000),
        allow_adjustment: true
      });
    }
    renderPaper(nextPaper);
  } catch (error) {
    button.disabled = false;
    button.textContent = "↻ Swap question";
    alert(error.message);
  }
}

function askPaperDetails(paper) {.
  const subject = paper.subject || "Assessment";
  const value = (id, fallback = "") => ($(id)?.value || "").trim() || fallback;
  return {
    institution: value("institution", "Institution Name"),
    examTitle: value("exam-title", `${subject} Assessment`),
    className: value("class-name"),
    academicYear: value("academic-year", String(new Date().getFullYear())),
    examDate: value("exam-date", new Date().toISOString().slice(0, 10)),
    duration: value("duration", "2 hours"),
    instructions: value("instructions", "Answer all questions carefully.")
  };
}

function buildPrintablePaper(paper, details) {
  const esc = escapeHtml;
  const subject = esc(paper.subject || "Assessment");
  const title = esc(details.examTitle);
  const institution = esc(details.institution);
  const totalMarks = esc(
    paper.achieved_marks ?? paper.requested_marks ?? ""
  );
  const requestedMarks = esc(paper.requested_marks ?? paper.achieved_marks ?? "");
  const completenessBanner = paper.exact_marks ? "" : `<div class="draft-warning"><strong>INCOMPLETE DRAFT — DO NOT PUBLISH</strong><p>Requested ${requestedMarks} marks; generated ${totalMarks} marks. Resolve the constraints before using this assessment.</p></div>`;

  const orderedQuestions = orderedPaperQuestions(paper);
  const questions = orderedQuestions.map((question, index) => {
    const marks = Number(question.marks) || 0;
    const type = String(question.question_type || "").toLowerCase();

    const options = Array.isArray(question.options) &&
      question.options.length
      ? `
        <ol class="options" type="A">
          ${question.options.map((option) => `
            <li>${esc(option)}</li>
          `).join("")}
        </ol>
      `
      : "";

    let answerSpace = "";

    if (type.includes("long") || marks >= 5) {
      answerSpace = `
        <div class="answer-lines long-lines">
          ${Array.from(
            { length: 5 },
            () => "<div></div>"
          ).join("")}
        </div>
      `;
    } else if (type.includes("short") || marks >= 2) {
      const numberOfLines = marks >= 3 ? 3 : 2;

      answerSpace = `
        <div class="answer-lines short-lines">
          ${Array.from(
            { length: numberOfLines },
            () => "<div></div>"
          ).join("")}
        </div>
      `;
    }

    const previousType = index > 0 ? orderedQuestions[index - 1].question_type : "";
    const sectionHeading = index === 0 || question.question_type !== previousType
      ? `<h2 class="question-section-heading">${esc(question.question_type)} Questions</h2>`
      : "";
    return `
      ${sectionHeading}
      <article class="question">
        <div class="question-row">
          <strong class="question-number">${index + 1}.</strong>

          <div class="question-body">
            <div class="question-text">${esc(question.question)}</div>
            ${options}
          </div>

          <strong class="question-marks">
            [${marks} ${marks === 1 ? "mark" : "marks"}]
          </strong>
        </div>

        ${answerSpace}
      </article>
    `;
  }).join("");

  const instructionItems = String(details.instructions)
    .split(/\n|;/)
    .map((line) => line.trim())
    .filter(Boolean);

  const instructionsHtml = instructionItems.map((line) => `
    <li>${esc(line)}</li>
  `).join("");

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title} - ${subject}</title>

<style>
  * {
    box-sizing: border-box;
  }

  html {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  body {
    margin: 0;
    background: #edf0f5;
    color: #111;
    font: 12pt "Times New Roman", Times, serif;
    line-height: 1.45;
  }

  .toolbar {
    position: sticky;
    top: 0;
    z-index: 10;
    display: flex;
    justify-content: center;
    gap: 10px;
    flex-wrap: wrap;
    padding: 12px;
    background: #102544;
  }

  .toolbar button {
    border: 0;
    border-radius: 6px;
    padding: 10px 18px;
    font-size: 13px;
    font-weight: bold;
    cursor: pointer;
  }

  .print-button {
    background: #3268e8;
    color: white;
  }

  .close-button {
    background: white;
    color: #102544;
  }

  .paper {
    width: 210mm;
    min-height: 297mm;
    margin: 18px auto;
    padding: 15mm 17mm 20mm;
    background: white;
    box-shadow: 0 3px 16px #0002;
  }

  .institution-name {
    text-align: center;
    font-size: 18pt;
    font-weight: bold;
    text-transform: uppercase;
    overflow-wrap: anywhere;
    margin: 0 0 2mm;
  }

  .institution-subtitle {
    text-align: center;
    color: #333;
    font-size: 10pt;
    margin-bottom: 5mm;
  }

  .header-rule {
    border: 0;
    border-top: 2px solid #222;
    margin: 4mm 0;
  }

  h1 {
    margin: 5mm 0 2mm;
    text-align: center;
    font-size: 16pt;
    text-transform: uppercase;
  }

  .exam-title {
    text-align: center;
    font-size: 13pt;
    font-weight: bold;
    margin-bottom: 5mm;
    overflow-wrap: anywhere;
  }

  .exam-subtitle {
    text-align: center;
    font-size: 10pt;
    margin-bottom: 5mm;
  }

  .student-details {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 5mm 10mm;
    margin: 7mm 0;
  }

  .detail-line {
    min-height: 8mm;
  }

  .blank {
    display: inline-block;
    min-width: 40mm;
    height: 5mm;
    border-bottom: 1px solid #555;
  }

  .exam-info {
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 4mm;
    padding: 3mm 0;
    margin: 5mm 0;
    border-top: 1px solid #333;
    border-bottom: 1px solid #333;
    font-weight: bold;
  }

  .instructions {
    margin: 6mm 0 8mm;
  }

  .instructions h2 {
    font-size: 12pt;
    margin: 0 0 2mm;
  }

  .instructions ol {
    margin: 0;
    padding-left: 7mm;
  }

  .instructions li {
    margin: 1mm 0;
  }

  .section-heading {
    margin: 7mm 0 4mm;
    padding-bottom: 2mm;
    border-bottom: 1px solid #777;
    font-weight: bold;
  }

  .question {
    margin: 5mm 0 6mm;
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .question-row {
    display: grid;
    grid-template-columns: 8mm minmax(0, 1fr) auto;
    gap: 2mm;
    align-items: start;
  }

  .question-text {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .question-marks {
    white-space: nowrap;
    padding-left: 2mm;
    font-size: 10.5pt;
  }

  .options {
    margin: 2mm 0 0;
    padding-left: 7mm;
  }

  .options li {
    margin: 1mm 0;
  }

  .answer-lines {
    margin: 2mm 0 0 10mm;
  }

  .answer-lines div {
    height: 8mm;
    border-bottom: 1px dotted #999;
  }

  .short-lines div {
    height: 7mm;
  }

  .long-lines div {
    height: 8mm;
  }

  .end-paper {
    text-align: center;
    font-weight: bold;
    margin: 10mm 0 0;
  }

  .signatures {
    display: flex;
    justify-content: space-between;
    gap: 20mm;
    margin-top: 16mm;
  }

  .signature {
    width: 45%;
    text-align: center;
    padding-top: 2mm;
    border-top: 1px solid #555;
    font-size: 10pt;
  }

  /*
   * Automatic page numbering:
   * Supported by recent Chromium-based browsers in print mode.
   * The browser creates the page number in the printed page margin.
   */
  @page {
    size: A4;
    margin: 15mm 16mm 19mm;

    @bottom-left {
      content: "${subject} | ${esc(details.academicYear)}";
      font-family: "Times New Roman", Times, serif;
      font-size: 9pt;
      color: #444;
      border-top: 0.5pt solid #aaa;
      padding-top: 3mm;
    }

    @bottom-right {
      content: "Page " counter(page) " of " counter(pages);
      font-family: "Times New Roman", Times, serif;
      font-size: 9pt;
      color: #444;
      border-top: 0.5pt solid #aaa;
      padding-top: 3mm;
    }
  }

  @media print {
    body {
      background: white;
    }

    .toolbar {
      display: none !important;
    }

    .paper {
      width: auto;
      min-height: 0;
      margin: 0;
      padding: 0;
      box-shadow: none;
    }

    .question {
      break-inside: avoid;
      page-break-inside: avoid;
    }
  }

  @media screen and (max-width: 800px) {
    .paper {
      width: 100%;
      min-height: 0;
      margin: 0;
      padding: 24px 20px 50px;
    }

    .student-details {
      grid-template-columns: 1fr;
    }

    .exam-info {
      display: block;
    }

    .exam-info span {
      display: block;
      margin: 2mm 0;
    }

    .question-row {
      grid-template-columns: 7mm minmax(0, 1fr);
    }

    .question-marks {
      grid-column: 2;
    }
  }
</style>
</head>

<body>
  <div class="toolbar">
    <button class="print-button" id="print-button">
      Download PDF / Print
    </button>
    <button class="close-button" id="close-button">
      Close Tab
    </button>
  </div>

  <main class="paper">
    ${completenessBanner}
    <div class="draft-warning"><strong>DRAFT — TEACHER REVIEW REQUIRED</strong><p>Verify the answer key, syllabus coverage, difficulty, and marking scheme before publishing.</p></div>
    <header>
      <div class="institution-name">${institution}</div>
      <div class="institution-subtitle">
        Academic Year: ${esc(details.academicYear)}
      </div>

      <hr class="header-rule">

      <h1>Question Paper</h1>
      <div class="exam-title">${title}</div>

      <div class="exam-subtitle">
        Subject: ${subject}
        ${details.className
          ? ` | Class / Grade: ${esc(details.className)}`
          : ""}
      </div>

      <hr class="header-rule">
    </header>

    <section class="student-details">
      <div class="detail-line">
        Student Name: <span class="blank"></span>
      </div>

      <div class="detail-line">
        Roll Number: <span class="blank"></span>
      </div>

      <div class="detail-line">
        Class / Grade: ${details.className
          ? esc(details.className)
          : '<span class="blank"></span>'}
      </div>

      <div class="detail-line">
        Date: ${esc(details.examDate)}
      </div>
    </section>

    <div class="exam-info">
      <span>Duration: ${esc(details.duration)}</span>
      <span>Maximum Marks: ${totalMarks}</span>
      <span>Total Questions: ${(paper.questions || []).length}</span>
    </div>

    <section class="instructions">
      <h2>General Instructions</h2>
      <ol>
        ${instructionsHtml}
        <li>Marks are indicated against each question.</li>
      </ol>
    </section>

    <div class="section-heading">Questions</div>

    ${questions}

    <div class="end-paper">— END OF QUESTION PAPER —</div>

    <div class="signatures">
      <div class="signature">Invigilator's Signature</div>
      <div class="signature">Teacher / Examiner's Signature</div>
    </div>
  </main>

  <script>
    document.getElementById("print-button").addEventListener("click", () => {
      window.focus();
      window.print();
    });

    document.getElementById("close-button").addEventListener("click", () => {
      window.close();
    });
  <\/script>
</body>
</html>`;
}

function openPaperInNewTab() {
  if (!currentPaper) {
    alert("Generate a paper first.");
    return;
  }

  const details = askPaperDetails(currentPaper);
  if (!details) return;
  currentPaper.exam_details = {
    ...(currentPaper.exam_details || {}),
    institution: details.institution,
    exam_title: details.examTitle,
    class_name: details.className,
    academic_year: details.academicYear,
    exam_date: details.examDate,
    duration: details.duration,
    instructions: details.instructions.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
  };
  try { localStorage.setItem("evalviaCurrentPaper", JSON.stringify(currentPaper)); }
  catch (error) { console.warn("Could not persist the current paper", error); }
  window.location.href = "/paper";
}

function downloadPaperAsPdf() {
  if (!currentPaper) {
    alert("Generate a paper first.");
    return;
  }

  const details = askPaperDetails(currentPaper);
  if (!details) return;

  currentPaper.exam_details = {
    ...(currentPaper.exam_details || {}),
    institution: details.institution,
    exam_title: details.examTitle,
    class_name: details.className,
    academic_year: details.academicYear,
    exam_date: details.examDate,
    duration: details.duration,
    instructions: details.instructions.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
  };
  try { localStorage.setItem("evalviaCurrentPaper", JSON.stringify(currentPaper)); }
  catch (error) { console.warn("Could not persist the current paper", error); }
  window.location.href = "/paper?print=1";
}

$("view-paper-btn")?.addEventListener("click", openPaperInNewTab);

$("pdf-btn")?.addEventListener("click", downloadPaperAsPdf);

$("subject")?.addEventListener("change", () => {
  buildTopicFields($("subject").value);
  refreshCapacity().catch((error) => showSourceStatus(error.message, true));
});

$("generator-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();

  const button = $("generate-btn");
  button.disabled = true;
  button.textContent = "Generating…";

  try {
    const paper = await api("/api/generate", {
      subject: $("subject").value,
      total_marks: Number($("total-marks").value),
      mixes: readMixes(),
      seed: Math.floor(Math.random() * 100000),
      exam_title: $("exam-title").value.trim() || "Question Paper",
      class_name: $("class-name").value.trim(),
      duration: $("duration").value.trim() || "2 hours",
      instructions: $("instructions").value.split("\n").map((line) => line.trim()).filter(Boolean)
    });

    renderPaper(paper);
    openPaperInNewTab();
  } catch (error) {
    showError(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = 'Generate paper <span>↗</span>';
  }
});

$("sample-btn")?.addEventListener("click", async () => {
  $("subject").value = "Maths";
  $("total-marks").value = 40;
  $("easy").value = 30;
  $("medium").value = 50;
  $("hard").value = 20;
  $("mcq").value = 40;
  $("short").value = 40;
  $("long").value = 20;

  buildTopicFields("Maths", {
    Algebra: 30,
    Geometry: 25,
    Trigonometry: 25,
    Statistics: 20
  });

  try {
    const paper = await api("/api/sample-paper");
    renderPaper(paper);
    openPaperInNewTab();
  } catch (error) {
    showError(error.message);
  }
});

$("export-btn")?.addEventListener("click", () => {
  if (!currentPaper) return;

  let text = `${String(currentPaper.exam_details?.exam_title || currentPaper.subject + " QUESTION PAPER").toUpperCase()}\n`;
  text += `Subject: ${currentPaper.subject}\n`;
  if (currentPaper.exam_details?.class_name) text += `Class: ${currentPaper.exam_details.class_name}\n`;
  if (currentPaper.exam_details?.duration) text += `Duration: ${currentPaper.exam_details.duration}\n`;
  text += `Total marks: ${currentPaper.achieved_marks} / ${currentPaper.requested_marks}\n`;
  if (!currentPaper.exact_marks) text += `STATUS: INCOMPLETE DRAFT — DO NOT PUBLISH\n`;
  text += `\n`;
  (currentPaper.exam_details?.instructions || []).forEach((line) => { text += `- ${line}\n`; });
  text += `\n`;

  orderedPaperQuestions(currentPaper).forEach((question, index) => {
    text += `${index + 1}. (${question.marks} mark${
      Number(question.marks) === 1 ? "" : "s"
    }) ${question.question}\n`;

    if (Array.isArray(question.options)) {
      question.options.forEach((option, optionIndex) => {
        text += `   ${String.fromCharCode(65 + optionIndex)}. ${option}\n`;
      });
    }

    text += "\n";
  });

  const blob = new Blob([text], {
    type: "text/plain;charset=utf-8"
  });

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download =
    `${String(currentPaper.subject).toLowerCase()}-student-question-paper.txt`;

  document.body.appendChild(link);
  link.click();
  link.remove();

  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

$("answer-key-btn")?.addEventListener("click", () => {
  if (!currentPaper) return;
  let text = `TEACHER ANSWER KEY\n${currentPaper.exam_details?.exam_title || currentPaper.subject + " Assessment"}\n`;
  text += `Subject: ${currentPaper.subject}\n`;
  text += `Marks: ${currentPaper.achieved_marks} / ${currentPaper.requested_marks}\n\n`;
  orderedPaperQuestions(currentPaper).forEach((question, index) => {
    text += `${index + 1}. [${question.marks} marks] ${question.answer || "REVIEW REQUIRED — answer not provided"}\n`;
    if (question.marking_scheme) text += `   Marking scheme: ${question.marking_scheme}\n`;
  });
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${String(currentPaper.subject).toLowerCase()}-teacher-answer-key.txt`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

$("synthesis-btn")?.addEventListener("click", async () => {
  const button = $("synthesis-btn");
  button.disabled = true;
  button.textContent = "Finding candidates…";
  try {
    const data = await api("/api/synthesis-proposals", {
      subject: $("subject").value,
      max_pairs: 10
    });
    const panel = $("synthesis-results");
    if (!panel) return;
    if (!data.proposals.length) {
      panel.textContent = "No same-topic Medium question pairs found. Add reviewed questions or use a different topic.";
    } else {
      panel.innerHTML = `<strong>Review-only synthesis candidates</strong><p>${escapeHtml(data.message)}</p>` + data.proposals.map((proposal) => `
        <article class="question-card synthesis-card">
          <div class="q-top"><strong>${escapeHtml(proposal.topic)} · ${escapeHtml(proposal.proposed_marks)} marks</strong><span class="chip">Needs teacher review</span></div>
          <p>${escapeHtml(proposal.draft_question)}</p>
          <small>Sources: ${proposal.source_ids.map(escapeHtml).join(", ")}. This is a compound-question proposal, not automatically classified as Hard.</small>
        </article>`).join("");
    }
    panel.classList.remove("hidden");
  } catch (error) {
    showSourceStatus(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Find synthesis candidates";
  }
});

function showSourceStatus(message, isError = false) {
  const status = $("source-status");
  if (!status) return;
  status.textContent = message;
  status.classList.toggle("error", isError);
}

async function refreshCapacity() {
  const subject = $("subject")?.value || "Maths";
  const capacity = await api(`/api/capacity/${encodeURIComponent(subject)}`);
  const target = Number($("total-marks")?.value || 0);
  const node = $("capacity-note");
  if (node) {
    node.textContent = `${capacity.subject} bank: ${capacity.question_count} questions · ${capacity.available_marks_sum} marks summed across the bank. Requested paper: ${target} marks. This is an upper bound, not a guarantee of a feasible exact total.`;
    node.classList.toggle("warning", target > capacity.available_marks_sum);
  }
}

function updateMixTotals() {
  const difficultyTotal = pct("easy") + pct("medium") + pct("hard");
  const typeTotal = pct("mcq") + pct("short") + pct("long");
  const difficultyNode = $("difficulty-total");
  const typeNode = $("type-total");
  if (difficultyNode) difficultyNode.textContent = `Entered total: ${difficultyTotal}% · normalized automatically`;
  if (typeNode) typeNode.textContent = `Entered total: ${typeTotal}% · normalized automatically`;
}

async function uploadFile(endpoint, inputId, label) {
  const input = $(inputId);
  const file = input?.files?.[0];
  if (!file) throw new Error(`Choose a ${label} file first.`);
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(endpoint, { method: "POST", body: form });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Could not load ${label}.`);
  return data;
}

$("validate-bank-btn")?.addEventListener("click", async () => {
  const button = $("validate-bank-btn");
  button.disabled = true;
  try {
    const data = await uploadFile("/api/validate-bank", "bank-upload", "question bank");
    const warningText = data.warnings?.length ? ` Warnings: ${data.warnings.join(" ")}` : " No import warnings.";
    showSourceStatus(`Validation passed: ${data.question_count} questions. Maths: ${data.subject_counts.Maths} questions / ${data.available_marks.Maths} marks; Science: ${data.subject_counts.Science} questions / ${data.available_marks.Science} marks. Select Load bank to activate it.${warningText}`, Boolean(data.warnings?.length));
  } catch (error) {
    showSourceStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("reset-bank-btn")?.addEventListener("click", async () => {
  if (!window.confirm("Restore the bundled sample bank? Your currently saved custom bank will be replaced.")) return;
  const button = $("reset-bank-btn");
  button.disabled = true;
  try {
    const data = await api("/api/reset-bank", {});
    optionsData = await api("/api/options");
    buildTopicFields($("subject").value);
    if ($("bank-count")) $("bank-count").textContent = String(data.question_count);
    await refreshCapacity();
    showSourceStatus(data.message, false);
  } catch (error) {
    showSourceStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("upload-bank-btn")?.addEventListener("click", async () => {
  const button = $("upload-bank-btn");
  button.disabled = true;
  try {
    const data = await uploadFile("/api/upload-bank", "bank-upload", "question bank");
    const warningText = data.warnings?.length ? ` Warnings: ${data.warnings.join(" ")}` : "";
    showSourceStatus(`Loaded and saved ${data.question_count} questions. Subjects: ${data.subjects.join(", ")}.${warningText}`, Boolean(data.warnings?.length));
    optionsData = await api("/api/options");
    if (!optionsData[$("subject").value]?.topics?.length) {
      $("subject").value = data.subjects.find((subject) => optionsData[subject]?.topics?.length) || "Maths";
    }
    buildTopicFields($("subject").value);
    if ($("bank-count")) $("bank-count").textContent = String(data.question_count);
    await refreshCapacity();
  } catch (error) {
    showSourceStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("upload-textbook-btn")?.addEventListener("click", async () => {
  const button = $("upload-textbook-btn");
  button.disabled = true;
  try {
    const data = await uploadFile("/api/upload-textbook", "textbook-upload", "textbook PDF");
    showSourceStatus(data.message || `Extracted text from ${data.filename}.`);
    const preview = $("textbook-preview");
    if (preview) {
      preview.textContent = `${data.filename} · ${data.pages} pages · ${data.characters_extracted} characters\n\n${data.preview || ""}`;
      preview.classList.remove("hidden");
    }
  } catch (error) {
    showSourceStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("total-marks")?.addEventListener("input", () => {
  refreshCapacity().catch(() => {});
});
["easy", "medium", "hard", "mcq", "short", "long"].forEach((id) => {
  $(id)?.addEventListener("input", updateMixTotals);
});
(async function initialize() {
  try {
    optionsData = await api("/api/options");

    if ($("bank-count")) {
      $("bank-count").textContent = String((await api("/api/health")).question_count);
    }

    buildTopicFields("Maths", {
      Algebra: 30,
      Geometry: 25,
      Trigonometry: 25,
      Statistics: 20
    });
    updateMixTotals();
    await refreshCapacity();
  } catch (error) {
    console.error("Could not load generator options:", error);
  }
})();
