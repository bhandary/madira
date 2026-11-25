"use client";

import { useEffect, useState } from "react";
import { ApprovalCard } from "@/components/ApprovalCard";
import {
  ApiError,
  getTastingInvite,
  proposeTastingInvite,
  type InviteDesk,
  type InviteSlot,
} from "@/lib/api";

export function TastingInvitePanel({ sessionId }: { sessionId: string }) {
  const [desk, setDesk] = useState<InviteDesk | null>(null);
  const [slots, setSlots] = useState<InviteSlot[]>([]);
  const [staffIds, setStaffIds] = useState<string[]>([]);
  const [slotIndex, setSlotIndex] = useState(0);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getTastingInvite(sessionId)
      .then((body) => {
        if (cancelled) return;
        setDesk(body);
        const seeded = body.invite?.slots?.length ? body.invite.slots : body.suggestions;
        setSlots(seeded.map((slot) => ({ starts_at: slot.starts_at, ends_at: slot.ends_at, source: slot.source || "service" })));
        setStaffIds((body.invite?.attendees || []).filter((row) => row.kind === "staff" && row.user_id).map((row) => row.user_id as string));
        const chosen = body.invite?.slots?.findIndex((slot) => slot.chosen) ?? 0;
        setSlotIndex(chosen < 0 ? 0 : chosen);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "The invite could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  function updateSlot(index: number, field: "starts_at" | "ends_at", value: string) {
    setSlots((current) => current.map((slot, slotIndex) => (slotIndex === index ? { ...slot, [field]: value, source: "entered" } : slot)));
  }

  async function propose() {
    const filled = slots.filter((slot) => slot.starts_at && slot.ends_at).slice(0, 3);
    setBusy(true);
    setError("");
    try {
      const body = await proposeTastingInvite(sessionId, { slots: filled, staff_user_ids: staffIds });
      setDesk(body);
      setCopied(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The invite could not be proposed.");
    } finally {
      setBusy(false);
    }
  }

  const invite = desk?.invite || null;
  const ready = invite?.status === "ready";
  const proposed = invite?.status === "proposed";
  const filled = slots.filter((slot) => slot.starts_at && slot.ends_at).length;

  return (
    <section className="panel space-y-3 p-3" data-testid="invite-panel">
      <h3 className="text-base font-medium">Tasting invite</h3>
      <p className="text-sm text-muted">Madira prepares the calendar file and the email. You send it.</p>
      {desk?.rep ? (
        <p className="text-sm" data-testid="invite-rep">
          {desk.rep.name || desk.rep.supplier || "Supplier rep"}
          {desk.rep.email ? ` · ${desk.rep.email}` : ""}
        </p>
      ) : null}
      <div className="space-y-2">
        {slots.map((slot, index) => (
          <div key={`${sessionId}-${index}`} className="grid grid-cols-1 gap-2">
            <label className="lbl" htmlFor={`invite-start-${index}`}>
              Start
              <input
                id={`invite-start-${index}`}
                className="field min-h-11 w-full"
                data-testid="invite-slot"
                type="datetime-local"
                value={slot.starts_at}
                onChange={(event) => updateSlot(index, "starts_at", event.target.value)}
              />
            </label>
            <label className="lbl" htmlFor={`invite-end-${index}`}>
              End
              <input
                id={`invite-end-${index}`}
                className="field min-h-11 w-full"
                data-testid="invite-slot-end"
                type="datetime-local"
                value={slot.ends_at}
                onChange={(event) => updateSlot(index, "ends_at", event.target.value)}
              />
            </label>
          </div>
        ))}
      </div>
      <fieldset className="space-y-1">
        <legend className="text-sm font-medium">Staff</legend>
        {(desk?.staff || []).map((person) => (
          <label key={person.id} className="flex min-h-11 items-center gap-2 text-sm">
            <input
              type="checkbox"
              data-testid="invite-staff"
              checked={staffIds.includes(person.id)}
              onChange={(event) => {
                setStaffIds((current) =>
                  event.target.checked ? [...current, person.id] : current.filter((id) => id !== person.id),
                );
              }}
            />
            {person.name} · {person.role}
          </label>
        ))}
      </fieldset>
      <button
        type="button"
        className="btn btn-primary min-h-11 w-full"
        data-testid="invite-propose"
        disabled={!desk || busy || filled < 2 || ready}
        onClick={() => void propose()}
      >
        Propose invite
      </button>
      {invite ? (
        <div className="space-y-2">
          <p className="text-sm uppercase tracking-wide text-muted" data-testid="invite-status">
            {invite.status}
          </p>
          <p className="text-sm" data-testid="invite-agenda">
            {invite.agenda_note}
          </p>
          <ul className="space-y-1 text-sm" data-testid="invite-facts" data-source={invite.agenda_facts.source}>
            {invite.agenda_facts.gaps.map((gap, index) => (
              <li key={`${gap.style}-${index}`} data-testid="invite-gap">
                {gap.category} / {gap.style} / {gap.price_band} / {gap.quantity_hint}
              </li>
            ))}
            {invite.agenda_facts.samples.map((sample) => (
              <li key={sample.sample_id} data-testid="invite-sample">
                {sample.name}
              </li>
            ))}
          </ul>
          {proposed && desk?.can_decide ? (
            <fieldset className="space-y-1">
              <legend className="text-sm font-medium">Time</legend>
              {invite.slots.map((slot, index) => (
                <label key={`${slot.starts_at}-${index}`} className="flex min-h-11 items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name={`invite-time-${invite.id}`}
                    data-testid="invite-slot-choice"
                    data-slot={slot.starts_at}
                    checked={slotIndex === index}
                    onChange={() => setSlotIndex(index)}
                  />
                  {slot.starts_at}
                </label>
              ))}
            </fieldset>
          ) : null}
          {desk?.can_decide && invite.approval ? (
            <ApprovalCard
              invite={{
                id: invite.id,
                session_id: invite.session_id,
                title: invite.title,
                supplier: invite.supplier,
                status: invite.status,
                chosen_starts_at: invite.slots[slotIndex]?.starts_at || invite.chosen_starts_at,
              }}
              approval={invite.approval}
              slotIndex={slotIndex}
              onDecided={() => {
                void getTastingInvite(sessionId).then((body) => {
                  setDesk(body);
                  setCopied(false);
                });
              }}
            />
          ) : null}
          {ready ? (
            <div className="space-y-2">
              <a
                className="btn btn-primary inline-flex min-h-11 items-center"
                data-testid="invite-ics"
                href={`/madira-api/tastings/${sessionId}/invite.ics`}
                download="tasting-invite.ics"
              >
                Download invite .ics
              </a>
              <p className="text-sm font-medium" data-testid="invite-subject">
                {invite.email_subject}
              </p>
              <pre className="whitespace-pre-wrap text-sm" data-testid="invite-body">
                {invite.email_body}
              </pre>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn min-h-11"
                  data-testid="invite-copy"
                  onClick={() => {
                    void navigator.clipboard.writeText(invite.email_body).then(() => setCopied(true));
                  }}
                >
                  {copied ? "Copied" : "Copy draft"}
                </button>
                {invite.email_mailto ? (
                  <a className="btn inline-flex min-h-11 items-center" data-testid="invite-mailto" href={invite.email_mailto}>
                    Open in mail
                  </a>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
      {error ? <p className="text-sm text-alert">{error}</p> : null}
    </section>
  );
}
