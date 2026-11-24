"use client";

import { useState } from "react";
import type { LessonPayload } from "@/a2ui/lessonCardSchema";
import type { QuizPayload } from "@/a2ui/quizCardSchema";
import { QuizCard } from "@/components/QuizCard";
import { ApiError, approveLesson, editLesson, getQuiz } from "@/lib/api";

export function LessonCard({
  lesson,
  testId = "lesson-card",
  onChange,
}: {
  lesson: LessonPayload;
  testId?: string;
  onChange?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(lesson.title);
  const [body, setBody] = useState(lesson.body);
  const [quiz, setQuiz] = useState<QuizPayload | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const author = lesson.can_author === true;

  async function approve() {
    setBusy(true);
    setError("");
    try {
      await approveLesson(lesson.id);
      onChange?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The lesson could not be approved.");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    setError("");
    try {
      await editLesson(lesson.id, { title, body });
      setEditing(false);
      onChange?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The lesson could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function openQuiz() {
    if (!lesson.quiz_id) return;
    setBusy(true);
    setError("");
    try {
      setQuiz(await getQuiz(lesson.quiz_id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The quiz could not be opened.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="panel p-3" data-testid={testId}>
      <p className="text-xs uppercase tracking-wide text-muted">{lesson.position}</p>
      <h3 className="mt-2 text-base font-medium">{lesson.title}</h3>
      {editing ? (
        <div className="mt-3 space-y-2">
          <label className="lbl" htmlFor={`lesson-title-${lesson.id}`}>
            Title
            <input id={`lesson-title-${lesson.id}`} className="field" value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label className="lbl" htmlFor={`lesson-body-${lesson.id}`}>
            Lesson
            <textarea
              id={`lesson-body-${lesson.id}`}
              data-testid="lesson-body"
              className="field-area"
              value={body}
              onChange={(event) => setBody(event.target.value)}
            />
          </label>
          <button type="button" data-testid="lesson-save" className="btn btn-primary w-full" disabled={busy} onClick={() => void save()}>
            Save lesson
          </button>
        </div>
      ) : (
        <p className="mt-2 text-sm leading-6">{lesson.body}</p>
      )}
      {(lesson.standards || []).length > 0 && (
        <p className="mt-2 text-sm text-muted">{(lesson.standards || []).map((row) => row.title).join(" · ")}</p>
      )}
      {(lesson.bottles || []).length > 0 && (
        <p className="mt-1 text-sm text-muted">{(lesson.bottles || []).map((row) => row.name).join(" · ")}</p>
      )}
      <div className="mt-3 flex flex-col gap-2">
        {author && lesson.status === "draft" && (
          <button type="button" data-testid="lesson-approve" className="btn btn-primary w-full" disabled={busy} onClick={() => void approve()}>
            Approve lesson
          </button>
        )}
        {author && !editing && (
          <button type="button" data-testid="lesson-edit" className="btn btn-secondary w-full" disabled={busy} onClick={() => setEditing(true)}>
            Edit lesson
          </button>
        )}
        {lesson.quiz_id && lesson.status === "approved" && !quiz && (
          <button type="button" data-testid="lesson-quiz" className="btn btn-secondary w-full" disabled={busy} onClick={() => void openQuiz()}>
            Take quiz
          </button>
        )}
      </div>
      {error && (
        <p className="banner-error mt-3" role="alert">
          {error}
        </p>
      )}
      {quiz && (
        <div className="mt-3">
          <QuizCard quiz={quiz} />
        </div>
      )}
    </article>
  );
}
