import { useEffect, useRef, useState, type MouseEvent } from "react";
import api from "../../api/client";
import type { Quiz } from "../../api/types";
import MathText from "../notebooks/MathText";

const DIFFICULTY_EMOJI: Record<Quiz["difficulty"], string> = {
  easy: "😊",
  medium: "😐",
  hard: "🤯",
};

const DIFFICULTY_LABEL: Record<Quiz["difficulty"], string> = {
  easy: "Easy",
  medium: "Medium",
  hard: "Hard",
};

const SOURCE_ICON: Record<Quiz["source_type"], string> = {
  pdf: "📄",
  pptx: "📊",
  mp3: "🎧",
};

const RING_RADIUS = 40;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

// Mirrors backend's quiz.MAX_QUESTIONS_PER_QUIZ — the backend is the real
// enforcement point, this is just so the button can hide itself instead of
// letting the user hit a 409 for an obviously-already-maxed quiz.
const MAX_QUESTIONS_PER_QUIZ = 100;

// Mirrors backend's settings.quiz_generation_limit — a cap on how many
// quizzes a user can have AT ONCE (deleting one frees up a slot). The
// backend is the real enforcement point; this just lets the upload form
// hide itself with an accurate message instead of failing with a 429.
// quizzes.length is an accurate live count of this because GET /quizzes
// is capped at this same limit server-side.
const MAX_QUIZZES_PER_USER = 30;

