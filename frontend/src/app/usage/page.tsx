"use client";

import { FormEvent, useEffect, useState } from "react";
import { ApiError, getUsage, saveUsageLimits, type UsageReport } from "@/lib/api";

export default function UsagePage() {
  const [report, setReport] = useState<UsageReport | null>(null);
  const [cap, setCap] = useState("");
  const [rpm, setRpm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getUsage()
      .then((next) => {
        if (cancelled) return;
        setReport(next);
        setCap(next.monthly_spend_cap_cents === null ? "" : String(next.monthly_spend_cap_cents));
        setRpm(next.requests_per_minute === null ? "" : String(next.requests_per_minute));
      })
      .catch((exc: unknown) => {
        if (!cancelled) setError(exc instanceof ApiError ? exc.message : "Usage could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function onSave(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const capValue = cap.trim() === "" ? null : Number(cap);
    const rpmValue = rpm.trim() === "" ? null : Number(rpm);
    if ((capValue !== null && !Number.isInteger(capValue)) || (rpmValue !== null && !Number.isInteger(rpmValue))) {
      setError("Use whole numbers, or leave a field empty to turn that limit off.");
      setBusy(false);
      return;
    }
    saveUsageLimits({ monthly_spend_cap_cents: capValue, requests_per_minute: rpmValue })
      .then((next) => {
        setReport(next);
        setCap(next.monthly_spend_cap_cents === null ? "" : String(next.monthly_spend_cap_cents));
        setRpm(next.requests_per_minute === null ? "" : String(next.requests_per_minute));
      })
      .catch((exc: unknown) => {
        setError(exc instanceof ApiError ? exc.message : "The limits could not be saved.");
      })
      .finally(() => setBusy(false));
  }

  return (
    <main className="mx-auto w-full max-w-lg px-4 py-6">
      <h1 className="text-2xl font-semibold">Usage</h1>
      <p className="mt-1 text-sm text-muted">
        Month-to-date for the venue&apos;s own model key. Demo cost is zero. Nothing is billed.
      </p>
      {error ? <p className="mt-3 text-sm text-alert">{error}</p> : null}
      {report ? (
        <>
          <p className="mt-4 text-sm" data-testid="usage-spent">
            {report.month} · spent {report.spent_cents} cents · {report.spent_micro_usd} micro-dollars
            {report.demo ? " · demo" : ""}
          </p>
          <p className="mt-1 break-words text-sm" data-testid="usage-cap-status">
            {report.cap_status}
          </p>
          <div className="table-wrap mt-4">
            <table>
              <thead>
                <tr>
                  <th>Subagent</th>
                  <th>Calls</th>
                  <th>Tokens in</th>
                  <th>Tokens out</th>
                  <th>Micro-dollars</th>
                </tr>
              </thead>
              <tbody>
                {report.by_subagent.length === 0 ? (
                  <tr>
                    <td colSpan={5}>No calls this month.</td>
                  </tr>
                ) : (
                  report.by_subagent.map((row) => (
                    <tr key={row.subagent} data-testid="usage-subagent">
                      <td>{row.subagent}</td>
                      <td>{row.calls}</td>
                      <td>{row.tokens_in}</td>
                      <td>{row.tokens_out}</td>
                      <td>{row.cost_micro_usd}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <ul className="mt-3 space-y-1 text-sm">
            {report.by_day.map((row) => (
              <li key={row.day}>
                {row.day}: {row.calls} calls, {row.cost_micro_usd} micro-dollars
              </li>
            ))}
          </ul>
          {report.can_edit ? (
            <form className="mt-4 space-y-3" onSubmit={onSave}>
              <label className="block text-sm" htmlFor="usage-cap">
                Monthly cap (cents, empty is off)
                <input
                  id="usage-cap"
                  data-testid="usage-cap"
                  className="mt-1 min-h-11 w-full"
                  inputMode="numeric"
                  value={cap}
                  onChange={(event) => setCap(event.target.value)}
                />
              </label>
              <label className="block text-sm" htmlFor="usage-rpm">
                Requests per minute (empty is off)
                <input
                  id="usage-rpm"
                  data-testid="usage-rpm"
                  className="mt-1 min-h-11 w-full"
                  inputMode="numeric"
                  value={rpm}
                  onChange={(event) => setRpm(event.target.value)}
                />
              </label>
              <button type="submit" data-testid="usage-save" className="min-h-11 w-full whitespace-normal" disabled={busy}>
                Save limits
              </button>
            </form>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
