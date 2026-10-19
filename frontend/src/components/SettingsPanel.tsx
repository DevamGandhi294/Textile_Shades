"use client";

import { Play, RotateCcw } from "lucide-react";
import { Checkbox, Radio, Section, SliderRow } from "./controls";
import type { Settings } from "@/lib/api";
import { ALL_FORMATS, DEFAULTS } from "@/lib/settings";

type Props = {
  settings: Settings;
  edit: (patch: Partial<Settings>) => void; // change only on screen (while dragging or typing)
  apply: (patch?: Partial<Settings>) => void; // change and send to the server
  autoCrop: boolean;
  setAutoCrop: (v: boolean) => void;
  formats: string[];
  setFormats: (f: string[]) => void;
  aiReady: boolean;
  aiStatus: string;
  busy: boolean;
  waitingToStart: boolean;
  onStart: () => void;
  onReset: () => void;
};

/** Every setting of the Python app (backend/app.py), in the same order and groups. */
export default function SettingsPanel(p: Props) {
  const { settings: s, edit, apply, busy } = p;

  // slider + number box + reset for one numeric setting
  const num = (key: "contrast" | "thickness" | "sharpness" | "uniform_width" | "beautify" | "smooth") => ({
    value: s[key],
    reset: DEFAULTS[key],
    onChange: (v: number) => edit({ [key]: v }),
    onCommit: (v?: number) => apply(v === undefined ? {} : { [key]: v }),
    disabled: busy,
  });

  return (
    <div className="flex flex-col">
      {p.waitingToStart && (
        <button
          type="button"
          onClick={p.onStart}
          disabled={busy}
          className="mb-5 inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-btn px-4 text-lg font-semibold text-white shadow-sm hover:bg-btn-hover disabled:opacity-50"
        >
          <Play className="h-5 w-5" aria-hidden /> Start cleaning
        </button>
      )}

      <Section>
        <Radio
          label="Output"
          info="Black & white gives clean lines for colour fill and vector files. Scanner look keeps pencil shading and fine hatching."
          value={s.output}
          onChange={(v) => apply({ output: v })}
          disabled={busy}
          options={[
            { label: "Black & white lines", value: "bw" },
            { label: "Scanner look (grayscale)", value: "scan" },
          ]}
        />
        <Radio
          label="Line finder (B&W)"
          info="AI makes clean, even lines. The first run takes 10–30 seconds; later changes are quicker."
          value={p.aiReady ? s.method : "classic"}
          onChange={(v) => apply({ method: v })}
          disabled={busy || !p.aiReady}
          options={[
            { label: "AI lines", hint: "(recommended)", value: "ai" },
            { label: "Classic", value: "classic" },
          ]}
        />
        {p.aiStatus && <p className="-mt-2 rounded-xl bg-gray-50 px-3 py-2.5 text-sm text-muted">{p.aiStatus}</p>}
        <Checkbox
          label="Keep hatching, dots and fine detail (AI)"
          info="AI removes hatching as tone; this adds fine detail back."
          checked={s.keep_detail}
          onChange={(v) => apply({ keep_detail: v })}
          disabled={busy}
        />
      </Section>

      <Section title="Clean the lines">
        <Checkbox
          label="Remove shading and smudges"
          info="Keep the paper clean while preserving the main lines."
          checked={s.remove_shading}
          onChange={(v) => apply({ remove_shading: v })}
          disabled={busy}
        />
        <SliderRow
          label="Contrast"
          info="+ makes lines darker and paper whiter; − keeps the photo softer."
          min={-1}
          max={1}
          step={0.05}
          {...num("contrast")}
        />
        <SliderRow label="Line thickness" info="+ bolder · − thinner" min={-2} max={3} step={0.25} {...num("thickness")} />
        <SliderRow label="Sharpness (scanner output)" info="Crisper edges in the scanner look." min={0} max={2} step={0.1} {...num("sharpness")} />
      </Section>

      <Section title="Even out the lines (B&W)">
        <Radio
          label="Line width"
          info="Same width everywhere: overdrawn and pressed-hard parts are cut back to one pen width. Light: only trims the worst spots. Per line: each line steady at its own width."
          value={s.even_width}
          onChange={(v) => apply({ even_width: v })}
          disabled={busy}
          options={[
            { label: "Same width everywhere", value: "uniform" },
            { label: "Light", value: "light" },
            { label: "Per line", value: "full" },
            { label: "Off", value: "off" },
          ]}
        />
        <SliderRow
          label="Pen width"
          info="0 = automatic (a normal stroke of this sketch), or set it in pixels of your photo."
          min={0}
          max={6}
          step={0.25}
          {...num("uniform_width")}
        />
        <SliderRow
          label="Beautify lines"
          info="Removes hand shake from curves and makes lines that stop just short touch the next line. 0 off · 1 normal · 2 extra smooth."
          min={0}
          max={2}
          step={0.1}
          {...num("beautify")}
        />
        <SliderRow
          label="Smooth and straighten"
          info="0 follows the pencil · 1 balanced · 2 very smooth, straighter lines."
          min={0}
          max={2}
          step={0.1}
          {...num("smooth")}
        />
        <Checkbox
          label="Join small breaks in lines"
          info="Bridges a gap where two line ends face each other."
          checked={s.join_gaps}
          onChange={(v) => apply({ join_gaps: v })}
          disabled={busy}
        />
      </Section>

      <Section title="Download settings">
        <label className="flex items-center justify-between gap-3">
          <span className="font-semibold">Line colour (B&W)</span>
          <input
            type="color"
            value={s.color}
            disabled={busy}
            onChange={(e) => edit({ color: e.target.value })}
            onBlur={() => apply()}
            className="h-10 w-16 cursor-pointer rounded-lg border border-line bg-white p-1"
          />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="font-semibold">Width in cm</span>
            <input
              type="number"
              min={0}
              step={0.5}
              inputMode="decimal"
              value={s.width_cm}
              disabled={busy}
              onChange={(e) => edit({ width_cm: Math.max(0, Number(e.target.value) || 0) })}
              onBlur={() => apply()}
              onKeyDown={(e) => e.key === "Enter" && apply()}
              className="h-11 rounded-xl border border-line bg-white px-3"
            />
            <span className="text-xs text-muted">0 = automatic</span>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="font-semibold">DPI</span>
            <select
              value={s.dpi}
              disabled={busy}
              onChange={(e) => apply({ dpi: Number(e.target.value) })}
              className="h-11 cursor-pointer rounded-xl border border-line bg-white px-3"
            >
              {[150, 200, 300, 600].map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
        </div>
        <fieldset className="flex flex-col gap-1">
          <legend className="contents">
            <span className="font-semibold">Formats</span>
            <span className="text-sm leading-relaxed text-muted">
              Wilcom E4: EPS or DXF (choose Millimeters) for vectors, BMP/PNG for auto-digitizing. Vectors need the B&W output.
            </span>
          </legend>
          <div className="mt-2 grid grid-cols-4 gap-2">
            {ALL_FORMATS.map((f) => {
              const on = p.formats.includes(f);
              return (
                <label
                  key={f}
                  className={`relative flex cursor-pointer items-center justify-center gap-1.5 rounded-lg border py-2 text-sm font-medium uppercase transition ${
                    on ? "border-brand bg-mint-soft text-btn-hover" : "border-line bg-white text-muted hover:bg-gray-50"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => p.setFormats(on ? p.formats.filter((x) => x !== f) : [...p.formats, f])}
                    className="sr-only"
                  />
                  {f}
                </label>
              );
            })}
          </div>
        </fieldset>
        <Checkbox
          label="Auto-crop the paper in photos"
          info="Turn off if part of the drawing gets cut."
          checked={p.autoCrop}
          onChange={p.setAutoCrop}
          disabled={busy}
        />
      </Section>

      <button
        type="button"
        onClick={p.onReset}
        disabled={busy}
        className="mt-2 inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-line font-semibold text-btn-hover hover:bg-gray-100 disabled:opacity-50"
      >
        <RotateCcw className="h-4 w-4" aria-hidden /> Reset all to recommended
      </button>
    </div>
  );
}
