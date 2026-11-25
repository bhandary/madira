"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AgentWorkbench } from "@/components/AgentWorkbench";
import { LessonCard } from "@/components/LessonCard";
import { RoleplayPanel } from "@/components/RoleplayPanel";
import { TeamDesk } from "@/components/TeamDesk";
import {
  ApiError,
  draftTrainingLesson,
  getDueReviews,
  getTrainingLessons,
  startRoleplay,
  type DueReview,
  type RoleplaySession,
  type TrainingLessons,
} from "@/lib/api";

const POSITIONS = ["server", "bartender", "barback", "host", "all"] as const;
const PERSONAS = [
  ["skeptic", "Skeptic"],
  ["budget-conscious", "Budget-conscious"],
  ["connoisseur", "Connoisseur"],
  ["celebration", "Celebration"],
] as const;

export default function TrainingPage() {
  const [data, setData] = useState<TrainingLessons | null>(null);
  const [due, setDue] = useState<DueReview[]>([]);
  const [tab, setTab] = useState<"lessons" | "due" | "practice" | "team" | "drafts">("lessons");
  const [persona, setPersona] = useState<(typeof PERSONAS)[number][0]>("skeptic");
  const [dish, setDish] = useState("");
  const [session, setSession] = useState<RoleplaySession | null>(null);
  const [position, setPosition] = useState<(typeof POSITIONS)[number]>("server");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [lessons, reviews] = await Promise.all([getTrainingLessons(), getDueReviews()]);
    setData(lessons);
    setDue(reviews.reviews);
  }, []);

  useEffect(() => {
    let live = true;
    Promise.all([getTrainingLessons(), getDueReviews()])
      .then(([lessons, reviews]) => {
        if (!live) return;
        setData(lessons);
        setDue(reviews.reviews);
      })
      .catch((err: unknown) => {
        if (!live) return;
        setError(err instanceof ApiError ? err.message : "Lessons could not be loaded.");
      });
    return () => {
      live = false;
    };
  }, []);

  async function draft() {
    setBusy(true);
    setError("");
    try {
      await draftTrainingLesson(position);
      await refresh();
      setTab("drafts");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The lesson could not be drafted.");
    } finally {
      setBusy(false);
    }
  }

  async function beginRoleplay() {
    setBusy(true);
    setError("");
    try {
      const next = await startRoleplay(persona, dish);
      setSession(next.session);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The roleplay could not start.");
    } finally {
      setBusy(false);
    }
  }

  const canManage = data?.role === "Owner" || data?.role === "Manager";
  const lessons = tab === "drafts" ? data?.drafts || [] : data?.lessons || [];

  return (
    <AgentWorkbench
      testId="training-workbench"
      title="Staff training"
      blurb="Lessons for each role, a quiz from the list, and reviews that come back on a schedule."
      prompt="List my lessons."
    >
      <p className="mt-4 text-sm" data-testid="training-actor">
        {data ? `${data.name} · ${data.role}` : "Loading lessons"}
      </p>
      <div className="mt-3 flex flex-col gap-2" role="tablist" aria-label="Training">
        <button type="button" className="btn btn-segment w-full" data-testid="tab-lessons" aria-pressed={tab === "lessons"} onClick={() => setTab("lessons")}>
          My lessons
        </button>
        <button type="button" className="btn btn-segment w-full" data-testid="tab-due" aria-pressed={tab === "due"} onClick={() => setTab("due")}>
          Due for review{due.length ? ` (${due.length})` : ""}
        </button>
        <button type="button" className="btn btn-segment w-full" data-testid="tab-practice" aria-pressed={tab === "practice"} onClick={() => setTab("practice")}>
          Practice
        </button>
        {canManage && (
          <button type="button" className="btn btn-segment w-full" data-testid="tab-team" aria-pressed={tab === "team"} onClick={() => setTab("team")}>
            Team
          </button>
        )}
        {data?.can_author && (
          <button type="button" className="btn btn-segment w-full" data-testid="tab-drafts" aria-pressed={tab === "drafts"} onClick={() => setTab("drafts")}>
            Drafts
          </button>
        )}
      </div>
      {data?.can_author && (
        <div className="mt-4 space-y-2">
          <label className="lbl" htmlFor="lesson-position">
            Position
            <select
              id="lesson-position"
              data-testid="lesson-position"
              className="field"
              value={position}
              onChange={(event) => setPosition(event.target.value as (typeof POSITIONS)[number])}
            >
              {POSITIONS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <button type="button" data-testid="lesson-draft" className="btn btn-primary w-full" disabled={busy} onClick={() => void draft()}>
            {busy ? "Drafting…" : "Draft lesson"}
          </button>
          <Link href="/training/standards" className="btn btn-secondary w-full" data-testid="standards-link">
            Service standards
          </Link>
        </div>
      )}
      {error && (
        <p className="banner-error mt-3" role="alert" data-testid="training-error">
          {error}
        </p>
      )}
      {tab === "practice" ? (
        <div className="mt-4 space-y-3">
          <div className="flex flex-col gap-2">
            {PERSONAS.map(([value, label]) => (
              <button
                key={value}
                type="button"
                className="btn btn-segment w-full"
                data-testid={`roleplay-persona-${value}`}
                aria-pressed={persona === value}
                onClick={() => setPersona(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="lbl" htmlFor="roleplay-dish">
            Dish
            <input id="roleplay-dish" className="field" data-testid="roleplay-dish" value={dish} onChange={(event) => setDish(event.target.value)} />
          </label>
          <button type="button" className="btn btn-primary w-full" data-testid="roleplay-start" disabled={busy} onClick={() => void beginRoleplay()}>
            Start roleplay
          </button>
          {session && <RoleplayPanel session={session} onSession={setSession} />}
        </div>
      ) : tab === "team" && canManage && data ? (
        <TeamDesk role={data.role} />
      ) : tab === "due" ? (
        <ul className="mt-4 space-y-2">
          {due.length === 0 && <li className="text-sm text-muted">Nothing is due.</li>}
          {due.map((review) => (
            <li key={`${review.quiz_id}-${review.question_id}`} className="panel p-3" data-testid="due-review">
              <p className="text-sm font-medium">{review.prompt}</p>
              <p className="mt-1 text-sm text-muted">
                {review.quiz_title} · due {review.due_on}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <div className="mt-4 space-y-3">
          {lessons.length === 0 && <p className="text-sm text-muted">No lessons in this tab.</p>}
          {lessons.map((lesson) => (
            <LessonCard
              key={lesson.id}
              lesson={lesson}
              testId={lesson.status === "draft" ? "draft-lesson" : "my-lesson"}
              onChange={() => void refresh()}
            />
          ))}
        </div>
      )}
    </AgentWorkbench>
  );
}
