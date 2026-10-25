"use client";

import { ChevronDown, FlipHorizontal2, FlipVertical2, PanelLeftClose, Scissors, SquareDashedMousePointer, Wand2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { DEFAULT_SETTINGS, type OutlineSettings } from "@/lib/api/outline";
import { CREDIT_COST } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { Button, Input, Label, PendingTag, Segmented, Select, Slider, Switch } from "../ui/primitives";

/** Settings the backend does not have yet; kept with the version so nothing is lost. */
export interface PendingSettings {
  height_cm: number;
  fill_repeat: boolean;
  flip_h: boolean;
  flip_v: boolean;
  mirror_half: boolean;
}

export const DEFAULT_PENDING: PendingSettings = { height_cm: 0, fill_repeat: false, flip_h: false, flip_v: false, mirror_half: false };

function Section({ title, tag, children }: { title: string; tag?: boolean; children: React.ReactNode }) {
  return (
    <div className="border-b border-line px-4 py-4 last:border-b-0">
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <p className="text-[13px] font-semibold">{title}</p>
        {tag && <PendingTag />}
      </div>
      {children}
    </div>
  );
}

function SliderRow({
  label,
  value,
  onChange,
  min,
  max,
  step,
  format,
  hint,
}: {
  label?: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  hint?: string;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-[13px]">
        <span className="text-muted">{label}</span>
        <span className="font-medium tabular-nums">{format(value)}</span>
      </div>
      <Slider value={value} onChange={onChange} min={min} max={max} step={step} aria-label={label} />
      {hint && <p className="mt-1 text-[11px] text-muted">{hint}</p>}
    </div>
  );
}

const signed = (v: number) => (v > 0 ? `+${v}` : `${v}`);
const level = (v: number) => (v === 0 ? "Off" : v < 0.75 ? "Low" : v < 1.4 ? "Normal" : "Strong");

export function SettingsPanel({
  designId,
  settings,
  onChange,
  pending,
  onPendingChange,
  onApply,
  applying,
  dirty,
  onPaidAction,
  paidBusy,
}: {
  designId: string;
  settings: OutlineSettings;
  onChange: (s: OutlineSettings) => void;
  pending: PendingSettings;
  onPendingChange: (p: PendingSettings) => void;
  onApply: () => void;
  applying: boolean;
  dirty: boolean;
  onPaidAction: (action: "watermark" | "resize_fill") => void;
  paidBusy: string | null;
}) {
  const [thickMode, setThickMode] = useState<"adjust" | "fixed">(settings.uniform_width > 0 ? "fixed" : "adjust");
  const [more, setMore] = useState(false);
  const set = <K extends keyof OutlineSettings>(k: K, v: OutlineSettings[K]) => onChange({ ...settings, [k]: v });
  const setP = <K extends keyof PendingSettings>(k: K, v: PendingSettings[K]) => onPendingChange({ ...pending, [k]: v });

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <Section title="Remove watermark and text" tag>
          <Button
            size="sm"
            className="w-full"
            onClick={() => onPaidAction("watermark")}
            loading={paidBusy === "watermark"}
          >
            <Scissors className="h-4 w-4" /> Remove watermark · {CREDIT_COST.watermark} credit
          </Button>
        </Section>

        <Section title="Resize and fill">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label className="text-xs text-muted">Width (cm)</Label>
              <Input
                type="number"
                min={0}
                max={300}
                step={0.5}
                value={settings.width_cm || ""}
                placeholder="Auto"
                onChange={(e) => set("width_cm", Math.min(300, Math.max(0, Number(e.target.value) || 0)))}
              />
            </div>
            <div>
              <Label className="flex items-center gap-1 text-xs text-muted">Height (cm)</Label>
              <Input
                type="number"
                min={0}
                max={300}
                step={0.5}
                value={pending.height_cm || ""}
                placeholder="Auto"
                onChange={(e) => setP("height_cm", Math.min(300, Math.max(0, Number(e.target.value) || 0)))}
              />
            </div>
          </div>
          <p className="mt-1 text-[11px] text-muted">Width sets the real size of the files. Height keeps the shape for now.</p>
          <label className="mt-3 flex items-center justify-between gap-2 text-[13px]">
            <span>Fill blank space by repeating the motif</span>
            <Switch checked={pending.fill_repeat} onChange={(v) => setP("fill_repeat", v)} aria-label="Fill by repeating" />
          </label>
          <div className="mt-2 flex items-center justify-between gap-2">
            <Button size="sm" variant="ghost" onClick={() => onPaidAction("resize_fill")} loading={paidBusy === "resize_fill"} className="-ml-2">
              <Wand2 className="h-4 w-4" /> Fill with AI · {CREDIT_COST.resize_fill} credits
            </Button>
            <PendingTag />
          </div>
        </Section>

        <Section title="Line thickness">
          <Segmented
            className="mb-3 w-full"
            value={thickMode}
            onChange={(m) => {
              setThickMode(m);
              if (m === "adjust") set("uniform_width", 0);
            }}
            options={[
              { value: "adjust", label: "Thinner / bolder" },
              { value: "fixed", label: "Fixed width" },
            ]}
          />
          {thickMode === "adjust" ? (
            <SliderRow
              label="Thickness"
              value={settings.thickness}
              onChange={(v) => set("thickness", v)}
              min={-2}
              max={3}
              step={0.25}
              format={(v) => (v === 0 ? "As drawn" : `${signed(v)} px`)}
            />
          ) : (
            <SliderRow
              label="Pen width"
              value={settings.uniform_width}
              onChange={(v) => {
                onChange({ ...settings, uniform_width: v, even_width: "uniform" });
              }}
              min={0}
              max={30}
              step={0.5}
              format={(v) => (v === 0 ? "Automatic" : `${v} px`)}
              hint="In pixels of the photo. Every line gets this one width."
            />
          )}
        </Section>

        <Section title="Gap fill">
          <label className="flex items-center justify-between text-[13px]">
            <span>Join small breaks between line ends</span>
            <Switch checked={settings.join_gaps} onChange={(v) => set("join_gaps", v)} aria-label="Gap fill" />
          </label>
        </Section>

        <Section title="Mirror and flip" tag>
          <div className="grid grid-cols-3 gap-1.5">
            <Toggle on={pending.flip_h} onClick={() => setP("flip_h", !pending.flip_h)}>
              <FlipHorizontal2 className="h-4 w-4" /> Flip ↔
            </Toggle>
            <Toggle on={pending.flip_v} onClick={() => setP("flip_v", !pending.flip_v)}>
              <FlipVertical2 className="h-4 w-4" /> Flip ↕
            </Toggle>
            <Toggle on={pending.mirror_half} onClick={() => setP("mirror_half", !pending.mirror_half)}>
              <PanelLeftClose className="h-4 w-4" /> Mirror half
            </Toggle>
          </div>
        </Section>

        <Section title="Smoothness">
          <SliderRow value={settings.smooth} onChange={(v) => set("smooth", v)} min={0} max={2} step={0.1} format={(v) => (v === 0 ? "Follow the pencil" : v < 1.5 ? "Balanced" : "Very smooth")} />
        </Section>

        <Section title="Sharpness">
          <SliderRow
            value={settings.sharpness}
            onChange={(v) => set("sharpness", v)}
            min={0}
            max={2}
            step={0.1}
            format={level}
            hint="Crisper edges. Affects the scanner-look output."
          />
        </Section>

        <div className="border-b border-line">
          <button className="flex w-full items-center justify-between px-4 py-3 text-[13px] font-semibold" onClick={() => setMore((v) => !v)}>
            More settings
            <ChevronDown className={cn("h-4 w-4 transition-transform", more && "rotate-180")} />
          </button>
          {more && (
            <div className="space-y-4 px-4 pb-4">
              <div>
                <Label className="text-xs text-muted">Output</Label>
                <Segmented
                  className="w-full"
                  value={settings.output}
                  onChange={(v) => set("output", v)}
                  options={[
                    { value: "bw", label: "Black & white" },
                    { value: "scan", label: "Scanner look" },
                  ]}
                />
              </div>
              <div>
                <Label className="text-xs text-muted">Line finder</Label>
                <Segmented
                  className="w-full"
                  value={settings.method}
                  onChange={(v) => set("method", v)}
                  options={[
                    { value: "ai", label: "AI model" },
                    { value: "classic", label: "Classic" },
                  ]}
                />
              </div>
              <label className="flex items-center justify-between text-[13px]">
                Keep hatching, dots and fine detail
                <Switch checked={settings.keep_detail} onChange={(v) => set("keep_detail", v)} />
              </label>
              <label className="flex items-center justify-between text-[13px]">
                Remove shading
                <Switch checked={settings.remove_shading} onChange={(v) => set("remove_shading", v)} />
              </label>
              <SliderRow label="Contrast" value={settings.contrast} onChange={(v) => set("contrast", v)} min={-1} max={1} step={0.05} format={(v) => (v === 0 ? "Auto" : signed(Number(v.toFixed(2))))} />
              <div>
                <Label className="text-xs text-muted">Line width</Label>
                <Select value={settings.even_width} onChange={(e) => set("even_width", e.target.value as OutlineSettings["even_width"])}>
                  <option value="uniform">Same width everywhere</option>
                  <option value="full">Per line (each line steady)</option>
                  <option value="light">Light (trim worst spots)</option>
                  <option value="off">Off</option>
                </Select>
              </div>
              {settings.even_width === "uniform" && (
                <SliderRow label="Beautify lines" value={settings.beautify} onChange={(v) => set("beautify", v)} min={0} max={2} step={0.1} format={level} />
              )}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs text-muted">Line colour</Label>
                  <div className="flex h-9 items-center gap-2 rounded-lg border border-line px-2">
                    <input type="color" value={settings.color} onChange={(e) => set("color", e.target.value)} className="h-6 w-8 cursor-pointer border-0 bg-transparent p-0" aria-label="Line colour" />
                    <span className="font-mono text-xs">{settings.color}</span>
                  </div>
                </div>
                <div>
                  <Label className="text-xs text-muted">DPI</Label>
                  <Select value={settings.dpi} onChange={(e) => set("dpi", Number(e.target.value))}>
                    {[150, 200, 300, 600, 1200].map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>
              <button className="text-xs text-muted underline" onClick={() => onChange(DEFAULT_SETTINGS)}>
                Reset to defaults
              </button>
            </div>
          )}
        </div>

        <div className="px-4 py-4">
          <Link
            href={`/workspace/${designId}/areas`}
            className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-accent/50 bg-accent-soft/50 px-3 py-2.5 text-sm font-medium text-accent-ink hover:bg-accent-soft"
          >
            <SquareDashedMousePointer className="h-4 w-4" /> Select areas and prompt
          </Link>
        </div>
      </div>

      <div className="border-t border-line bg-surface p-4">
        <Button variant="primary" className="w-full" onClick={onApply} loading={applying}>
          Apply settings
        </Button>
        <p className="mt-1.5 text-center text-[11px] text-muted">{dirty ? "Free. Makes a new outline version." : "Settings are free to change."}</p>
      </div>
    </div>
  );
}

function Toggle({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      className={cn(
        "flex flex-col items-center gap-1 rounded-lg border px-2 py-2 text-[11px] font-medium",
        on ? "border-accent bg-accent-soft text-accent-ink" : "border-line text-muted hover:bg-canvas",
      )}
    >
      {children}
    </button>
  );
}
