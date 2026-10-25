"use client";

import Link from "next/link";
import type { Design } from "@/lib/api/types";
import { shortAgo, sizeLabel } from "@/lib/utils";

export function rawOf(d: Design) {
  return d.versions.find((v) => v.kind === "raw") ?? null;
}

export function currentOf(d: Design) {
  return d.versions.find((v) => v.id === d.current_version_id) ?? d.versions.at(-1) ?? null;
}

/** Raw + outline pair, as on the party page and the Designs page. */
export function DesignCard({ design, partyName }: { design: Design; partyName?: string }) {
  const raw = rawOf(design);
  const cur = currentOf(design);
  const outlineNo = design.versions.filter((v) => v.kind === "outline").length;
  const size = sizeLabel(cur?.width_mm, cur?.height_mm);
  return (
    <Link
      href={`/designs/${design.id}`}
      className="group block rounded-[var(--radius-card)] border border-line bg-surface p-3 transition-shadow hover:shadow-md"
    >
      <div className="grid grid-cols-2 gap-2">
        <Thumb src={raw?.image_url} label="Raw" />
        <Thumb src={cur && cur.kind !== "raw" ? cur.image_url : undefined} label="Outline" />
      </div>
      <p className="mt-3 truncate font-medium group-hover:text-accent-ink">{design.name}</p>
      <p className="mt-0.5 truncate text-xs text-muted">
        {[
          partyName,
          outlineNo ? `v${outlineNo}` : "No outline yet",
          size,
          `${design.chat_count} chat${design.chat_count === 1 ? "" : "s"}`,
          shortAgo(design.updated_at),
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
    </Link>
  );
}

export function Thumb({ src, label, className = "" }: { src?: string | null; label?: string; className?: string }) {
  return (
    <div className={`relative aspect-[4/3] overflow-hidden rounded-lg border border-line bg-canvas ${className}`}>
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={label ?? ""} className="h-full w-full object-contain" loading="lazy" />
      ) : (
        <div className="grid h-full place-items-center text-xs text-muted">{label ? `No ${label.toLowerCase()}` : ""}</div>
      )}
      {label && (
        <span className="absolute left-1.5 top-1.5 rounded bg-white/90 px-1.5 py-px text-[10px] font-medium text-muted">{label}</span>
      )}
    </div>
  );
}
