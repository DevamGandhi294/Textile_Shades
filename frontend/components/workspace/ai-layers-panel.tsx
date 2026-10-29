"use client";

import { Eye, EyeOff, Layers, Sparkles } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { errorText } from "@/lib/api/client";
import type { Reservation } from "@/lib/api/data";
import { outlineApi, type AiLayersState, type Machine } from "@/lib/api/outline";
import { CREDIT_COST } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { Button, Label, Segmented } from "../ui/primitives";

const MACHINES: { value: Machine; label: string; hint: string }[] = [
  { value: "embroidery", label: "Embroidery", hint: "Layers by thread colour and stitch type" },
  { value: "print", label: "Print", hint: "Layers by colour, one ink each" },
  { value: "cad", label: "CAD", hint: "One layer for each motif" },
];

/**
 * AI layers: the AI checks the design (cheap), then traces the whole design as outlines in ONE paid picture,
 * which the server cuts into one layer per part by the photo's colours (so the layers always line up), each in
 * its own colour and with no fill. The background colour is one more layer. The cost is shown before anything is made.
 */
export function AiLayersPanel({
  withSession,
  sid,
  disabled,
  reserve,
  onPreview,
  onMade,
}: {
  withSession: <T>(fn: (sid: string) => Promise<T>) => Promise<T>;
  sid: string | null;
  disabled: boolean;
  reserve: (count: number) => Promise<Reservation>;
  onPreview: (img: string | null) => void;
  /** The layers were made (all, or some of them): save them as a version of the design. */
  onMade?: (s: AiLayersState, credits: number) => void | Promise<void>;
}) {
  const [machine, setMachine] = useState<Machine>("embroidery");
  const [state, setState] = useState<AiLayersState | null>(null);
  const [hidden, setHidden] = useState<number[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const plan = state?.plan ?? null;
  const n = plan?.layers.length ?? 0;
  const left = state ? state.runs.limit - state.runs.used : 0;

  function show(s: AiLayersState) {
    setState(s);
    onPreview(s.made ? (s.image ?? null) : null);
  }

  async function analyse() {
    setBusy("analyse");
    try {
      show(await withSession((id) => outlineApi.aiAnalyse(id, machine)));
      setHidden([]);
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  async function make() {
    setBusy("make");
    let reservation: Reservation;
    try {
      reservation = await reserve(1); // one AI picture for all the layers; 402 when there are not enough credits
    } catch (e) {
      toast.error(errorText(e));
      setBusy(null);
      return;
    }
    try {
      const s = await withSession((id) => outlineApi.aiMake(id));
      show(s);
      setHidden([]);
      await reservation.settle(true);
      await onMade?.(s, reservation.cost);
      toast.success(`${n} AI layers are ready.`);
    } catch (e) {
      toast.error(errorText(e));
      // some layers may have been made: show them; credits are only kept when something was made
      try {
        const s = await withSession((id) => outlineApi.aiLayers(id));
        show(s);
        await reservation.settle(s.made);
        if (s.made) await onMade?.(s, reservation.cost);
      } catch {
        await reservation.settle(false);
      }
    } finally {
      setBusy(null);
    }
  }

  async function toggle(id: number) {
    const next = hidden.includes(id) ? hidden.filter((x) => x !== id) : [...hidden, id];
    setHidden(next);
    try {
      show(await withSession((sid) => outlineApi.aiLayers(sid, next)));
    } catch (e) {
      toast.error(errorText(e));
    }
  }

  async function download() {
    if (!sid) return;
    setBusy("psd");
    try {
      await outlineApi.download(sid, "ai-layers-psd");
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        <p className="text-sm text-muted">
          The AI traces your design as clean, closed outlines with no fill, and it is cut into one layer per part by the
          colours of your photo, so every outline sits in the right layer and all layers line up. The background colour is
          one separate layer.
        </p>

        <div>
          <Label className="text-xs text-muted">Made for</Label>
          <Segmented className="w-full" value={machine} onChange={setMachine} options={MACHINES.map(({ value, label }) => ({ value, label }))} />
          <p className="mt-1 text-[11px] text-muted">{MACHINES.find((m) => m.value === machine)?.hint}</p>
        </div>

        <Button
          variant={plan ? "secondary" : "primary"}
          className="w-full"
          onClick={analyse}
          loading={busy === "analyse"}
          disabled={disabled || !!busy}
        >
          <Sparkles className="h-4 w-4" /> {plan ? "Check again" : "Check my design"}
        </Button>
        <p className="-mt-2 text-center text-[11px] text-muted">A quick check. Nothing is drawn and no credits are used.</p>

        {plan && (
          <div className="space-y-3 rounded-lg bg-canvas p-3 text-[13px]">
            <ul className="space-y-1">
              <li>
                <b>Design:</b> {plan.image_type === "color" ? "with colour" : "line only"}
              </li>
              <li>
                <b>Finished:</b> {plan.is_complete ? "yes" : "no, rough or unfinished"} · <span className="font-mono text-xs">{plan.model}</span>
              </li>
              <li>
                <b>Symmetric:</b> {plan.mirror ? "yes, the left half is drawn and mirrored" : "no"}
              </li>
              <li className="flex items-center gap-1.5">
                <b>Background:</b> <Swatch hex={plan.background_color} /> one solid layer, free
              </li>
            </ul>
            <ol className="list-decimal space-y-1 pl-5">
              {plan.layers.map((l) => (
                <li key={l.name}>
                  <Swatch hex={l.border_color} /> <b>{l.name}</b>: <span className="text-muted">{l.description}</span>
                </li>
              ))}
            </ol>
            <p>
              Makes <b>one AI picture</b> with thin, even outlines, cut into one layer per colour of your photo (every
              colour, also small ones like white beads): <b>{CREDIT_COST.final} credits</b>.{" "}
              {left > 0 ? `You can do this ${left} more time${left === 1 ? "" : "s"} for this photo.` : "No more runs for this photo."}
            </p>
            <Button variant="primary" className="w-full" onClick={make} loading={busy === "make"} disabled={disabled || !!busy || left <= 0}>
              <Layers className="h-4 w-4" /> {busy === "make" ? "Making the layers… (about a minute)" : `Make ${n} layer${n === 1 ? "" : "s"}`}
            </Button>
          </div>
        )}

        {state?.made && state.layers && (
          <>
            <p className="text-[13px] font-semibold">{state.layers.length} layers</p>
            <ul className="space-y-1.5">
              {state.layers.map((l) => (
                <li key={l.id} className={cn("flex items-center gap-2 rounded-lg border border-line px-2 py-1.5", hidden.includes(l.id) && "opacity-50")}>
                  <span className="flex-1 truncate text-[13px]">{l.name}</span>
                  <button
                    className="rounded p-1 text-muted hover:bg-canvas hover:text-ink"
                    aria-label={hidden.includes(l.id) ? "Show layer" : "Hide layer"}
                    onClick={() => toggle(l.id)}
                    disabled={!!busy}
                  >
                    {hidden.includes(l.id) ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </li>
              ))}
            </ul>
            <Button size="sm" className="w-full" onClick={download} loading={busy === "psd"} disabled={!sid}>
              Photoshop PSD · one layer each
            </Button>
            <p className="text-[11px] text-muted">
              The PSD has a white background, your photo as a hidden layer, the background colour, then one outline layer for
              each part. All layers come from one drawing, so they line up exactly.
            </p>
          </>
        )}
        {!sid && <p className="text-xs text-muted">Upload a raw image first.</p>}
      </div>
    </div>
  );
}

function Swatch({ hex }: { hex: string }) {
  return <span title={hex} className="inline-block h-3 w-3 shrink-0 rounded-sm border border-line align-middle" style={{ background: hex }} />;
}
