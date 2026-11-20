"use client";

import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  approveServiceCard,
  approveTastingNote,
  draftTastingNote,
  getServiceCards,
  getTastingNotes,
  updateServiceCard,
  updateTastingNote,
  type ServiceCardRecord,
  type TastingNote,
} from "@/lib/api";

const BODIES = ["light", "medium", "full"];
const ACIDITY = ["low", "medium", "high"];
const TANNIN = ["none", "low", "medium", "high"];
const SWEETNESS = ["bone-dry", "dry", "off-dry", "medium-sweet", "sweet"];
const OAK = ["none", "light", "medium", "heavy"];
const INTENSITY = ["subtle", "medium", "pronounced"];

function message(err: unknown, fallback: string) {
  if (err instanceof ApiError && err.message) return err.message;
  return fallback;
}

function sourceLabel(source: string) {
  return source === "staff" ? "Staff entry" : "Drafted by agent";
}

function statusLabel(status: string) {
  return status === "approved" ? "Approved" : "Draft";
}

export function asNote(value: unknown): TastingNote | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Partial<TastingNote>;
  if (typeof row.id !== "string" || typeof row.product_id !== "string") return null;
  return {
    id: row.id,
    product_id: row.product_id,
    product_name: String(row.product_name ?? ""),
    producer: String(row.producer ?? ""),
    server_hook: String(row.server_hook ?? ""),
    guest_description: String(row.guest_description ?? ""),
    technical_note: String(row.technical_note ?? ""),
    body: String(row.body ?? ""),
    acidity: String(row.acidity ?? ""),
    tannin: String(row.tannin ?? ""),
    sweetness: String(row.sweetness ?? ""),
    oak: String(row.oak ?? ""),
    intensity: String(row.intensity ?? ""),
    aroma_families: Array.isArray(row.aroma_families) ? row.aroma_families.map(String) : [],
    source: String(row.source ?? "agent"),
    status: String(row.status ?? "draft"),
    approved_by: row.approved_by ?? null,
    approved_at: row.approved_at ?? null,
    has_tech_sheet: row.has_tech_sheet === true,
    created_at: String(row.created_at ?? ""),
  };
}

export function asCard(value: unknown): ServiceCardRecord | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Partial<ServiceCardRecord>;
  if (typeof row.id !== "string" || typeof row.product_id !== "string") return null;
  return {
    id: row.id,
    product_id: row.product_id,
    product_name: String(row.product_name ?? ""),
    tasting_note_id: String(row.tasting_note_id ?? ""),
    serving_temperature: String(row.serving_temperature ?? ""),
    glassware: String(row.glassware ?? ""),
    decanting: String(row.decanting ?? ""),
    pour_size: String(row.pour_size ?? ""),
    source: String(row.source ?? "agent"),
    status: String(row.status ?? "draft"),
    approved_by: row.approved_by ?? null,
    approved_at: row.approved_at ?? null,
    created_at: String(row.created_at ?? ""),
  };
}

function Status({ status, testId }: { status: string; testId: string }) {
  const tone = status === "approved" ? "badge badge-ok" : "badge badge-draft";
  return (
    <span className={tone} data-testid={testId}>
      {statusLabel(status)}
    </span>
  );
}

