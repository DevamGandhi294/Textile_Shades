"use client";

import { useState } from "react";

/** Before / after slider: drag to compare two images of the same design. */
export function ImageCompare({
  before,
  after,
  beforeLabel = "Before",
  afterLabel = "After",
  className = "",
}: {
  before: string;
  after: string;
  beforeLabel?: string;
  afterLabel?: string;
  className?: string;
}) {
  const [pos, setPos] = useState(50);
  return (
    <div className={`relative overflow-hidden rounded-xl border border-line bg-white ${className}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={after} alt={afterLabel} className="block h-full w-full select-none object-contain" draggable={false} />
      <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={before} alt={beforeLabel} className="h-full w-full select-none object-contain" draggable={false} />
      </div>
      <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-accent" style={{ left: `${pos}%` }}>
        <span className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent px-1.5 py-1 text-[10px] font-semibold text-white shadow">
          ◀▶
        </span>
      </div>
      <span className="absolute left-2 top-2 rounded bg-white/90 px-1.5 py-px text-[11px] font-medium text-muted">{beforeLabel}</span>
      <span className="absolute right-2 top-2 rounded bg-white/90 px-1.5 py-px text-[11px] font-medium text-muted">{afterLabel}</span>
      <input
        type="range"
        min={0}
        max={100}
        value={pos}
        onChange={(e) => setPos(Number(e.target.value))}
        aria-label="Compare before and after"
        className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
      />
    </div>
  );
}
