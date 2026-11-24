"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, getStandards, resetStandard, saveStandard, type ServiceStandard } from "@/lib/api";

export default function StandardsPage() {
  const [canAuthor, setCanAuthor] = useState(false);
  const [rows, setRows] = useState<ServiceStandard[]>([]);
  const [drafts, setDrafts] = useState<Record<string, { title: string; body: string }>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    void getStandards()
      .then((payload) => {
        setCanAuthor(payload.can_author);
        setRows(payload.standards);
        setDrafts(Object.fromEntries(payload.standards.map((row) => [row.slug, { title: row.title, body: row.body }])));
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "Standards could not be loaded.");
      });
  }, []);

  function edit(slug: string, patch: Partial<{ title: string; body: string }>) {
    setDrafts((current) => ({ ...current, [slug]: { ...current[slug], ...patch } }));
  }

  async function save(row: ServiceStandard) {
    const draft = drafts[row.slug];
    if (!draft) return;
    setBusy(row.slug);
    setError("");
    try {
      const saved = await saveStandard({ slug: row.slug, title: draft.title, body: draft.body, topic: row.topic });
      setRows((current) => current.map((item) => (item.slug === saved.slug ? saved : item)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The standard could not be saved.");
    } finally {
      setBusy("");
    }
  }

  async function reset(row: ServiceStandard) {
    setBusy(row.slug);
    setError("");
    try {
      const saved = await resetStandard(row.slug);
      setRows((current) => current.map((item) => (item.slug === saved.slug ? saved : item)));
      setDrafts((current) => ({ ...current, [saved.slug]: { title: saved.title, body: saved.body } }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The standard could not be reset.");
    } finally {
      setBusy("");
    }
  }

  return (
    <section>
      <h1 className="h-page">Service standards</h1>
      <p className="lead">Madira ships these. An edit is the version a lesson quotes.</p>
      <Link href="/training" className="btn btn-secondary mt-4 w-full">
        Back to lessons
      </Link>
      {error && (
        <p className="banner-error mt-3" role="alert">
          {error}
        </p>
      )}
      <div className="mt-4 space-y-4">
        {rows.map((row) => {
          const draft = drafts[row.slug] || { title: row.title, body: row.body };
          return (
            <article key={row.slug} className="panel p-3" data-testid="standard">
              <p className="text-xs uppercase tracking-wide text-muted">
                {row.topic} · version {row.version}
              </p>
              <label className="lbl mt-2" htmlFor={`standard-title-${row.slug}`}>
                Title
                <input
                  id={`standard-title-${row.slug}`}
                  data-testid="standard-title"
                  className="field"
                  value={draft.title}
                  readOnly={!canAuthor}
                  onChange={(event) => edit(row.slug, { title: event.target.value })}
                />
              </label>
              <label className="lbl mt-2" htmlFor={`standard-body-${row.slug}`}>
                Standard
                <textarea
                  id={`standard-body-${row.slug}`}
                  data-testid="standard-body"
                  className="field-area"
                  value={draft.body}
                  readOnly={!canAuthor}
                  onChange={(event) => edit(row.slug, { body: event.target.value })}
                />
              </label>
              {canAuthor && (
              <div className="mt-3 flex flex-col gap-2">
                <button type="button" data-testid="standard-save" className="btn btn-primary w-full" disabled={busy === row.slug} onClick={() => void save(row)}>
                  Save standard
                </button>
                <button type="button" data-testid="standard-reset" className="btn btn-secondary w-full" disabled={busy === row.slug} onClick={() => void reset(row)}>
                  Reset to default
                </button>
              </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