export default function Trivisum() {
  const [quizzes, setQuizzes] = useState<Quiz[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const [language, setLanguage] = useState<"en" | "he">("en");
  const [difficulty, setDifficulty] = useState<Quiz["difficulty"]>("medium");

  const [currentIndex, setCurrentIndex] = useState(0);
  const [userAnswers, setUserAnswers] = useState<Record<number, string>>({});
  const [showExplanation, setShowExplanation] = useState(false);
  const [showResults, setShowResults] = useState(false);
  // Snapshot of how many questions existed when results were entered — the
  // results screen scores against this, not the live (possibly-growing,
  // via "generate more") questions array, so the ring/score displayed
  // can't silently shift while the user is looking at a result they
  // already finished.
  const [resultsCount, setResultsCount] = useState<number | null>(null);
  // How many questions existed right before a "generate more" click, so
  // completion can be detected (by comparing against the new count) and
  // distinguished from "found nothing new" without the backend needing to
  // persist that distinction itself.
  const [preGenerateCount, setPreGenerateCount] = useState<number | null>(null);
  const [newQuestionsReady, setNewQuestionsReady] = useState<number | null>(null);
  const [noMoreFound, setNoMoreFound] = useState(false);
  const [generateMoreError, setGenerateMoreError] = useState("");
  const wasGeneratingMore = useRef(false);

  // Opening a different quiz (or the same one again) always starts fresh.
  useEffect(() => {
    setCurrentIndex(0);
    setUserAnswers({});
    setShowExplanation(false);
    setShowResults(false);
    setResultsCount(null);
    setPreGenerateCount(null);
    setNewQuestionsReady(null);
    setNoMoreFound(false);
    setGenerateMoreError("");
    wasGeneratingMore.current = false;
  }, [selectedId]);

  async function load() {
    const { data } = await api.get<Quiz[]>("/quizzes");
    setQuizzes(data);
    return data;
  }

  useEffect(() => {
    load();
  }, []);

  // While any quiz is still being generated (initial or "generate more"),
  // poll every 3 s.
  useEffect(() => {
    if (!quizzes.some((q) => q.status === "pending" || q.status === "running" || q.generating_more)) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [quizzes]);

  async function upload(file: File) {
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("language", language);
      form.append("difficulty", difficulty);
      await api.post("/quizzes", form);
      await load();
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Could not upload — try again");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function remove(q: Quiz, e: MouseEvent) {
    e.stopPropagation();
    if (!window.confirm(`Delete "${q.title ?? q.original_filename}"? This can't be undone.`)) return;
    await api.delete(`/quizzes/${q.id}`);
    if (selectedId === q.id) setSelectedId(null);
    await load();
  }

  const selected = quizzes.find((q) => q.id === selectedId) ?? null;
  const selectedQuestionCount = selected?.questions?.length ?? 0;

  async function generateMore() {
    if (!selected) return;
    setGenerateMoreError("");
    setNewQuestionsReady(null);
    setNoMoreFound(false);
    setPreGenerateCount(selectedQuestionCount);
    try {
      await api.post(`/quizzes/${selected.id}/generate-more`);
      await load();
    } catch (err: any) {
      setGenerateMoreError(err.response?.data?.detail ?? "Could not start — try again");
      setPreGenerateCount(null);
    }
  }

  // Detects a "generate more" job finishing by watching generating_more
  // flip true -> false, then compares the question count against what it
  // was right before the click — the backend only tells us the operation
  // finished, not whether it actually found anything new, so that
  // distinction is inferred here rather than persisted server-side.
  useEffect(() => {
    const isGenerating = selected?.generating_more ?? false;
    if (wasGeneratingMore.current && !isGenerating && preGenerateCount !== null) {
      if (!selected?.generate_more_error) {
        const added = selectedQuestionCount - preGenerateCount;
        if (added > 0) setNewQuestionsReady(added);
        else setNoMoreFound(true);
      }
      setPreGenerateCount(null);
    }
    wasGeneratingMore.current = isGenerating;
  }, [selected?.generating_more, selectedQuestionCount, selected?.generate_more_error, preGenerateCount]);

  // ---------- Detail view (quiz-taking) ----------
  if (selected && selected.status === "done") {
    const questions = selected.questions ?? [];
    if (questions.length === 0) {
      return (
        <div>
          <button className="btn btn-ghost btn-sm" onClick={() => setSelectedId(null)}>
            ← Back to quizzes
          </button>
          <div className="empty" style={{ marginTop: 16 }}>
            This quiz has no valid questions — try regenerating it from the source PDF.
          </div>
        </div>
      );
    }

    const quizTitle = selected.title ?? selected.original_filename;
    const quizLanguage = selected.language;
    const contentDir = quizLanguage === "he" ? "rtl" : "auto";
    const textAlign: "right" | "left" = quizLanguage === "he" ? "right" : "left";
    const mathDir: "rtl" | "ltr" = quizLanguage === "he" ? "rtl" : "ltr";

    const clampedIndex = Math.min(currentIndex, questions.length - 1);
    const current = questions[clampedIndex];
    const userAnswer = userAnswers[clampedIndex];

    function selectOption(option: string) {
      setUserAnswers((prev) => ({ ...prev, [clampedIndex]: option }));
    }

    // Nothing is revealed until the user actually picks something — unlike
    // the original Trivisum, which subtly marked the correct option even
    // before an answer was chosen.
    function optionClass(option: string) {
      if (!userAnswer) return "quiz-option";
      if (option === current.answer) return "quiz-option correct";
      if (option === userAnswer) return "quiz-option incorrect";
      return "quiz-option";
    }

    function goNext() {
      setShowExplanation(false);
      if (clampedIndex < questions.length - 1) {
        setCurrentIndex(clampedIndex + 1);
      } else {
        // Freeze the count used for scoring at the moment of finishing —
        // "generate more" can append questions while this screen is up,
        // and the score for a result already reached shouldn't shift.
        setResultsCount(questions.length);
        setShowResults(true);
      }
    }

    function goPrev() {
      setShowExplanation(false);
      setCurrentIndex(Math.max(0, clampedIndex - 1));
    }

    const scoringCount = resultsCount ?? questions.length;
    const scoringQuestions = questions.slice(0, scoringCount);
    const correctCount = scoringQuestions.reduce(
      (count, q, i) => (q.answer === userAnswers[i] ? count + 1 : count),
      0
    );
    const answeredCount = Object.keys(userAnswers).filter((k) => Number(k) < scoringCount).length;
    const incorrectCount = answeredCount - correctCount;
    const percentage = scoringCount > 0 ? (correctCount / scoringCount) * 100 : 0;
    const strokeDash = (percentage / 100) * RING_CIRCUMFERENCE;

    if (showResults) {
      const canGenerateMore = selected.can_generate_more && questions.length < MAX_QUESTIONS_PER_QUIZ;

      function backToQuestions() {
        setCurrentIndex(0);
        setShowResults(false);
        setResultsCount(null);
      }

      function retry() {
        setCurrentIndex(0);
        setUserAnswers({});
        setShowResults(false);
        setResultsCount(null);
      }

      function continueWithNewQuestions() {
        if (newQuestionsReady === null) return;
        setCurrentIndex(questions.length - newQuestionsReady);
        setShowResults(false);
        setResultsCount(null);
        setNewQuestionsReady(null);
      }

      return (
        <div style={{ maxWidth: 480 }}>
          <button
            className="btn btn-ghost btn-sm no-print"
            style={{ marginBottom: 16 }}
            onClick={() => setSelectedId(null)}
          >
            ← Back to quizzes
          </button>
          <div className="panel quiz-results">
            <h1 style={{ textAlign: "center", margin: "0 0 20px" }}>Results</h1>
            <div className="quiz-ring-wrap">
              <svg className="quiz-ring" viewBox="0 0 100 100">
                <circle className="quiz-ring-bg" cx="50" cy="50" r={RING_RADIUS} />
                <circle
                  className="quiz-ring-fg"
                  cx="50"
                  cy="50"
                  r={RING_RADIUS}
                  style={{ strokeDasharray: `${strokeDash} ${RING_CIRCUMFERENCE}` }}
                />
              </svg>
              <div className="quiz-ring-text">
                <span className="quiz-ring-score">{correctCount}</span>
                <span className="quiz-ring-total"> / {scoringCount}</span>
              </div>
            </div>
            <div className="quiz-results-stats">
              <span>✔ Correct: {correctCount}</span>
              <span>✖ Incorrect: {incorrectCount}</span>
            </div>
            <div className="quiz-results-actions">
              <button className="btn btn-ghost" onClick={backToQuestions}>
                Back to Questions
              </button>
              <button className="btn btn-yellow" onClick={retry}>
                Retry
              </button>
            </div>

            {canGenerateMore && (
              <div className="quiz-generate-more">
                {selected.generating_more ? (
                  <span className="meta">Generating more questions…</span>
                ) : newQuestionsReady ? (
                  <button className="btn btn-yellow" onClick={continueWithNewQuestions}>
                    Continue with {newQuestionsReady} new question{newQuestionsReady === 1 ? "" : "s"} →
                  </button>
                ) : noMoreFound ? (
                  <span className="meta">No more distinct questions could be found in this source.</span>
                ) : (
                  <button className="btn btn-ghost" onClick={generateMore}>
                    ✨ Generate More Questions
                  </button>
                )}
                {generateMoreError && (
                  <div className="auth-error" style={{ marginTop: 8 }}>{generateMoreError}</div>
                )}
              </div>
            )}
          </div>
        </div>
      );
    }

    return (
      <div style={{ maxWidth: 680 }}>
        <div className="no-print" style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <button className="btn btn-ghost btn-sm" onClick={() => setSelectedId(null)}>
            ← Back to quizzes
          </button>
          <span className="meta" dir="ltr">
            {clampedIndex + 1} / {questions.length}
          </span>
        </div>

        <div className="panel quiz-question-panel">
          <div className="meta" dir="auto" style={{ marginBottom: 4 }}>
            {quizTitle}
          </div>
          <h2 className="quiz-question" dir={contentDir} style={{ textAlign }}>
            <MathText text={current.question} dir={mathDir} />
          </h2>
          <ul className="quiz-options">
            {current.options.map((opt, i) => (
              <li
                key={i}
                className={optionClass(opt)}
                dir={contentDir}
                style={{ textAlign }}
                onClick={() => selectOption(opt)}
              >
                <span className="quiz-option-text">
                  <MathText text={opt} dir={mathDir} />
                </span>
                {userAnswer && opt === current.answer && <span className="quiz-mark">✔</span>}
                {userAnswer === opt && opt !== current.answer && <span className="quiz-mark">✖</span>}
              </li>
            ))}
          </ul>

          <div className="quiz-nav">
            <button className="btn btn-ghost btn-sm" onClick={goPrev} disabled={clampedIndex === 0}>
              ← Previous
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setShowExplanation((s) => !s)}>
              💡 Explanation
            </button>
            <button className="btn btn-yellow btn-sm" onClick={goNext}>
              {clampedIndex === questions.length - 1 ? "Finish" : "Next →"}
            </button>
          </div>

          {showExplanation && (
            <div className="quiz-explanation" dir={contentDir} style={{ textAlign }}>
              <strong>Explanation</strong>
              <p>
                <MathText text={current.explanation} dir={mathDir} />
              </p>
            </div>
          )}
        </div>
      </div>
    );
  }

  // ---------- List view ----------
  const atQuizLimit = quizzes.length >= MAX_QUIZZES_PER_USER;

  return (
    <div>
      <h1>📝 Trivisum</h1>
      <p className="page-sub">
        Upload a PDF — we'll turn it into a multiple-choice practice quiz with an explanation for
        every answer.
      </p>

      <div className="panel" style={{ maxWidth: 560 }}>
        <div className="meta" style={{ marginBottom: 14 }} dir="ltr">
          {quizzes.length} / {MAX_QUIZZES_PER_USER} quizzes
        </div>
        {atQuizLimit ? (
          <div className="empty">
            You've reached the limit of {MAX_QUIZZES_PER_USER} quizzes. Delete one below to make
            room for a new one.
          </div>
        ) : (
          <>
            <label>Quiz language</label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value as "en" | "he")}
              disabled={uploading}
              style={{ marginBottom: 14 }}
            >
              <option value="en">English</option>
              <option value="he">עברית (Hebrew)</option>
            </select>
            <label>Difficulty</label>
            <select
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value as Quiz["difficulty"])}
              disabled={uploading}
              style={{ marginBottom: 14 }}
            >
              <option value="easy">Easy 😊</option>
              <option value="medium">Medium 😐</option>
              <option value="hard">Hard 🤯</option>
            </select>
            <label>Upload source (PDF/PPTX up to 20 MB, MP3 up to 150 MB)</label>
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.pptx,.mp3,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation,audio/mpeg"
              disabled={uploading}
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
            />
            {error && <div className="auth-error" style={{ marginTop: 8 }}>{error}</div>}
          </>
        )}
      </div>

      <div className="stack" style={{ marginTop: 20 }}>
        {quizzes.map((q) => (
          <div
            className={`panel${q.status === "done" ? " list-card" : ""}`}
            key={q.id}
            style={{ cursor: q.status === "done" ? "pointer" : "default" }}
            onClick={() => q.status === "done" && setSelectedId(q.id)}
          >
            <h3 style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, margin: 0 }}>
              <span dir="auto">
                <span dir="ltr">{SOURCE_ICON[q.source_type]}</span> {q.title ?? q.original_filename}
              </span>
              {q.status === "done" && <span className="badge done">ready</span>}
              {q.status === "failed" && <span className="badge failed">failed</span>}
              {(q.status === "pending" || q.status === "running") && (
                <span className="badge pending">{q.status === "pending" ? "queued" : "generating…"}</span>
              )}
            </h3>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 6 }}>
              <span className="meta">
                {DIFFICULTY_EMOJI[q.difficulty]} {DIFFICULTY_LABEL[q.difficulty]} ·{" "}
                {q.language === "he" ? "Hebrew" : "English"} ·{" "}
                {new Date(q.created_at).toLocaleString()}
              </span>
              <button className="btn btn-danger btn-sm" onClick={(e) => remove(q, e)}>
                Delete
              </button>
            </div>
            {q.status === "failed" && q.error && (
              <div className="auth-error" style={{ marginTop: 8 }}>{q.error}</div>
            )}
          </div>
        ))}
        {quizzes.length === 0 && (
          <div className="empty">Upload a PDF above to generate your first quiz.</div>
        )}
      </div>
    </div>
  );
}