function Choice({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  const choices = options.includes(value) || !value ? options : [value, ...options];
  return (
    <label className="lbl" htmlFor={id}>
      {label}
      <select id={id} className="field" value={value} onChange={(event) => onChange(event.target.value)}>
        {choices.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

export function TastingNoteCard({ note, onChange }: { note: TastingNote; onChange?: (note: TastingNote) => void }) {
  const [current, setCurrent] = useState(note);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(note);
  const [busy, setBusy] = useState<"save" | "approve" | null>(null);
  const [error, setError] = useState("");

  function apply(next: TastingNote) {
    setCurrent(next);
    setDraft(next);
    onChange?.(next);
  }

  async function save() {
    if (busy) return;
    setBusy("save");
    setError("");
    try {
      const saved = await updateTastingNote(current.product_id, current.id, {
        server_hook: draft.server_hook,
        guest_description: draft.guest_description,
        technical_note: draft.technical_note,
        body: draft.body,
        acidity: draft.acidity,
        tannin: draft.tannin,
        sweetness: draft.sweetness,
        oak: draft.oak,
        intensity: draft.intensity,
        aroma_families: draft.aroma_families,
      });
      apply(saved);
      setEditing(false);
    } catch (err) {
      setError(message(err, "The tasting note could not be saved."));
    } finally {
      setBusy(null);
    }
  }

  async function approve() {
    if (busy) return;
    setBusy("approve");
    setError("");
    try {
      apply(await approveTastingNote(current.product_id, current.id));
    } catch (err) {
      setError(message(err, "The tasting note could not be approved."));
    } finally {
      setBusy(null);
    }
  }

  const words = draft.guest_description.trim() ? draft.guest_description.trim().split(/\s+/).length : 0;

  return (
    <article className="panel min-w-0 p-4" data-testid="tasting-note-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base text-ink">{current.product_name}</h3>
        <Status status={current.status} testId="tasting-note-status" />
      </div>
      <p className="mt-1 text-sm text-muted">
        {sourceLabel(current.source)}
        {current.producer ? ` · ${current.producer}` : ""}
      </p>
      {editing ? (
        <div className="mt-3 grid gap-3">
          <label className="lbl" htmlFor={`hook-${current.id}`}>
            Server hook
            <input
              id={`hook-${current.id}`}
              data-testid="tasting-note-hook-input"
              className="field"
              value={draft.server_hook}
              onChange={(event) => setDraft({ ...draft, server_hook: event.target.value })}
            />
          </label>
          <label className="lbl" htmlFor={`guest-${current.id}`}>
            Guest description
            <span className="text-xs text-muted">{words} words · about 30</span>
            <textarea
              id={`guest-${current.id}`}
              className="field-area"
              value={draft.guest_description}
              onChange={(event) => setDraft({ ...draft, guest_description: event.target.value })}
            />
          </label>
          <label className="lbl" htmlFor={`technical-${current.id}`}>
            Technical note
            <textarea
              id={`technical-${current.id}`}
              className="field-area"
              value={draft.technical_note}
              onChange={(event) => setDraft({ ...draft, technical_note: event.target.value })}
            />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <Choice id={`body-${current.id}`} label="Body" value={draft.body} options={BODIES} onChange={(body) => setDraft({ ...draft, body })} />
            <Choice id={`acidity-${current.id}`} label="Acidity" value={draft.acidity} options={ACIDITY} onChange={(acidity) => setDraft({ ...draft, acidity })} />
            <Choice id={`tannin-${current.id}`} label="Tannin" value={draft.tannin} options={TANNIN} onChange={(tannin) => setDraft({ ...draft, tannin })} />
            <Choice id={`sweetness-${current.id}`} label="Sweetness" value={draft.sweetness} options={SWEETNESS} onChange={(sweetness) => setDraft({ ...draft, sweetness })} />
            <Choice id={`oak-${current.id}`} label="Oak" value={draft.oak} options={OAK} onChange={(oak) => setDraft({ ...draft, oak })} />
            <Choice id={`intensity-${current.id}`} label="Intensity" value={draft.intensity} options={INTENSITY} onChange={(intensity) => setDraft({ ...draft, intensity })} />
          </div>
          <label className="lbl" htmlFor={`aroma-${current.id}`}>
            Aroma families
            <input
              id={`aroma-${current.id}`}
              className="field"
              value={draft.aroma_families.join(", ")}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  aroma_families: event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                })
              }
            />
          </label>
        </div>
      ) : (
        <div className="mt-3 grid gap-3">
          <p className="text-sm text-ink" data-testid="tasting-note-hook">
            {current.server_hook}
          </p>
          <p className="text-sm leading-6">{current.guest_description}</p>
          <p className="text-sm leading-6 text-muted">{current.technical_note}</p>
          <div className="flex flex-wrap gap-1.5">
            {[current.body, current.acidity, current.tannin, current.sweetness, current.oak, current.intensity]
              .filter(Boolean)
              .map((item) => (
                <span key={item} className="badge">
                  {item}
                </span>
              ))}
            {current.aroma_families.map((item) => (
              <span key={item} className="badge badge-wine">
                {item}
              </span>
            ))}
          </div>
        </div>
      )}
      {error && (
        <p className="banner-error mt-3" role="alert" data-testid="tasting-note-error">
          {error}
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {editing ? (
          <>
            <button type="button" className="btn btn-primary w-full sm:w-auto" data-testid="tasting-note-save" disabled={busy !== null} onClick={() => void save()}>
              {busy === "save" ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              className="btn btn-secondary w-full sm:w-auto"
              disabled={busy !== null}
              onClick={() => {
                setDraft(current);
                setEditing(false);
                setError("");
              }}
            >
              Cancel
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-secondary w-full sm:w-auto" data-testid="tasting-note-edit" disabled={busy !== null} onClick={() => setEditing(true)}>
            Edit
          </button>
        )}
        {current.status !== "approved" && !editing && (
          <button type="button" className="btn btn-primary w-full sm:w-auto" data-testid="tasting-note-approve" disabled={busy !== null} onClick={() => void approve()}>
            {busy === "approve" ? "Approving…" : "Approve"}
          </button>
        )}
      </div>
    </article>
  );
}

export function ServiceCard({ card, onChange }: { card: ServiceCardRecord; onChange?: (card: ServiceCardRecord) => void }) {
  const [current, setCurrent] = useState(card);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(card);
  const [busy, setBusy] = useState<"save" | "approve" | null>(null);
  const [error, setError] = useState("");

  function apply(next: ServiceCardRecord) {
    setCurrent(next);
    setDraft(next);
    onChange?.(next);
  }

  async function save() {
    if (busy) return;
    setBusy("save");
    setError("");
    try {
      const saved = await updateServiceCard(current.product_id, current.id, {
        serving_temperature: draft.serving_temperature,
        glassware: draft.glassware,
        decanting: draft.decanting,
        pour_size: draft.pour_size,
      });
      apply(saved);
      setEditing(false);
    } catch (err) {
      setError(message(err, "The service card could not be saved."));
    } finally {
      setBusy(null);
    }
  }

  async function approve() {
    if (busy) return;
    setBusy("approve");
    setError("");
    try {
      apply(await approveServiceCard(current.product_id, current.id));
    } catch (err) {
      setError(message(err, "The service card could not be approved."));
    } finally {
      setBusy(null);
    }
  }

  const fields: [string, string, string][] = [
    ["Temperature", current.serving_temperature, "service-card-temperature"],
    ["Glassware", current.glassware, "service-card-glassware"],
    ["Decanting", current.decanting, "service-card-decanting"],
    ["Pour", current.pour_size, "service-card-pour"],
  ];

  return (
    <article className="panel min-w-0 p-4" data-testid="service-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base text-ink">Service</h3>
        <Status status={current.status} testId="service-card-status" />
      </div>
      <p className="mt-1 text-sm text-muted">{sourceLabel(current.source)}</p>
      {editing ? (
        <div className="mt-3 grid gap-3">
          <label className="lbl" htmlFor={`temp-${current.id}`}>
            Serving temperature
            <input id={`temp-${current.id}`} className="field" value={draft.serving_temperature} onChange={(event) => setDraft({ ...draft, serving_temperature: event.target.value })} />
          </label>
          <label className="lbl" htmlFor={`glass-${current.id}`}>
            Glassware
            <input id={`glass-${current.id}`} className="field" value={draft.glassware} onChange={(event) => setDraft({ ...draft, glassware: event.target.value })} />
          </label>
          <label className="lbl" htmlFor={`decant-${current.id}`}>
            Decanting
            <input id={`decant-${current.id}`} className="field" value={draft.decanting} onChange={(event) => setDraft({ ...draft, decanting: event.target.value })} />
          </label>
          <label className="lbl" htmlFor={`pour-${current.id}`}>
            Pour size
            <input id={`pour-${current.id}`} className="field" value={draft.pour_size} onChange={(event) => setDraft({ ...draft, pour_size: event.target.value })} />
          </label>
        </div>
      ) : (
        <dl className="mt-3 grid gap-2 sm:grid-cols-2">
          {fields.map(([label, value, testId]) => (
            <div key={label}>
              <dt className="kicker">{label}</dt>
              <dd className="text-sm text-ink" data-testid={testId}>
                {value}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {error && (
        <p className="banner-error mt-3" role="alert">
          {error}
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {editing ? (
          <>
            <button type="button" className="btn btn-primary w-full sm:w-auto" data-testid="service-card-save" disabled={busy !== null} onClick={() => void save()}>
              {busy === "save" ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              className="btn btn-secondary w-full sm:w-auto"
              disabled={busy !== null}
              onClick={() => {
                setDraft(current);
                setEditing(false);
                setError("");
              }}
            >
              Cancel
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-secondary w-full sm:w-auto" data-testid="service-card-edit" disabled={busy !== null} onClick={() => setEditing(true)}>
            Edit
          </button>
        )}
        {current.status !== "approved" && !editing && (
          <button type="button" className="btn btn-primary w-full sm:w-auto" data-testid="service-card-approve" disabled={busy !== null} onClick={() => void approve()}>
            {busy === "approve" ? "Approving…" : "Approve"}
          </button>
        )}
      </div>
    </article>
  );
}

function cardFor(note: TastingNote | null, cards: ServiceCardRecord[]) {
  if (!note) return cards[0] ?? null;
  return cards.find((card) => card.tasting_note_id === note.id) ?? null;
}

export function ProductNotes({ productId, productName }: { productId: string; productName: string }) {
  const [note, setNote] = useState<TastingNote | null>(null);
  const [card, setCard] = useState<ServiceCardRecord | null>(null);
  const [techSheet, setTechSheet] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ticket = useRef(0);

  useEffect(() => {
    const mine = ++ticket.current;
    void (async () => {
      try {
        const [notes, cards] = await Promise.all([getTastingNotes(productId), getServiceCards(productId)]);
        if (mine !== ticket.current) return;
        const latest = notes.notes[0] ?? null;
        setNote(latest);
        setCard(cardFor(latest, cards.service_cards));
      } catch (err) {
        if (mine !== ticket.current) return;
        setError(message(err, "The tasting notes could not be loaded."));
      }
    })();
  }, [productId]);

  async function draft() {
    if (busy) return;
    const mine = ++ticket.current;
    setBusy(true);
    setError("");
    try {
      const result = await draftTastingNote(productId, techSheet, file);
      if (mine !== ticket.current) return;
      setNote(result.note);
      setCard(result.service_card);
    } catch (err) {
      if (mine !== ticket.current) return;
      setError(message(err, "The tasting note could not be drafted."));
    } finally {
      if (mine === ticket.current) setBusy(false);
    }
  }

  return (
    <section className="mt-5 min-w-0" data-testid="tasting-notes">
      <h3 className="text-base text-ink">Tasting notes · {productName}</h3>
      <p className="mt-1 text-sm text-muted">
        Draft a note and a service card from the catalog. A tech sheet is stored as data. Only an approved note is for the floor.
      </p>
      <div className="mt-3 grid gap-3">
        <label className="lbl" htmlFor="tasting-note-tech-sheet">
          Producer tech sheet
          <textarea
            id="tasting-note-tech-sheet"
            data-testid="tasting-note-tech-sheet"
            className="field-area"
            value={techSheet}
            onChange={(event) => setTechSheet(event.target.value)}
          />
        </label>
        <label className="lbl" htmlFor="tasting-note-file">
          Or a text file
          <input
            id="tasting-note-file"
            data-testid="tasting-note-file"
            type="file"
            accept=".txt,.csv,.pdf,text/plain,text/csv,application/pdf"
            className="field-file"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <button type="button" className="btn btn-primary w-full sm:w-auto" data-testid="tasting-note-draft" disabled={busy} onClick={() => void draft()}>
          {busy ? "Drafting…" : "Draft note"}
        </button>
      </div>
      {error && (
        <p className="banner-error mt-3" role="alert" data-testid="tasting-note-error">
          {error}
        </p>
      )}
      {(note || card) && (
        <div className="mt-4 grid gap-3">
          {note && <TastingNoteCard key={note.id} note={note} onChange={setNote} />}
          {card && <ServiceCard key={card.id} card={card} onChange={setCard} />}
        </div>
      )}
    </section>
  );
}
