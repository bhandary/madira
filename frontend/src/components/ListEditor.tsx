"use client";

import { useEffect, useRef, useState } from "react";
import {
  candidate as candidateSchema,
  listEditorProps,
  type EditorCandidate,
  type EditorItem,
  type EditorSection,
} from "@/a2ui/listEditorSchema";
import {
  ApiError,
  addListItem,
  createListVersion,
  decideListVersion,
  deleteListItem,
  listQrPath,
  listVersions,
  revokePublicList,
  submitListVersion,
  updateListItem,
  type BeverageListDetail,
  type ListDiff,
  type ListVersionRecord,
} from "@/lib/api";

function money(minor: number, currency: string) {
  const code = /^[A-Z]{3}$/.test(currency) ? currency : "USD";
  return (minor / 100).toLocaleString(undefined, { style: "currency", currency: code });
}

function asEditor(props: {
  listId: unknown;
  currency: unknown;
  sections: unknown;
  items: unknown;
  candidates: unknown;
}) {
  const parsed = listEditorProps.safeParse(props);
  if (!parsed.success) return null;
  const value = parsed.data;
  if (typeof value.listId !== "string") return null;
  return {
    listId: value.listId,
    currency: typeof value.currency === "string" ? value.currency : "USD",
    sections: Array.isArray(value.sections) ? value.sections : [],
    items: Array.isArray(value.items) ? value.items : [],
    candidates: Array.isArray(value.candidates) ? value.candidates : [],
  };
}

