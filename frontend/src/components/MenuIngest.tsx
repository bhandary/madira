"use client";

import { useEffect, useState } from "react";
import { DishReview } from "@/components/DishReview";
import { ApiError, getMenus, ingestMenu, type MenuReview } from "@/lib/api";

export function MenuIngest() {
  const [camera, setCamera] = useState<File | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [menuId, setMenuId] = useState("");
  const [menus, setMenus] = useState<{ id: string; name: string }[]>([]);
  const [review, setReview] = useState<MenuReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getMenus()
      .then((payload) => setMenus(payload.menus.map((menu) => ({ id: menu.id, name: menu.name }))))
      .catch(() => undefined);
  }, []);

  async function readMenu() {
    if (busy) return;
    const chosen = camera ?? file;
    if (!chosen && !url.trim() && !text.trim()) {
      setError("Add a photo, PDF, link, or menu text.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await ingestMenu({
        file: chosen,
        url: chosen ? "" : url.trim(),
        text: chosen || url.trim() ? "" : text,
        menuId,
      });
      setReview(result.review);
    } catch (err) {
      const detail = err instanceof ApiError ? err.message : "The menu could not be read.";
      setError(detail || "The menu could not be read.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel mt-5 min-w-0 p-4" data-testid="menu-ingest">
      <h2 className="text-lg text-ink">Read a menu</h2>
      <p className="mt-1 text-sm text-muted">
        Take a photo, upload a PDF or text, paste a link, or paste the menu. Review the dishes, then confirm.
      </p>
      <div className="mt-3 grid gap-3">
        <label className="lbl" htmlFor="menu-camera">
          Take a photo
          <input
            id="menu-camera"
            data-testid="menu-camera"
            type="file"
            accept="image/*;capture"
            capture="environment"
            className="field-file"
            onChange={(event) => {
              setCamera(event.target.files?.[0] ?? null);
              setError("");
            }}
          />
        </label>
        <label className="lbl" htmlFor="menu-ingest-file">
          PDF, photo, or text file
          <input
            id="menu-ingest-file"
            data-testid="menu-ingest-file"
            type="file"
            accept="image/png,image/jpeg,image/webp,.pdf,.txt,text/plain"
            className="field-file"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setError("");
            }}
          />
        </label>
        <label className="lbl" htmlFor="menu-ingest-url">
          Menu link
          <input
            id="menu-ingest-url"
            data-testid="menu-ingest-url"
            className="field"
            inputMode="url"
            placeholder="https://"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
        </label>
        <label className="lbl" htmlFor="menu-ingest-text">
          Pasted menu
          <textarea
            id="menu-ingest-text"
            data-testid="menu-ingest-text"
            className="field-area"
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
        </label>
        {menus.length > 0 && (
          <label className="lbl" htmlFor="menu-ingest-target">
            Add to
            <select
              id="menu-ingest-target"
              data-testid="menu-ingest-target"
              className="field"
              value={menuId}
              onChange={(event) => setMenuId(event.target.value)}
            >
              <option value="">New menu</option>
              {menus.map((menu) => (
                <option key={menu.id} value={menu.id}>
                  {menu.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {error && (
        <p className="banner-error mt-3" role="alert" data-testid="menu-ingest-error">
          {error}
        </p>
      )}
      <button type="button" className="btn btn-primary mt-3 w-full" data-testid="menu-ingest-submit" disabled={busy} onClick={() => void readMenu()}>
        {busy ? "Reading…" : "Read menu"}
      </button>
      {review && <DishReview key={review.version_id} review={review} onChange={setReview} />}
    </section>
  );
}
