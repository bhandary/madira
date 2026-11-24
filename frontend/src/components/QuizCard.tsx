"use client";

import { useState } from "react";
import type { QuizPayload } from "@/a2ui/quizCardSchema";
import { ApiError, submitQuizAttempt } from "@/lib/api";

export function QuizCard({ quiz }: { quiz: QuizPayload }) {
  const [picks, setPicks] = useState<Record<string, number>>({});
  const [result, setResult] = useState<QuizPayload | null>(quiz.score == null ? null : quiz);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const questions = quiz.questions || [];
  const shown = result || quiz;
  const review = shown.review || [];
  const complete = questions.every((question) => picks[question.id] != null);

  async function submit() {
    if (!complete || busy) return;
    setBusy(true);
    setError("");
    try {
      const graded = await submitQuizAttempt(
        quiz.id,
        questions.map((question) => picks[question.id]),
      );
      setResult(graded);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The quiz could not be scored.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel p-3" data-testid="quiz-card">
      <h3 className="text-base font-medium">{shown.title || "Quiz"}</h3>
      {shown.score != null && (
        <p className="mt-1 text-sm" data-testid="quiz-score">
          Score {String(shown.score)}% ({String(shown.correct)}/{String(shown.total)})
        </p>
      )}
      {shown.next_review_on && (
        <p className="mt-1 text-sm text-muted" data-testid="quiz-next-review">
          Next review {shown.next_review_on}
        </p>
      )}
      <ol className="mt-3 space-y-3">
        {questions.map((question, index) => {
          const note = review[index];
          return (
            <li key={question.id}>
              <fieldset data-testid="quiz-question" className="space-y-2">
                <legend className="text-sm font-medium">{question.prompt}</legend>
                {result ? (
                  <ul className="text-sm text-muted">
                    {(question.choices || []).map((choice, choiceIndex) => (
                      <li key={choice}>{choiceIndex}. {choice}</li>
                    ))}
                  </ul>
                ) : (
                  (question.choices || []).map((choice, choiceIndex) => (
                    <button
                      key={choice}
                      type="button"
                      data-testid="quiz-choice"
                      aria-pressed={picks[question.id] === choiceIndex}
                      className="btn btn-segment w-full text-left"
                      onClick={() => setPicks((current) => ({ ...current, [question.id]: choiceIndex }))}
                    >
                      {choice}
                    </button>
                  ))
                )}
                {note && (
                  <p className="text-sm text-ok">
                    {note.ok ? "Correct. " : "Missed. "}
                    {note.explain}
                  </p>
                )}
              </fieldset>
            </li>
          );
        })}
      </ol>
      {!result && questions.length > 0 && (
        <button type="button" data-testid="quiz-submit" className="btn btn-primary mt-3 w-full" disabled={!complete || busy} onClick={() => void submit()}>
          {busy ? "Scoring…" : "Submit answers"}
        </button>
      )}
      {error && (
        <p className="banner-error mt-3" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
