"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  createCertificate,
  deleteCertificate,
  getTeam,
  getTeamCertificates,
  getTeamProgress,
  inviteTeamMember,
  removeTeamMember,
  revokeTeamInvite,
  updateTeamMember,
  type CertificateRecord,
  type TeamProgress,
  type TeamRoster,
} from "@/lib/api";

const ROLES = ["Owner", "Sommelier", "Manager", "Staff", "Auditor"] as const;
const POSITIONS = ["server", "bartender", "barback", "host"] as const;

function iso(day: Date) {
  const year = day.getFullYear();
  const month = String(day.getMonth() + 1).padStart(2, "0");
  const date = String(day.getDate()).padStart(2, "0");
  return `${year}-${month}-${date}`;
}

export function TeamDesk({ role }: { role: string }) {
  const managerOnly = role === "Manager";
  const [roster, setRoster] = useState<TeamRoster | null>(null);
  const [progress, setProgress] = useState<TeamProgress | null>(null);
  const [certificates, setCertificates] = useState<CertificateRecord[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<(typeof ROLES)[number]>("Staff");
  const [invitePosition, setInvitePosition] = useState<(typeof POSITIONS)[number]>("server");
  const [holder, setHolder] = useState("");
  const [kind, setKind] = useState("responsible_service");
  const [label, setLabel] = useState("Responsible service");
  const [issuedOn, setIssuedOn] = useState(() => iso(new Date(Date.now() - 20 * 24 * 60 * 60 * 1000)));
  const [expiresOn, setExpiresOn] = useState(() => iso(new Date(Date.now() + 10 * 24 * 60 * 60 * 1000)));
  const [file, setFile] = useState<File | null>(null);

  const refresh = useCallback(async () => {
    const [nextRoster, nextProgress, nextCertificates] = await Promise.all([
      getTeam(),
      getTeamProgress(),
      getTeamCertificates(),
    ]);
    setRoster(nextRoster);
    setProgress(nextProgress);
    setCertificates(nextCertificates.certificates);
    setHolder((current) => current || nextRoster.members[0]?.user_id || "");
  }, []);

  useEffect(() => {
    let live = true;
    Promise.all([getTeam(), getTeamProgress(), getTeamCertificates()])
      .then(([nextRoster, nextProgress, nextCertificates]) => {
        if (!live) return;
        setRoster(nextRoster);
        setProgress(nextProgress);
        setCertificates(nextCertificates.certificates);
        setHolder((current) => current || nextRoster.members[0]?.user_id || "");
      })
      .catch((err: unknown) => {
        if (!live) return;
        setError(err instanceof ApiError ? err.message : "The team could not be loaded.");
      });
    return () => {
      live = false;
    };
  }, []);

  async function invite() {
    setBusy(true);
    setError("");
    try {
      await inviteTeamMember({
        email,
        role: managerOnly ? "Staff" : inviteRole,
        position: managerOnly || inviteRole === "Staff" ? invitePosition : null,
      });
      setEmail("");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The invite could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function saveCertificate() {
    if (!holder) return;
    setBusy(true);
    setError("");
    try {
      await createCertificate({ userId: holder, kind, label, issuedOn, expiresOn, file });
      setFile(null);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The certificate could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  const roleChoices = managerOnly ? (["Staff"] as const) : ROLES;

  return (
    <div className="mt-4 space-y-4" data-testid="team-desk">
      {error && (
        <p className="banner-error" role="alert" data-testid="team-error">
          {error}
        </p>
      )}
      <section className="space-y-2">
        <h2 className="text-base font-medium">Roster</h2>
        <ul className="space-y-2">
          {(roster?.members || []).map((member) => (
            <li key={member.user_id} className="panel space-y-2 p-3" data-testid="roster-row">
              <p className="text-sm font-medium">{member.name || member.email}</p>
              <p className="text-sm text-muted">
                {member.email} · {member.role}
                {member.position ? ` · ${member.position}` : ""}
              </p>
              <MemberEditor
                key={`${member.user_id}-${member.role}-${member.position || ""}`}
                member={member}
                roles={roleChoices}
                disabled={busy || (managerOnly && member.role !== "Staff")}
                onSave={async (nextRole, nextPosition) => {
                  setBusy(true);
                  setError("");
                  try {
                    await updateTeamMember(member.user_id, { role: nextRole, position: nextPosition });
                    await refresh();
                  } catch (err) {
                    setError(err instanceof ApiError ? err.message : "The role could not be saved.");
                  } finally {
                    setBusy(false);
                  }
                }}
                onRemove={async () => {
                  setBusy(true);
                  setError("");
                  try {
                    await removeTeamMember(member.user_id);
                    await refresh();
                  } catch (err) {
                    setError(err instanceof ApiError ? err.message : "The membership could not be removed.");
                  } finally {
                    setBusy(false);
                  }
                }}
              />
            </li>
          ))}
        </ul>
      </section>
      <section className="space-y-2">
        <h2 className="text-base font-medium">Invite</h2>
        <label className="lbl" htmlFor="invite-email">
          Email
          <input id="invite-email" className="field" data-testid="invite-email" value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label className="lbl" htmlFor="invite-role">
          Role
          <select
            id="invite-role"
            className="field"
            data-testid="invite-role"
            value={managerOnly ? "Staff" : inviteRole}
            onChange={(event) => setInviteRole(event.target.value as (typeof ROLES)[number])}
          >
            {roleChoices.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="lbl" htmlFor="invite-position">
          Position
          <select
            id="invite-position"
            className="field"
            data-testid="invite-position"
            value={invitePosition}
            disabled={!managerOnly && inviteRole !== "Staff"}
            onChange={(event) => setInvitePosition(event.target.value as (typeof POSITIONS)[number])}
          >
            {POSITIONS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn btn-primary w-full" data-testid="invite-submit" disabled={busy || !email.trim()} onClick={() => void invite()}>
          Invite
        </button>
        <ul className="space-y-2">
          {(roster?.invites || []).map((invite) => (
            <li key={invite.id} className="panel flex flex-col gap-2 p-3" data-testid="invite-row">
              <p className="text-sm">
                {invite.email} · {invite.role}
                {invite.position ? ` · ${invite.position}` : ""}
              </p>
              <button
                type="button"
                className="btn btn-secondary w-full"
                data-testid="invite-revoke"
                disabled={busy}
                onClick={() => {
                  setBusy(true);
                  revokeTeamInvite(invite.id)
                    .then(() => refresh())
                    .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "The invite could not be revoked."))
                    .finally(() => setBusy(false));
                }}
              >
                Revoke
              </button>
            </li>
          ))}
        </ul>
      </section>
      <section className="space-y-2" data-testid="team-progress">
        <h2 className="text-base font-medium">Progress</h2>
        <p className="text-sm text-muted">
          {progress ? `${progress.week.start} – ${progress.week.end}` : "This week"}
        </p>
        <ul className="space-y-2">
          {(progress?.people || []).map((person) => (
            <li key={person.user_id} className="panel p-3 text-sm" data-testid="progress-person">
              <p className="font-medium">{person.name || person.email}</p>
              <p>
                Briefings {person.briefing_ack.label} · Lessons {person.lessons_done} · Quiz {person.quiz_average_label} · Roleplay{" "}
                {person.roleplay_average_label}
              </p>
            </li>
          ))}
        </ul>
        <h3 className="text-sm font-medium">Weak topics</h3>
        {(progress?.weak_topics || []).length === 0 && <p className="text-sm text-muted">No quiz topics yet.</p>}
        <ul className="space-y-2">
          {(progress?.weak_topics || []).map((topic) => (
            <li key={topic.topic} className="text-sm" data-testid="weak-topic">
              {topic.topic} · {topic.label}
            </li>
          ))}
        </ul>
      </section>
      <section className="space-y-2">
        <h2 className="text-base font-medium">Certificates</h2>
        <label className="lbl" htmlFor="certificate-user">
          Person
          <select id="certificate-user" className="field" data-testid="certificate-user" value={holder} onChange={(event) => setHolder(event.target.value)}>
            {(roster?.members || []).map((member) => (
              <option key={member.user_id} value={member.user_id}>
                {member.name || member.email}
              </option>
            ))}
          </select>
        </label>
        <label className="lbl" htmlFor="certificate-kind">
          Kind
          <select id="certificate-kind" className="field" data-testid="certificate-kind" value={kind} onChange={(event) => setKind(event.target.value)}>
            <option value="responsible_service">Responsible service</option>
            <option value="food_handler">Food handler</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label className="lbl" htmlFor="certificate-label">
          Label
          <input id="certificate-label" className="field" data-testid="certificate-label" value={label} onChange={(event) => setLabel(event.target.value)} />
        </label>
        <label className="lbl" htmlFor="certificate-issued">
          Issued
          <input id="certificate-issued" className="field" data-testid="certificate-issued" type="date" value={issuedOn} onChange={(event) => setIssuedOn(event.target.value)} />
        </label>
        <label className="lbl" htmlFor="certificate-expires">
          Expires
          <input id="certificate-expires" className="field" data-testid="certificate-expires" type="date" value={expiresOn} onChange={(event) => setExpiresOn(event.target.value)} />
        </label>
        <label className="btn btn-secondary w-full">
          {file ? file.name : "Attach a file"}
          <input
            type="file"
            className="sr-only"
            data-testid="certificate-file"
            accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.csv"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
          />
        </label>
        <button type="button" className="btn btn-primary w-full" data-testid="certificate-save" disabled={busy || !holder || !label.trim()} onClick={() => void saveCertificate()}>
          Save certificate
        </button>
        <ul className="space-y-2">
          {certificates.map((row) => (
            <li key={row.id} className="panel space-y-2 p-3" data-testid={row.expired || row.expiring ? "certificate-expiring" : "certificate-row"}>
              <p className="text-sm font-medium">
                {row.name} · {row.label}
              </p>
              <p className="text-sm text-muted">{row.status_label}</p>
              {row.document_filename ? <p className="text-sm">{row.document_filename}</p> : null}
              <button
                type="button"
                className="btn btn-secondary w-full"
                data-testid="certificate-remove"
                disabled={busy}
                onClick={() => {
                  setBusy(true);
                  deleteCertificate(row.id)
                    .then(() => refresh())
                    .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "The certificate could not be removed."))
                    .finally(() => setBusy(false));
                }}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function MemberEditor({
  member,
  roles,
  disabled,
  onSave,
  onRemove,
}: {
  member: TeamRoster["members"][number];
  roles: readonly string[];
  disabled: boolean;
  onSave: (role: string, position: string | null) => Promise<void>;
  onRemove: () => Promise<void>;
}) {
  const [nextRole, setNextRole] = useState(member.role);
  const [nextPosition, setNextPosition] = useState(member.position || "server");

  return (
    <div className="space-y-2">
      <label className="lbl" htmlFor={`member-role-${member.user_id}`}>
        Role
        <select
          id={`member-role-${member.user_id}`}
          className="field"
          data-testid="member-role"
          value={roles.includes(nextRole) ? nextRole : roles[0]}
          disabled={disabled}
          onChange={(event) => setNextRole(event.target.value)}
        >
          {roles.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </label>
      <label className="lbl" htmlFor={`member-position-${member.user_id}`}>
        Position
        <select
          id={`member-position-${member.user_id}`}
          className="field"
          data-testid="member-position"
          value={nextPosition}
          disabled={disabled || nextRole !== "Staff"}
          onChange={(event) => setNextPosition(event.target.value)}
        >
          {POSITIONS.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="btn btn-secondary w-full"
        data-testid="member-save"
        disabled={disabled}
        onClick={() => void onSave(nextRole, nextRole === "Staff" ? nextPosition : null)}
      >
        Save role
      </button>
      <button type="button" className="btn btn-secondary w-full" data-testid="member-remove" disabled={disabled} onClick={() => void onRemove()}>
        Remove
      </button>
    </div>
  );
}
