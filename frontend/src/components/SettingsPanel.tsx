"use client";

import { Play, RotateCcw } from "lucide-react";
import { Accordion, Checkbox, Group, Radio, SliderRow } from "./controls";
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
    <div className="flex flex-col gap-3">
      {p.waitingToStart && (
        <button
          type="button"
          onClick={p.onStart}
          disabled={busy}
          className="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg bg-green-600 px-4 text-lg font-bold text-white hover:bg-green-700 disabled:opacity-50"
        >
          <Play className="h-5 w-5" aria-hidden /> Start cleaning
        </button>
      )}

      <Group>
        <Radio
          label="Output"
          info="B&W: clean lines for colour fill and vector files. Scanner: keeps pencil shading and fine hatching."
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
          info={`AI: clean, even lines without blobs. First run on a new image takes 10-30 s on CPU; after that, settings update quickly. ${p.aiStatus}`}
          value={p.aiReady ? s.method : "classic"}
          onChange={(v) => apply({ method: v })}
          disabled={busy || !p.aiReady}
          options={[
            { label: "AI lines (recommended)", value: "ai" },
            { label: "Classic", value: "classic" },
          ]}
        />
        <Checkbox
          label="Keep hatching, dots and fine detail (AI)"
          info="The AI removes hatching as 'tone'; this adds it back from the classic finder."
          checked={s.keep_detail}
          onChange={(v) => apply({ keep_detail: v })}
          disabled={busy}
        />
      </Group>

      <Accordion title="2 · Clean the lines" open>
        <Checkbox
          label="Remove shading and smudges"
          info="Keeps thin lines, drops soft pencil shading and leftover shadow."
          checked={s.remove_shading}
          onChange={(v) => apply({ remove_shading: v })}
          disabled={busy}
        />
        <SliderRow label="Contrast" info="+ darker lines and whiter paper · − softer" min={-1} max={1} step={0.05} {...num("contrast")} />
        <SliderRow label="Line thickness" info="+ bolder · − thinner" min={-2} max={3} step={0.25} {...num("thickness")} />
        <SliderRow label="Sharpness (scanner output)" info="Crisper edges in the scanner look." min={0} max={2} step={0.1} {...num("sharpness")} />
      </Accordion>

      <Accordion title="3 · Even out the lines (B&W)" open>
        <Radio
          label="Line width"
          info="Same width everywhere: overdrawn, pressed-hard and dark-shaded parts are cut back to one pen width. Light: only trims the worst spots. Per line: each line steady at its own width."
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
          label="Pen width (Same width everywhere)"
          info="0 = automatic (a normal stroke of this sketch). Or set it in pixels of your photo."
          min={0}
          max={6}
          step={0.25}
          {...num("uniform_width")}
        />
        <SliderRow
          label="Beautify lines (Same width everywhere)"
          info="Redraws every line like a professional: removes hand shake from curves and continues lines that stop just short of another line so they touch. 0 off · 1 normal · 2 extra smooth."
          min={0}
          max={2}
          step={0.1}
          {...num("beautify")}
        />
        <SliderRow
          label="Smooth and straighten"
          info="0 follows the pencil · 1 balanced · 2 very smooth, straighter lines"
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
      </Accordion>

      <Accordion title="Download settings">
        <Group>
          <label className="flex flex-col gap-1.5">
            <span className="font-semibold text-white">Line colour (B&W)</span>
            <input
              type="color"
              value={s.color}
              disabled={busy}
              onChange={(e) => edit({ color: e.target.value })}
              onBlur={() => apply()}
              className="h-9 w-14 cursor-pointer rounded border border-white/25 bg-transparent"
            />
          </label>
        </Group>
        <Group>
          <label className="flex flex-col gap-1.5">
            <span className="font-semibold text-white">Width in cm (0 = automatic)</span>
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
              className="h-11 rounded-lg border border-white/25 bg-white/10 px-3 text-white"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="font-semibold text-white">DPI</span>
            <select
              value={s.dpi}
              disabled={busy}
              onChange={(e) => apply({ dpi: Number(e.target.value) })}
              className="h-11 cursor-pointer rounded-lg border border-white/25 bg-white/10 px-3 text-white [&>option]:text-ink"
            >
              {[150, 200, 300, 600].map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <fieldset className="flex flex-col gap-1">
            <legend className="contents">
              <span className="font-semibold text-white">Formats</span>
              <span className="text-sm leading-snug text-white/75">
                Wilcom E4: EPS or DXF (choose Millimeters) for vectors, BMP/PNG for auto-digitizing. Vectors need the B&W output.
              </span>
            </legend>
            <div className="mt-1.5 flex flex-wrap gap-2">
              {ALL_FORMATS.map((f) => {
                const on = p.formats.includes(f);
                return (
                  <label
                    key={f}
                    className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium text-white ${
                      on ? "border-mint bg-white/15" : "border-white/20 hover:bg-white/10"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={() => p.setFormats(on ? p.formats.filter((x) => x !== f) : [...p.formats, f])}
                      className="h-4 w-4 cursor-pointer accent-mint"
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
        </Group>
      </Accordion>

      <button
        type="button"
        onClick={p.onReset}
        disabled={busy}
        className="mt-1 inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-mint px-4 font-semibold text-mint hover:bg-white/10 disabled:opacity-50"
      >
        <RotateCcw className="h-4 w-4" aria-hidden /> Reset all to recommended
      </button>
    </div>
  );
}