export function ListEditor(props: {
  listId: unknown;
  currency: unknown;
  sections: unknown;
  items: unknown;
  candidates: unknown;
  onChanged?: (list: BeverageListDetail) => void;
}) {
  const incoming = asEditor(props);
  const signature = JSON.stringify({
    listId: props.listId,
    currency: props.currency,
    sections: props.sections,
    items: props.items,
    candidates: props.candidates,
  });
  const [revision, setRevision] = useState(signature);
  const [listId, setListId] = useState(incoming?.listId || "");
  const [currency, setCurrency] = useState(incoming?.currency || "USD");
  const [sections, setSections] = useState<EditorSection[]>(incoming?.sections || []);
  const [items, setItems] = useState<EditorItem[]>(incoming?.items || []);
  const [candidates, setCandidates] = useState<EditorCandidate[]>(incoming?.candidates || []);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [version, setVersion] = useState<ListVersionRecord | null>(null);
  const [diff, setDiff] = useState<ListDiff | null>(null);
  const [canSubmit, setCanSubmit] = useState(true);
  const versionTicket = useRef(0);

  useEffect(() => {
    if (!listId) return;
    const ticket = versionTicket.current;
    let live = true;
    listVersions(listId)
      .then((body) => {
        if (!live || ticket !== versionTicket.current) return;
        const latest = body.versions[0] || null;
        setVersion(latest);
        setDiff(latest?.diff || null);
        setCanSubmit(body.can_submit);
      })
      .catch((exc) => {
        if (!live) return;
        if (exc instanceof ApiError && exc.status === 403) setCanSubmit(false);
      });
    return () => {
      live = false;
    };
  }, [listId]);

  if (revision !== signature && incoming) {
    setRevision(signature);
    setListId(incoming.listId);
    setCurrency(incoming.currency);
    setSections(incoming.sections);
    setItems(incoming.items);
    setCandidates(incoming.candidates);
  }

  function apply(body: BeverageListDetail) {
    setListId(body.list_id);
    setCurrency(body.currency || "USD");
    setSections(body.sections);
    setItems(body.items);
    setCandidates(
      body.candidates.flatMap((row) => {
        const parsed = candidateSchema.safeParse(row);
        return parsed.success ? [parsed.data] : [];
      }),
    );
    props.onChanged?.(body);
  }

  async function run(key: string, action: () => Promise<BeverageListDetail>) {
    setBusy(key);
    setError("");
    try {
      apply(await action());
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "The list could not be updated.");
    } finally {
      setBusy("");
    }
  }

  async function runVersion(key: string, action: () => Promise<ListVersionRecord>) {
    setBusy(key);
    setError("");
    versionTicket.current += 1;
    try {
      const next = await action();
      setVersion(next);
      setDiff(next.diff);
      setCanSubmit(next.can_submit);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "The list version could not be saved.");
    } finally {
      setBusy("");
    }
  }

  const ordered = [...items].sort((a, b) => a.position - b.position);

  return (
    <div className="min-w-0" data-testid="list-editor">
      {sections.length > 0 && (
        <ul className="mb-3 grid gap-2">
          {sections.map((section) => (
            <li key={section.id} className="panel flex min-h-11 items-center justify-between gap-3 px-3 text-sm" data-testid="list-section">
              <span className="text-ink">{section.name}</span>
              <span className="text-muted">
                {section.item_count} · {section.margin_pct != null ? `${section.margin_pct}% margin` : "margin hidden"}
              </span>
            </li>
          ))}
        </ul>
      )}
      {ordered.length === 0 ? (
        <p className="text-sm text-muted">This list has no bottles yet.</p>
      ) : (
        <ul className="grid gap-2">
          {ordered.map((item, index) => (
            <li key={item.id} className="panel p-3" data-testid="list-item">
              <div className="text-sm text-ink">{item.name}</div>
              <div className="text-xs text-muted">
                {item.section} · {item.style} · {item.band}
                {item.margin_pct != null ? ` · ${item.margin_pct}% margin` : ""}
              </div>
              <div className="mt-1 text-sm text-ink">
                Bottle {item.bottle_price ? money(item.bottle_price, item.currency || currency) : "—"} · Glass{" "}
                {item.pour_price ? money(item.pour_price, item.currency || currency) : "—"}
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn min-h-11"
                  data-testid="list-item-up"
                  disabled={busy !== "" || index === 0}
                  onClick={() => void run(item.id, () => updateListItem(listId, item.id, { position: Math.max(1, item.position - 1) }))}
                >
                  Up
                </button>
                <button
                  type="button"
                  className="btn min-h-11"
                  data-testid="list-item-down"
                  disabled={busy !== "" || index === ordered.length - 1}
                  onClick={() => void run(item.id, () => updateListItem(listId, item.id, { position: item.position + 1 }))}
                >
                  Down
                </button>
                <button
                  type="button"
                  className="btn min-h-11"
                  data-testid="list-item-reprice"
                  disabled={busy !== ""}
                  onClick={() => void run(item.id, () => updateListItem(listId, item.id, { reprice: true }))}
                >
                  Reprice
                </button>
                <button
                  type="button"
                  className="btn min-h-11"
                  data-testid="list-item-remove"
                  disabled={busy !== ""}
                  onClick={() => void run(item.id, () => deleteListItem(listId, item.id))}
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {candidates.length > 0 && (
        <div className="mt-4">
          <div className="kicker">Add from the cellar</div>
          <ul className="mt-2 grid gap-2">
            {candidates.slice(0, 8).map((row) => (
              <li key={row.sku_id} className="flex min-h-11 items-center justify-between gap-3 text-sm">
                <span className="min-w-0 truncate text-ink">{row.name}</span>
                <button
                  type="button"
                  className="btn min-h-11 shrink-0"
                  data-testid="list-add-candidate"
                  disabled={busy !== ""}
                  onClick={() => void run(row.sku_id, () => addListItem(listId, row.sku_id, ""))}
                >
                  Add
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <section className="mt-4" data-testid="list-publish">
        <div className="kicker">Publish</div>
        <div className="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            className="btn min-h-11"
            data-testid="list-diff-load"
            disabled={busy !== ""}
            onClick={() =>
              void runVersion("diff", async () => {
                const next = await createListVersion(listId);
                return next;
              })
            }
          >
            Review changes
          </button>
          {canSubmit ? (
            <button
              type="button"
              className="btn btn-primary min-h-11"
              data-testid="list-submit"
              disabled={busy !== ""}
              onClick={() =>
                void runVersion("submit", async () => {
                  const draft = version?.status === "draft" ? version : await createListVersion(listId);
                  return submitListVersion(draft.id);
                })
              }
            >
              Submit for publish
            </button>
          ) : null}
          {version?.can_decide ? (
            <>
              <button
                type="button"
                className="btn btn-primary min-h-11"
                data-testid="list-approve"
                disabled={busy !== ""}
                onClick={() => {
                  const current = version;
                  if (!current) return;
                  void runVersion("approve", () => decideListVersion(current.id, "approve"));
                }}
              >
                Approve and publish
              </button>
              <button
                type="button"
                className="btn min-h-11"
                data-testid="list-reject"
                disabled={busy !== ""}
                onClick={() => {
                  const current = version;
                  if (!current) return;
                  void runVersion("reject", () => decideListVersion(current.id, "reject"));
                }}
              >
                Reject
              </button>
            </>
          ) : null}
          {version?.public_path ? (
            <button
              type="button"
              className="btn min-h-11"
              data-testid="list-revoke"
              disabled={busy !== ""}
              onClick={() => {
                const current = version;
                if (!current) return;
                void runVersion("revoke", () => revokePublicList(current.id));
              }}
            >
              Revoke QR
            </button>
          ) : null}
        </div>
        {version?.status === "pending_approval" && !version.can_decide ? (
          <p className="mt-2 text-sm text-muted" data-testid="list-pending">
            Waiting for the Owner
          </p>
        ) : null}
        {diff ? (
          <div className="mt-3" data-testid="list-diff">
            <p className="text-sm text-ink" data-testid="list-diff-added">
              Added {diff.added.length}
            </p>
            <p className="text-sm text-ink" data-testid="list-diff-removed">
              Removed {diff.removed.length}
            </p>
            <p className="text-sm text-ink" data-testid="list-diff-repriced">
              Repriced {diff.repriced.length}
            </p>
            <p className="text-sm text-ink" data-testid="list-diff-moved">
              Moved {diff.moved.length}
            </p>
            <ul className="mt-2 grid gap-1">
              {diff.added.map((row) => (
                <li key={`added-${row.sku_id}`} className="text-sm text-muted" data-testid="list-diff-row">
                  {row.name} added
                </li>
              ))}
              {diff.removed.map((row) => (
                <li key={`removed-${row.sku_id}`} className="text-sm text-muted" data-testid="list-diff-row">
                  {row.name} removed
                </li>
              ))}
              {diff.repriced.map((row) => (
                <li key={`price-${row.sku_id}`} className="text-sm text-muted" data-testid="list-diff-row">
                  {row.name} repriced
                </li>
              ))}
              {diff.moved.map((row) => (
                <li key={`moved-${row.sku_id}`} className="text-sm text-muted" data-testid="list-diff-row">
                  {row.name} moved
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {version?.public_path ? (
          <div className="mt-3">
            <a className="text-link inline-flex min-h-11 items-center" data-testid="list-public-url" href={version.public_path}>
              Guest list
            </a>
            <img
              className="mt-2 h-40 w-40"
              data-testid="list-qr"
              alt="QR code for the guest list"
              src={listQrPath(version.id)}
            />
          </div>
        ) : null}
      </section>
      {error && (
        <p className="banner-error mt-3" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
