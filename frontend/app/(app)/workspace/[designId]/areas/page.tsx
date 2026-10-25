"use client";

import { Brush, Eraser, Plus, RectangleHorizontal, Trash2, Undo2 } from "lucide-react";
import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { currentOf } from "@/components/design-card";
import { Button, ErrorBox, PendingTag, Skeleton, Slider, Textarea } from "@/components/ui/primitives";
import { CREDIT_COST } from "@/lib/api/types";
import { useDesign, useParty } from "@/lib/queries";
import { cn, uid } from "@/lib/utils";

const PALETTE = [
  { name: "Blue", hex: "#2563EB" },
  { name: "Orange", hex: "#EA580C" },
  { name: "Green", hex: "#16A34A" },
  { name: "Pink", hex: "#DB2777" },
  { name: "Purple", hex: "#7C3AED" },
  { name: "Teal", hex: "#0D9488" },
];
const MAX_SIDE = 1600;

type Tool = "brush" | "box" | "eraser";
interface Area {
  id: string;
  name: string;
  hex: string;
  prompt: string;
  canvas: HTMLCanvasElement; // the painted mask, full image size
}

/** Screen 2: paint areas in colours, one prompt per colour; everything outside stays as it is. */
export default function AreaSelectorPage({ params }: { params: Promise<{ designId: string }> }) {
  const { designId } = use(params);
  const design = useDesign(designId);
  const party = useParty(design.data?.party_id);
  const cur = design.data ? currentOf(design.data) : null;

  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [areas, setAreas] = useState<Area[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [tool, setTool] = useState<Tool>("brush");
  const [brush, setBrush] = useState(28);
  const [busy, setBusy] = useState(false);
  const view = useRef<HTMLCanvasElement>(null);
  const undo = useRef<{ areaId: string; data: ImageData }[]>([]);
  const drag = useRef<{ x: number; y: number; snapshot: ImageData } | null>(null);
  const last = useRef<{ x: number; y: number } | null>(null);

  const newMask = (w: number, h: number) => {
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    return c;
  };

  // image size decides the mask size
  useEffect(() => {
    if (!cur?.image_url) return;
    const img = new Image();
    img.onload = () => {
      const f = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
      const w = Math.round((img.naturalWidth || 1200) * f);
      const h = Math.round((img.naturalHeight || 900) * f);
      setSize({ w, h });
      setAreas((a) =>
        a.length
          ? a
          : PALETTE.slice(0, 2).map((p) => ({ id: uid(), name: `${p.name} area`, hex: p.hex, prompt: "", canvas: newMask(w, h) })),
      );
    };
    img.src = cur.image_url;
  }, [cur?.image_url]);

  useEffect(() => {
    if (!active && areas[0]) setActive(areas[0].id);
  }, [areas, active]);

  const redraw = useCallback(() => {
    const c = view.current;
    if (!c || !size) return;
    const ctx = c.getContext("2d")!;
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.globalAlpha = 0.45;
    for (const a of areas) ctx.drawImage(a.canvas, 0, 0);
    ctx.globalAlpha = 1;
  }, [areas, size]);
  useEffect(redraw, [redraw]);

  const area = areas.find((a) => a.id === active) ?? null;

  function point(e: React.PointerEvent<HTMLCanvasElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: ((e.clientX - r.left) / r.width) * size!.w, y: ((e.clientY - r.top) / r.height) * size!.h };
  }
  const scale = () => (view.current ? size!.w / view.current.getBoundingClientRect().width : 1);

  function stroke(from: { x: number; y: number }, to: { x: number; y: number }) {
    const ctx = area!.canvas.getContext("2d")!;
    ctx.globalCompositeOperation = tool === "eraser" ? "destination-out" : "source-over";
    ctx.strokeStyle = area!.hex;
    ctx.lineWidth = brush * scale();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
    ctx.globalCompositeOperation = "source-over";
  }

  function down(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!area || !size) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const ctx = area.canvas.getContext("2d")!;
    const snap = ctx.getImageData(0, 0, size.w, size.h);
    undo.current.push({ areaId: area.id, data: snap });
    if (undo.current.length > 30) undo.current.shift();
    const p = point(e);
    if (tool === "box") drag.current = { ...p, snapshot: snap };
    else {
      last.current = p;
      stroke(p, p);
      redraw();
    }
  }

  function move(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!area || !size || !(e.buttons & 1)) return;
    const p = point(e);
    if (tool === "box" && drag.current) {
      const ctx = area.canvas.getContext("2d")!;
      ctx.putImageData(drag.current.snapshot, 0, 0);
      ctx.fillStyle = area.hex;
      ctx.fillRect(Math.min(p.x, drag.current.x), Math.min(p.y, drag.current.y), Math.abs(p.x - drag.current.x), Math.abs(p.y - drag.current.y));
    } else if (last.current) {
      stroke(last.current, p);
      last.current = p;
    }
    redraw();
  }

  function up() {
    drag.current = null;
    last.current = null;
    setAreas((a) => [...a]); // refresh "painted" state
  }

  function doUndo() {
    const s = undo.current.pop();
    if (!s) return;
    const a = areas.find((x) => x.id === s.areaId);
    a?.canvas.getContext("2d")!.putImageData(s.data, 0, 0);
    setAreas((x) => [...x]);
  }

  const painted = (a: Area) => {
    if (!size) return false;
    const d = a.canvas.getContext("2d")!.getImageData(0, 0, size.w, size.h).data;
    for (let i = 3; i < d.length; i += 16) if (d[i]! > 0) return true;
    return false;
  };

  function addColour() {
    if (!size) return;
    const used = new Set(areas.map((a) => a.hex));
    const p = PALETTE.find((x) => !used.has(x.hex));
    if (!p) return toast.info(`Up to ${PALETTE.length} colours.`);
    const a = { id: uid(), name: `${p.name} area`, hex: p.hex, prompt: "", canvas: newMask(size.w, size.h) };
    setAreas([...areas, a]);
    setActive(a.id);
  }

  /** One black-and-white mask PNG per colour: what the area-edit endpoint will receive. */
  function masks() {
    return areas.filter(painted).map((a) => {
      const m = newMask(size!.w, size!.h);
      const ctx = m.getContext("2d")!;
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, m.width, m.height);
      ctx.globalCompositeOperation = "destination-out";
      ctx.drawImage(a.canvas, 0, 0); // painted pixels become transparent = "edit here" (OpenAI mask convention)
      return { color: a.hex, prompt: a.prompt.trim(), mask: m.toDataURL("image/png") };
    });
  }

  async function regenerate() {
    const ready = areas.filter(painted);
    if (!ready.length) return toast.error("Paint at least one area first.");
    const missing = ready.find((a) => !a.prompt.trim());
    if (missing) return toast.error(`Write what should change in the ${missing.name.toLowerCase()}.`);
    setBusy(true);
    const m = masks();
    setBusy(false);
    toast.info(
      `${m.length} area mask${m.length === 1 ? "" : "s"} ready, but area editing needs backend work: the endpoint is not built yet. No credits were used.`,
    );
  }

  if (design.isLoading) return <div className="p-6"><Skeleton className="h-[70vh]" /></div>;
  if (design.error) return <div className="p-6"><ErrorBox error={design.error} /></div>;
  const d = design.data!;
  const paintedCount = areas.filter(painted).length;

  return (
    <div className="flex min-h-[calc(100vh-48px)] flex-col lg:h-screen lg:min-h-0">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface px-4 py-3">
        <p className="min-w-0 truncate text-sm">
          <Link href={`/workspace/${d.id}`} className="text-muted hover:text-ink">
            ← Back to workspace
          </Link>
          <span className="mx-2 text-muted">/</span>
          {[party.data?.name, d.name, "Select areas"].filter(Boolean).join(" · ")}
        </p>
        <p className="text-sm text-muted">Paint an area, then write what should change there</p>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <div className="flex shrink-0 gap-1 border-b border-line bg-surface p-2 lg:w-16 lg:flex-col lg:border-b-0 lg:border-r">
          <ToolBtn on={tool === "brush"} onClick={() => setTool("brush")} label="Brush">
            <Brush className="h-5 w-5" />
          </ToolBtn>
          <ToolBtn on={tool === "box"} onClick={() => setTool("box")} label="Box">
            <RectangleHorizontal className="h-5 w-5" />
          </ToolBtn>
          <ToolBtn on={tool === "eraser"} onClick={() => setTool("eraser")} label="Eraser">
            <Eraser className="h-5 w-5" />
          </ToolBtn>
          <ToolBtn on={false} onClick={doUndo} label="Undo">
            <Undo2 className="h-5 w-5" />
          </ToolBtn>
        </div>

        <section className="flex min-w-0 flex-1 flex-col p-4">
          {!cur ? (
            <p className="text-sm text-muted">Make an outline in the workspace first.</p>
          ) : (
            <>
              <div className="mb-3 flex items-center gap-3 text-sm">
                <span className="text-muted">Brush size</span>
                <Slider value={brush} onChange={setBrush} min={4} max={120} step={2} className="w-48" aria-label="Brush size" />
                <span className="tabular-nums text-muted">{brush}px</span>
                {area && (
                  <span className="ml-auto flex items-center gap-1.5">
                    <span className="h-3 w-3 rounded-full" style={{ background: area.hex }} />
                    Painting {area.name.toLowerCase()}
                  </span>
                )}
              </div>
              <div className="grid flex-1 place-items-center overflow-auto rounded-xl border border-line bg-white p-2">
                {size && (
                  <div className="relative w-full" style={{ maxWidth: `min(100%, calc((100vh - 220px) * ${size.w / size.h}))` }}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={cur.image_url} alt={cur.label} className="block w-full select-none" draggable={false} />
                    <canvas
                      ref={view}
                      width={size.w}
                      height={size.h}
                      className={cn("absolute inset-0 h-full w-full touch-none", tool === "eraser" ? "cursor-cell" : "cursor-crosshair")}
                      onPointerDown={down}
                      onPointerMove={move}
                      onPointerUp={up}
                      onPointerCancel={up}
                    />
                  </div>
                )}
              </div>
            </>
          )}
        </section>

        <aside className="flex w-full shrink-0 flex-col border-t border-line bg-surface lg:w-96 lg:border-l lg:border-t-0">
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            <div>
              <h2 className="font-semibold">Selected areas</h2>
              <p className="text-sm text-muted">Each colour is one area with its own prompt. Everything outside the areas stays exactly as it is.</p>
            </div>
            {areas.map((a) => (
              <div
                key={a.id}
                onClick={() => setActive(a.id)}
                className={cn("cursor-pointer rounded-xl border-2 p-3", a.id === active ? "border-accent" : "border-line")}
              >
                <div className="mb-2 flex items-center justify-between">
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <span className="h-4 w-4 rounded-full" style={{ background: a.hex }} />
                    {a.name}
                  </span>
                  <button
                    className="flex items-center gap-1 text-xs text-muted hover:text-danger"
                    onClick={(e) => {
                      e.stopPropagation();
                      setAreas(areas.filter((x) => x.id !== a.id));
                      if (active === a.id) setActive(null);
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" /> Remove
                  </button>
                </div>
                <Textarea
                  rows={2}
                  value={a.prompt}
                  onChange={(e) => setAreas(areas.map((x) => (x.id === a.id ? { ...x, prompt: e.target.value.slice(0, 300) } : x)))}
                  placeholder="Prompt for this area, e.g. “make this feather a closed paisley”"
                  aria-label={`Prompt for ${a.name}`}
                />
              </div>
            ))}
            <Button variant="ghost" className="w-full" onClick={addColour}>
              <Plus className="h-4 w-4" /> Add another colour
            </Button>
          </div>
          <div className="border-t border-line p-4">
            <div className="mb-3 flex items-center justify-between text-sm">
              <span>
                {paintedCount} area{paintedCount === 1 ? "" : "s"}
              </span>
              <span className="text-muted">About {paintedCount * CREDIT_COST.area_edit} credits</span>
            </div>
            <Button variant="primary" className="w-full" onClick={regenerate} loading={busy}>
              Regenerate selected areas
            </Button>
            <div className="mt-2 flex justify-center">
              <PendingTag />
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function ToolBtn({ on, onClick, label, children }: { on: boolean; onClick: () => void; label: string; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      aria-pressed={on}
      className={cn(
        "flex flex-col items-center gap-0.5 rounded-lg px-2 py-2 text-[10px] font-medium text-muted hover:bg-canvas",
        on && "bg-accent-soft text-accent-ink hover:bg-accent-soft",
      )}
    >
      {children}
      {label}
    </button>
  );
}
