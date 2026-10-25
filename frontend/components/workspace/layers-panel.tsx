"use client";

import { Eye, EyeOff, Layers, Merge, Undo2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { errorText } from "@/lib/api/client";
import { outlineApi, type LayerColour, type LayersInput, type LayersResult } from "@/lib/api/outline";
import { cn } from "@/lib/utils";
import { Button, Input, Label, PendingTag, Segmented, Select, Switch } from "../ui/primitives";

/**
 * Colour layers: split a coloured design into one layer per colour (free, offline, backend k-means).
 * The layers are made from the black & white lines, so they need a live image session.
 */
export function LayersPanel({
  withSession,
  sid,
  onPreview,
  lineColor,
  onLineColor,
}: {
  withSession: <T>(fn: (sid: string) => Promise<T>) => Promise<T>;
  sid: string | null;
  onPreview: (img: string | null) => void;
  lineColor: string;
  onLineColor: (hex: string) => void;
}) {
  const [colors, setColors] = useState(0);
  const [merge, setMerge] = useState<[number, number][]>([]);
  const [hidden, setHidden] = useState<number[]>([]);
  const [showLines, setShowLines] = useState(true);
  const [palette, setPalette] = useState<LayerColour[] | null>(null);
  const [names, setNames] = useState<Record<number, string>>({});
  const [outlineMode, setOutlineMode] = useState<"black" | "own">("black");
  const [busy, setBusy] = useState<string | null>(null);

  async function run(next: Partial<LayersInput> = {}) {
    const body: LayersInput = { colors, merge, hidden, show_lines: showLines, ...next };
    setBusy("layers");
    try {
      const r: LayersResult = await withSession((id) => outlineApi.layers(id, body));
      setPalette(r.palette);
      onPreview(r.image);
      if (!r.palette.length) toast.info("No colours were found in this photo. Pencil sketches have no colour layers.");
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  async function download(fmt: "layers-psd" | "layers-svg" | "layers-zip") {
    if (!sid) return;
    setBusy(fmt);
    try {
      await outlineApi.download(sid, fmt);
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  const toggleHidden = (id: number) => {
    const h = hidden.includes(id) ? hidden.filter((x) => x !== id) : [...hidden, id];
    setHidden(h);
    run({ hidden: h });
  };
  const doMerge = (from: number, to: number) => {
    const m: [number, number][] = [...merge, [from, to]];
    setMerge(m);
    run({ merge: m });
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        <p className="text-sm text-muted">
          Split a coloured design into one layer per colour, the way you work in Photoshop or textile CAD. Free, no AI.
        </p>
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Label className="text-xs text-muted">Number of colours</Label>
            <Select value={colors} onChange={(e) => setColors(Number(e.target.value))}>
              <option value={0}>Find automatically</option>
              {Array.from({ length: 11 }, (_, i) => i + 2).map((n) => (
                <option key={n} value={n}>
                  {n} colours
                </option>
              ))}
            </Select>
          </div>
          <Button
            variant="primary"
            loading={busy === "layers"}
            onClick={() => {
              setMerge([]);
              setHidden([]);
              run({ merge: [], hidden: [] });
            }}
          >
            <Layers className="h-4 w-4" /> Find colours
          </Button>
        </div>

        {palette && palette.length > 0 && (
          <>
            <div className="flex items-center justify-between">
              <p className="text-[13px] font-semibold">{palette.length} layers</p>
              {merge.length > 0 && (
                <button
                  className="flex items-center gap-1 text-xs text-muted hover:text-ink"
                  onClick={() => {
                    setMerge([]);
                    run({ merge: [] });
                  }}
                >
                  <Undo2 className="h-3.5 w-3.5" /> Undo merges
                </button>
              )}
            </div>
            <ul className="space-y-2">
              {palette.map((c) => (
                <li key={c.id} className={cn("rounded-lg border border-line p-2", hidden.includes(c.id) && "opacity-50")}>
                  <div className="flex items-center gap-2">
                    <span className="h-7 w-7 shrink-0 rounded-md border border-line" style={{ background: c.hex }} />
                    <Input
                      value={names[c.id] ?? c.name}
                      onChange={(e) => setNames({ ...names, [c.id]: e.target.value })}
                      className="h-8 flex-1"
                      aria-label="Layer name"
                    />
                    <span className="w-10 text-right text-xs tabular-nums text-muted">{Math.round(c.share * 100)}%</span>
                    <button
                      className="rounded p-1 text-muted hover:bg-canvas hover:text-ink"
                      aria-label={hidden.includes(c.id) ? "Show layer" : "Hide layer"}
                      onClick={() => toggleHidden(c.id)}
                    >
                      {hidden.includes(c.id) ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                  {palette.length > 1 && (
                    <div className="mt-1.5 flex items-center gap-2 pl-9 text-xs text-muted">
                      <Merge className="h-3.5 w-3.5" />
                      <select
                        className="rounded border border-line bg-surface px-1 py-0.5"
                        value=""
                        onChange={(e) => e.target.value && doMerge(c.id, Number(e.target.value))}
                        aria-label="Merge into"
                      >
                        <option value="">Merge into…</option>
                        {palette
                          .filter((o) => o.id !== c.id)
                          .map((o) => (
                            <option key={o.id} value={o.id}>
                              {names[o.id] ?? o.name}
                            </option>
                          ))}
                      </select>
                    </div>
                  )}
                </li>
              ))}
            </ul>
            <p className="flex items-center gap-2 text-[11px] text-muted">
              Layer names show here only; the files use the colour names for now. <PendingTag />
            </p>

            <div className="space-y-3 rounded-lg bg-canvas p-3">
              <label className="flex items-center justify-between text-[13px]">
                Show lines on top
                <Switch
                  checked={showLines}
                  onChange={(v) => {
                    setShowLines(v);
                    run({ show_lines: v });
                  }}
                />
              </label>
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <Label className="mb-0 text-xs text-muted">Outline colour</Label>
                  {outlineMode === "own" && <PendingTag />}
                </div>
                <Segmented
                  className="w-full"
                  value={outlineMode}
                  onChange={setOutlineMode}
                  options={[
                    { value: "black", label: "One colour" },
                    { value: "own", label: "Each in its own colour" },
                  ]}
                />
                {outlineMode === "black" && (
                  <div className="mt-2 flex items-center gap-2">
                    <input type="color" value={lineColor} onChange={(e) => onLineColor(e.target.value)} className="h-7 w-9 cursor-pointer" aria-label="Line colour" />
                    <span className="font-mono text-xs">{lineColor}</span>
                    <span className="text-[11px] text-muted">Apply settings to use it</span>
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <p className="text-[13px] font-semibold">Download layers</p>
              <div className="grid gap-1.5">
                <Button size="sm" onClick={() => download("layers-psd")} loading={busy === "layers-psd"} disabled={!sid}>
                  Photoshop PSD · one layer per colour
                </Button>
                <Button size="sm" onClick={() => download("layers-svg")} loading={busy === "layers-svg"} disabled={!sid}>
                  SVG · one group per colour
                </Button>
                <Button size="sm" onClick={() => download("layers-zip")} loading={busy === "layers-zip"} disabled={!sid}>
                  PNG zip · one file per colour
                </Button>
              </div>
            </div>
          </>
        )}
        {!sid && <p className="text-xs text-muted">Upload a raw image first. Layers need the black &amp; white output.</p>}
      </div>
    </div>
  );
}
