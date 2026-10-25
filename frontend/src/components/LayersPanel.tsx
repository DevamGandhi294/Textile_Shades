"use client";

import { Button } from "./controls";
import { DEFAULT_LAYER_OPTIONS, type LayerOptions, type LayersAnswer } from "@/lib/api";

const COLOUR_COUNTS = [2, 3, 4, 5, 6, 7, 8, 10, 12];

type Props = {
  data: LayersAnswer;
  options: LayerOptions;
  busy: boolean; // something else is running: wait
  downloading: string; // file type being prepared
  onChange: (next: LayerOptions) => void;
  onDownload: (fmt: "layers-psd" | "layers-svg" | "layers-zip") => void;
};

/** The colours found in the photo as layers (free): hide one, merge two, choose how many, download. */
export default function LayersPanel({ data, options, busy, downloading, onChange, onDownload }: Props) {
  const changed = JSON.stringify(options) !== JSON.stringify(DEFAULT_LAYER_OPTIONS);
  const share = (v: number) => (v < 0.01 ? "<1%" : `${Math.round(v * 100)}%`);

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-line bg-white p-4">
      <div className="flex flex-col gap-1">
        <h3 className="font-semibold">Colour layers (free)</h3>
        <p className="text-sm text-muted">
          Every colour of your design is one layer, so one change recolours all areas of that colour. Untick a layer to
          check it, or merge two colours that should be one layer.
        </p>
      </div>

      <label className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-semibold">Number of colours</span>
        <select
          value={options.colors}
          disabled={busy}
          onChange={(e) => onChange({ ...options, colors: Number(e.target.value), merge: [], hidden: [] })}
          className="h-10 cursor-pointer rounded-xl border border-line bg-white px-3 text-sm"
        >
          <option value={0}>Find automatically</option>
          {COLOUR_COUNTS.map((n) => (
            <option key={n} value={n}>
              {n} colours
            </option>
          ))}
        </select>
      </label>

      {data.palette.length === 0 ? (
        <p className="rounded-xl bg-sand px-4 py-3 text-sm">
          No colours were found in this photo. Colour layers need a coloured sketch; a pencil or pen drawing has only lines.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {data.palette.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-line px-3 py-2">
              <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-3">
                <input
                  type="checkbox"
                  checked={!options.hidden.includes(p.id)}
                  disabled={busy}
                  onChange={(e) =>
                    onChange({
                      ...options,
                      hidden: e.target.checked ? options.hidden.filter((h) => h !== p.id) : [...options.hidden, p.id],
                    })
                  }
                  className="h-5 w-5 shrink-0 cursor-pointer accent-btn"
                  aria-label={`Show ${p.name}`}
                />
                <span className="h-7 w-7 shrink-0 rounded-md border border-line" style={{ background: p.hex }} aria-hidden />
                <span className="truncate font-medium">{p.name}</span>
                <span className="text-sm text-muted">{share(p.share)}</span>
              </label>
              {data.palette.length > 1 && (
                <select
                  value=""
                  disabled={busy}
                  onChange={(e) =>
                    e.target.value !== "" &&
                    onChange({
                      ...options,
                      merge: [...options.merge, [p.id, Number(e.target.value)]],
                      hidden: options.hidden.filter((h) => h !== p.id),
                    })
                  }
                  aria-label={`Merge ${p.name} into another layer`}
                  className="h-9 cursor-pointer rounded-lg border border-line bg-white px-2 text-sm"
                >
                  <option value="">Merge into…</option>
                  {data.palette
                    .filter((q) => q.id !== p.id)
                    .map((q) => (
                      <option key={q.id} value={q.id}>
                        {q.name}
                      </option>
                    ))}
                </select>
              )}
            </li>
          ))}
          <li className="flex items-center gap-3 rounded-xl border border-line px-3 py-2">
            <label className="flex flex-1 cursor-pointer items-center gap-3">
              <input
                type="checkbox"
                checked={options.show_lines}
                disabled={busy}
                onChange={(e) => onChange({ ...options, show_lines: e.target.checked })}
                className="h-5 w-5 shrink-0 cursor-pointer accent-btn"
                aria-label="Show the lines"
              />
              <span className="h-7 w-7 shrink-0 rounded-md border border-line bg-ink" aria-hidden />
              <span className="font-medium">Lines</span>
            </label>
          </li>
        </ul>
      )}

      <div className="flex flex-wrap gap-3">
        {changed && (
          <Button kind="ghost" onClick={() => onChange(DEFAULT_LAYER_OPTIONS)} disabled={busy}>
            Reset layers
          </Button>
        )}
        <Button onClick={() => onDownload("layers-psd")} disabled={busy || !!downloading || data.palette.length === 0}>
          {downloading === "layers-psd" ? "Preparing…" : "Download layers (PSD)"}
        </Button>
        <Button kind="outline" onClick={() => onDownload("layers-svg")} disabled={busy || !!downloading || data.palette.length === 0}>
          {downloading === "layers-svg" ? "Preparing…" : "Download layered SVG"}
        </Button>
        <Button kind="outline" onClick={() => onDownload("layers-zip")} disabled={busy || !!downloading || data.palette.length === 0}>
          {downloading === "layers-zip" ? "Preparing…" : "Download layers (ZIP of PNG)"}
        </Button>
      </div>
      <p className="text-xs text-muted">
        The PSD is one file for Photoshop: a white background, your original photo as a hidden layer (switch it on with the
        eye icon to compare), a layer per colour and the lines on top. The SVG is the vector version, with each colour as its
        own layer (Illustrator, CorelDRAW, Inkscape). The ZIP has one transparent PNG per colour and one for the lines. Merged
        colours are one layer in every file; hidden layers are still included.
      </p>
    </div>
  );
}
