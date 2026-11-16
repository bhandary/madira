"use client";

import Link from "next/link";
import { useRef } from "react";
import { HoverArrow } from "@/components/HoverArrow";

export function BentoLink({ href, title, body }: { href: string; title: string; body: string }) {
  const ref = useRef<HTMLAnchorElement>(null);

  function track(event: React.MouseEvent<HTMLAnchorElement>) {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const box = el.getBoundingClientRect();
    const nx = ((event.clientX - box.left) / box.width) * 2 - 1;
    const ny = (((event.clientY - box.top) / box.height) * 2 - 1) * (box.height / box.width);
    const len = Math.hypot(nx, ny) || 1;
    const dx = nx / len;
    const dy = ny / len;
    const halfW = box.width / 2;
    const halfH = box.height / 2;
    const tx = dx === 0 ? Infinity : halfW / Math.abs(dx);
    const ty = dy === 0 ? Infinity : halfH / Math.abs(dy);
    const hit = Math.min(tx, ty);
    el.style.setProperty("--card-mouse-x", `${dx * hit}px`);
    el.style.setProperty("--card-mouse-y", `${dy * hit}px`);
  }

  return (
    <Link href={href} ref={ref} className="bento" onMouseMove={track}>
      <span className="bento-rim" aria-hidden="true">
        <span className="bento-glow" />
      </span>
      <span className="bento-inner">
        <span className="bento-title">{title}</span>
        <span className="bento-body">{body}</span>
        <span className="bento-go">
          Open
          <HoverArrow />
        </span>
      </span>
    </Link>
  );
}
