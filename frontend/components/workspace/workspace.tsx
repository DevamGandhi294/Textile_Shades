"use client";

import { AlertTriangle, Check, ImagePlus, Loader2, Pencil } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { errorText } from "@/lib/api/client";
import { billingApi, chatsApi, designsApi, type NewVersion } from "@/lib/api/data";
import { DEFAULT_SETTINGS, outlineApi, type OutlineSettings } from "@/lib/api/outline";
import { CREDIT_COST, type Design, type DesignVersion } from "@/lib/api/types";
import { storableCopy } from "@/lib/image";
import { takePendingUpload } from "@/lib/pending-upload";
import { useDesign, useDesignChats, useHealth, useParty, useRefreshAll } from "@/lib/queries";
import { cn, shortDate, sizeLabel } from "@/lib/utils";
import { DownloadMenu } from "../download-menu";
import { ImageCompare } from "../image-compare";
import { Button, ErrorBox, Input, Select, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/primitives";
import { AiLayersPanel } from "./ai-layers-panel";
import { ChatPanel } from "./chat-panel";
import { LayersPanel } from "./layers-panel";
import { DEFAULT_PENDING, SettingsPanel, type PendingSettings } from "./settings-panel";
import { useOutlineSession } from "./use-outline-session";

const IMAGE_TYPES = ".png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff";
// what is shown next to the raw photo (Before / After is the only full-width view)
type View = "scan" | "compare" | "result" | "check" | "layers" | "ailayers";

function baseVersion(kind: DesignVersion["kind"]): NewVersion {
  return {
    parent_id: null,
    kind,
    label: "",
    note: null,
    image_url: "",
    width_px: null,
    height_px: null,
    dpi: null,
    width_mm: null,
    height_mm: null,
    settings: null,
    closed_boxes: null,
    gaps_joined: null,
    credits: 0,
    chat_message_id: null,
  };
}

function settingsOf(d: Design | undefined): { s: OutlineSettings; p: PendingSettings } {
  const v = [...(d?.versions ?? [])].reverse().find((x) => x.settings);
  const saved = (v?.settings ?? {}) as Partial<OutlineSettings> & { pending?: PendingSettings };
  const { pending, ...rest } = saved;
  return { s: { ...DEFAULT_SETTINGS, ...rest }, p: { ...DEFAULT_PENDING, ...pending } };
}

/** Screen 1: chat on the left, raw and outline in the middle, settings on the right. */
export function Workspace({ designId }: { designId: string }) {
  const params = useSearchParams();
  const design = useDesign(designId);
  const party = useParty(design.data?.party_id);
  const chats = useDesignChats(designId);
  const health = useHealth();
  const refresh = useRefreshAll();

  const initial = useMemo(() => settingsOf(design.data), [design.data?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const [settings, setSettings] = useState<OutlineSettings>(initial.s);
  const [pending, setPending] = useState<PendingSettings>(initial.p);
  const [applied, setApplied] = useState(JSON.stringify(initial.s));
  useEffect(() => {
    setSettings(initial.s);
    setPending(initial.p);
    setApplied(JSON.stringify(initial.s));
  }, [initial]);

  const session = useOutlineSession(design.data, settings);
  const [busy, setBusy] = useState<string | null>(null);
  const [view, setView] = useState<View>("result");
  const [shownId, setShownId] = useState<string | null>(null);
  const [layerImg, setLayerImg] = useState<string | null>(null);
  const [aiImg, setAiImg] = useState<string | null>(null); // AI layers preview
  const [chatId, setChatId] = useState<string | null>(params.get("chat"));
  const [panel, setPanel] = useState<"settings" | "layers" | "ailayers">("settings");
  const [mobilePane, setMobilePane] = useState<"chat" | "image" | "settings">("image");
  const fileRef = useRef<HTMLInputElement>(null);

  // pick the latest chat once they load (unless one was asked for)
  useEffect(() => {
    if (!chatId && chats.data?.length && !params.get("new")) setChatId(chats.data.at(-1)!.id);
  }, [chats.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const d = design.data;
  const versions = d?.versions ?? [];
  const raw = [...versions].reverse().find((v) => v.kind === "raw") ?? null;
  const chainStart = raw ? versions.indexOf(raw) : 0;
  const chain = versions.slice(chainStart); // the current raw image and what came from it
  const scan = chain.find((v) => v.kind === "scan") ?? null;
  const results = chain.filter((v) => v.kind === "ai" || v.kind === "outline");
  // only results made from the current raw image: an older (or demo) version must not sit next to a new photo
  const current = results.find((v) => v.id === d?.current_version_id) ?? null;
  const shown = results.find((v) => v.id === shownId) ?? current ?? results.at(-1) ?? null;

  const nextLabel = (kind: "outline" | "ai") => {
    const n = versions.filter((v) => v.kind === kind).length + 1;
    return kind === "outline" ? `Outline v${n}` : n === 1 ? "AI result" : `AI result ${n}`;
  };

  const addResultVersion = useCallback(
    async (v: Partial<NewVersion> & { kind: "outline" | "ai"; image_url: string }) => {
      const parent = versions.find((x) => x.id === d?.current_version_id) ?? versions.at(-1);
      return designsApi.addVersion(designId, { ...baseVersion(v.kind), label: nextLabel(v.kind), parent_id: parent?.id ?? null, ...v });
    },
    [versions, d?.current_version_id, designId], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const sizeMm = (wPx: number, hPx: number, s: OutlineSettings) => {
    if (s.width_cm > 0) return { width_mm: s.width_cm * 10, height_mm: Math.round((s.width_cm * 10 * hPx) / wPx) };
    return { width_mm: Math.round((wPx / s.dpi) * 25.4), height_mm: Math.round((hPx / s.dpi) * 25.4) };
  };

  // ------------------------------------------------------------------ upload

  const upload = useCallback(
    async (file: File) => {
      setBusy("upload");
      try {
        const copy = await storableCopy(file);
        const r = await session.upload(file);
        const rawV = await designsApi.addVersion(designId, {
          ...baseVersion("raw"),
          label: "Raw",
          note: /^IMG|^PXL|^\d{8}/i.test(file.name) ? "Phone photo" : file.name,
          image_url: copy.url,
          width_px: copy.width,
          height_px: copy.height,
        }, false);
        const scanV = r.previews.scan
          ? await designsApi.addVersion(designId, {
              ...baseVersion("scan"),
              parent_id: rawV.id,
              label: "Scanned",
              note: "Auto clean",
              image_url: r.previews.scan,
              width_px: r.info.width,
              height_px: r.info.height,
            }, false)
          : null;
        setAiImg(null);
        const outlineNo = versions.filter((v) => v.kind === "outline").length + 1;
        const lines = r.previews.final ?? r.previews.clean;
        if (!lines) {
          // the backend made only the scan (fast upload); the outline is made by Apply settings
          setApplied("");
          setShownId(null);
          setView("result");
          toast.success("Photo is ready. Use Generate or AI layers, or press Apply settings for a free outline.");
          refresh();
          return;
        }
        await designsApi.addVersion(designId, {
          ...baseVersion("outline"),
          parent_id: scanV?.id ?? rawV.id,
          label: `Outline v${outlineNo}`,
          note: r.info.lines_from ? `${r.info.lines_from} lines` : null,
          image_url: lines,
          width_px: r.info.width,
          height_px: r.info.height,
          dpi: settings.dpi,
          ...sizeMm(r.info.width, r.info.height, settings),
          settings: { ...settings, pending },
          closed_boxes: r.info.closed_boxes,
          gaps_joined: r.info.gaps_joined,
        });
        setApplied(JSON.stringify(settings));
        setShownId(null);
        setView("result");
        if (r.info.ai_note) toast.info(r.info.ai_note);
        toast.success(
          r.info.closed_boxes != null
            ? `Outline v${outlineNo} is ready. ${r.info.closed_boxes} closed boxes, ${r.info.gaps_joined ?? 0} gaps joined.`
            : "Scan is ready.",
        );
        refresh();
      } catch (e) {
        toast.error(errorText(e));
      } finally {
        setBusy(null);
      }
    },
    [session, designId, versions, settings, pending, refresh], // eslint-disable-line react-hooks/exhaustive-deps
  );

  // a photo chosen in the "New design" dialog
  useEffect(() => {
    if (!d) return;
    const f = takePendingUpload(d.id);
    if (f) upload(f);
  }, [d?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------------ apply settings (free)

  async function apply() {
    if (!raw) return toast.error("Upload a raw image first.");
    setBusy("apply");
    try {
      const r = await session.update(settings);
      await addResultVersion({
        kind: "outline",
        image_url: r.previews.final ?? r.previews.clean ?? "",
        note: changeNote(JSON.parse(applied), settings),
        width_px: r.info.width,
        height_px: r.info.height,
        dpi: settings.dpi,
        ...sizeMm(r.info.width, r.info.height, settings),
        settings: { ...settings, pending },
        closed_boxes: r.info.closed_boxes,
        gaps_joined: r.info.gaps_joined,
      });
      setApplied(JSON.stringify(settings));
      setShownId(null);
      await billingApi.logFree(changeNote(JSON.parse(applied), settings) ?? "Settings", party.data?.name ?? null, d?.name ?? null);
      if (pending.flip_h || pending.flip_v || pending.mirror_half || pending.height_cm || pending.fill_repeat)
        toast.info("Mirror, flip, height and repeat-fill are saved but need backend work before they change the image.");
      toast.success(`${nextLabel("outline")} done. No AI credits used.`);
      refresh();
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  // ------------------------------------------------------------------ generate (paid)

  async function generate(message: string): Promise<boolean> {
    if (!d) return false;
    if (!raw) {
      toast.error("Upload a raw image first.");
      return false;
    }
    setBusy("generate");
    let cid = chatId;
    try {
      if (!cid) {
        const c = await chatsApi.start(d.id, message || "Redraw as clean line art");
        cid = c.id;
        setChatId(c.id);
      }
      await chatsApi.addMessage(cid, {
        role: "user",
        content: message || "Redraw this as clean line art.",
        attachment_version_id: null,
        final_prompt: null,
        model_label: null,
        credits_used: 0,
      });
      refresh();
    } catch (e) {
      toast.error(errorText(e));
      setBusy(null);
      return false;
    }

    let reservation: Awaited<ReturnType<typeof billingApi.reserve>> | null = null;
    try {
      reservation = await billingApi.reserve("final", 1, "Final AI outline", party.data?.name ?? null, d.name);
      let image: string | null;
      let reply: string;
      if (message) {
        const r = await session.withSession((id) => outlineApi.chat(id, message));
        image = r.image;
        reply = r.reply;
      } else {
        const r = await session.withSession((id) => outlineApi.perfect(id, settings.output === "scan" ? "color" : "sketch"));
        image = r.image;
        reply = "AI result is ready. Clean black line art from your sketch.";
      }
      await reservation.settle(!!image);
      const v = image
        ? await addResultVersion({ kind: "ai", image_url: image, note: `gpt-image-2 · ${CREDIT_COST.final} cr`, credits: CREDIT_COST.final })
        : null;
      await chatsApi.addMessage(cid, {
        role: "assistant",
        content: image ? reply : `${reply} No credits used.`,
        attachment_version_id: v?.id ?? null,
        final_prompt: null,
        model_label: image ? `gpt-image-2 · medium · ${CREDIT_COST.final} credits` : null,
        credits_used: image ? CREDIT_COST.final : 0,
      });
      if (v) setShownId(v.id);
      refresh();
      return true;
    } catch (e) {
      await reservation?.settle(false);
      await chatsApi.addMessage(cid, {
        role: "assistant",
        content: `${errorText(e)} No credits were used.`,
        attachment_version_id: null,
        final_prompt: null,
        model_label: null,
        credits_used: 0,
      });
      refresh();
      return false;
    } finally {
      setBusy(null);
    }
  }

  function paidPending(action: "watermark" | "resize_fill") {
    toast.info(
      `${action === "watermark" ? "Remove watermark" : "Fill with AI"} needs backend work: the endpoint is not built yet. No credits were used.`,
    );
  }

  async function makeCurrent(v: DesignVersion) {
    await designsApi.update(designId, { current_version_id: v.id });
    toast.success(`${v.label} is now the current version.`);
    refresh();
  }

  // ------------------------------------------------------------------ render

  if (design.isLoading) return <div className="p-6"><Skeleton className="h-[70vh]" /></div>;
  if (design.error) return <div className="p-6"><ErrorBox error={design.error} onRetry={() => design.refetch()} /></div>;
  if (!d) return null;

  const dirty = JSON.stringify(settings) !== applied;
  const offline = health.isError;
  const noAi = health.data && !health.data.perfect;

  return (
    <div className="flex h-[calc(100vh-48px)] flex-col lg:h-screen">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          {party.data ? (
            <Link href={`/parties/${party.data.id}`} className="truncate text-muted hover:text-ink">
              {party.data.name}
            </Link>
          ) : (
            <span className="text-muted">No party</span>
          )}
          <span className="text-muted">/</span>
          <DesignName design={d} onSaved={refresh} />
          <span className="flex items-center gap-1 text-xs text-ok">
            <Check className="h-3.5 w-3.5" /> Saved
          </span>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            accept={IMAGE_TYPES}
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload(f);
              e.target.value = "";
            }}
          />
          <Button onClick={() => fileRef.current?.click()} loading={busy === "upload"}>
            <ImagePlus className="h-4 w-4" /> Upload raw image
          </Button>
          <DownloadMenu
            primary
            label={`Download ${(party.data?.default_formats[0] ?? "svg").toUpperCase()}`}
            sid={session.sid}
            designId={d.id}
            formats={session.result?.previews.final ? session.result.formats : undefined /* lines are made when a file needs them */}
            hasPerfect={results.some((v) => v.kind === "ai")}
            hasLayers={!!layerImg}
            hasAiLayers={!!aiImg}
            fallbackImage={shown?.image_url}
            fallbackName={d.name}
          />
        </div>
      </header>

      {(offline || noAi) && (
        <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-warn">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {offline
            ? "The image server is not reachable. Start backend/api.py (and check BACKEND_URL) to upload, apply settings or generate."
            : "The image server has no OpenAI key, so Generate will not work. Settings, layers and exports still work."}
        </div>
      )}

      {/* phone: one pane at a time */}
      <div className="flex border-b border-line bg-surface lg:hidden">
        {(["chat", "image", "settings"] as const).map((p) => (
          <button
            key={p}
            onClick={() => setMobilePane(p)}
            className={cn("flex-1 py-2 text-sm font-medium capitalize text-muted", mobilePane === p && "border-b-2 border-accent text-ink")}
          >
            {p}
          </button>
        ))}
      </div>

      <div className="flex min-h-0 flex-1">
        <aside className={cn("w-full shrink-0 border-r border-line bg-surface lg:block lg:w-80", mobilePane === "chat" ? "block" : "hidden")}>
          <ChatPanel
            chats={chats.data ?? []}
            chatId={chatId}
            onChatChange={setChatId}
            versions={versions}
            onGenerate={generate}
            busy={busy === "generate"}
            disabled={!raw || offline}
            disabledReason={!raw ? "Upload a raw image first" : "Image server offline"}
          />
        </aside>

        <section className={cn("min-w-0 flex-1 flex-col overflow-y-auto lg:flex", mobilePane === "image" ? "flex" : "hidden")}>
          {!raw ? (
            <UploadBox onFile={upload} busy={busy === "upload"} />
          ) : (
            <div className="flex flex-1 flex-col p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <Tabs value={view} onValueChange={(v) => setView(v as View)} className="min-w-0 max-w-full overflow-x-auto">
                  <TabsList className="border-b-0">
                    <TabsTrigger value="result">Result</TabsTrigger>
                    <TabsTrigger value="scan" disabled={!scan}>Scanned</TabsTrigger>
                    <TabsTrigger value="ailayers">All layers</TabsTrigger>
                    {layerImg && <TabsTrigger value="layers">Colour layers</TabsTrigger>}
                    {session.result?.previews.check && <TabsTrigger value="check">Check gaps</TabsTrigger>}
                  </TabsList>
                </Tabs>
                {results.length > 0 && (
                  <div className="flex items-center gap-2">
                    <Select
                      value={shown?.id ?? ""}
                      onChange={(e) => setShownId(e.target.value)}
                      className="h-8 w-48 text-[13px]"
                      aria-label="Version"
                    >
                      {results.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.label}
                          {v.id === d.current_version_id ? " · current" : ""}
                        </option>
                      ))}
                    </Select>
                    {shown && shown.id !== d.current_version_id && (
                      <Button size="sm" variant="soft" onClick={() => makeCurrent(shown)}>
                        Make current
                      </Button>
                    )}
                  </div>
                )}
              </div>

              <div className="relative flex min-h-[320px] flex-1">
                {busy && busy !== "generate" && (
                  <div className="absolute inset-0 z-10 grid place-items-center rounded-xl bg-white/60">
                    <span className="flex items-center gap-2 rounded-full bg-surface px-4 py-2 text-sm shadow">
                      <Loader2 className="h-4 w-4 animate-spin text-accent" />
                      {busy === "upload" ? "Scanning the photo…" : "Applying settings… (up to a minute the first time)"}
                    </span>
                  </div>
                )}
                {view !== "compare" && (
                  <div className="grid flex-1 gap-3 md:grid-cols-2">
                    <Pane src={raw.image_url} caption={rawCaption(raw)} />
                    {view === "result" && (
                      <Pane src={shown?.image_url ?? null} caption={shown ? resultCaption(shown) : "No result yet: use Generate, AI layers or Apply settings"} checker />
                    )}
                    {view === "scan" && <Pane src={scan?.image_url ?? null} caption="Scanned · page flattened, shadow and grain removed" />}
                    {view === "check" && (
                      <Pane src={session.result?.previews.check ?? null} caption={`Loose line ends are marked · ${session.result?.info.loose_ends ?? 0} loose ends`} />
                    )}
                    {view === "layers" && <Pane src={layerImg} caption="Colour layers preview" checker />}
                    {view === "ailayers" && (
                      <Pane src={aiImg} caption={aiImg ? "AI layers · outlines only, one colour per layer" : "No AI layers yet: open AI layers on the right"} />
                    )}
                  </div>
                )}
                {view === "compare" && shown && (
                  <div className="flex flex-1 flex-col">
                    <ImageCompare before={raw.image_url} after={shown.image_url} beforeLabel="Raw" afterLabel={shown.label} className="min-h-[320px] flex-1" />
                    <p className="mt-2 text-xs text-muted">Drag to compare. {resultCaption(shown)}</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </section>

        <aside className={cn("w-full shrink-0 flex-col border-l border-line bg-surface lg:flex lg:w-80", mobilePane === "settings" ? "flex" : "hidden")}>
          <Tabs value={panel} onValueChange={(v) => {
              setPanel(v as typeof panel);
              if (v === "ailayers") setView("ailayers"); // show the AI layers next to the photo
              else if (v === "layers" && layerImg) setView("layers");
            }} className="flex min-h-0 flex-1 flex-col">
            <TabsList className="px-2">
              <TabsTrigger value="settings">Settings</TabsTrigger>
              <TabsTrigger value="layers">Colour layers</TabsTrigger>
              <TabsTrigger value="ailayers">AI layers</TabsTrigger>
            </TabsList>
            <TabsContent value="settings" className="min-h-0 flex-1">
              <SettingsPanel
                designId={d.id}
                settings={settings}
                onChange={setSettings}
                pending={pending}
                onPendingChange={setPending}
                onApply={apply}
                applying={busy === "apply"}
                dirty={dirty}
                onPaidAction={paidPending}
                paidBusy={null}
              />
            </TabsContent>
            <TabsContent value="layers" className="min-h-0 flex-1">
              <LayersPanel
                withSession={session.withSession}
                sid={session.sid}
                lineColor={settings.color}
                onLineColor={(c) => setSettings({ ...settings, color: c })}
                onPreview={(img) => {
                  setLayerImg(img);
                  if (img) setView("layers");
                }}
              />
            </TabsContent>
            <TabsContent value="ailayers" className="min-h-0 flex-1">
              <AiLayersPanel
                withSession={session.withSession}
                sid={session.sid}
                disabled={!raw || offline || !!noAi}
                reserve={(count) => billingApi.reserve("final", count, "AI layers", party.data?.name ?? null, d.name)}
                onPreview={(img) => {
                  setAiImg(img);
                  if (img) setView("ailayers");
                }}
                onMade={async (s, cost) => {
                  // saved like every AI result: it shows in Designs and in the version list here
                  if (!s.image) return;
                  try {
                    const n = versions.filter((v) => v.label.startsWith("AI layers")).length + 1;
                    const v = await addResultVersion({
                      kind: "ai",
                      image_url: s.image,
                      label: n === 1 ? "AI layers" : `AI layers ${n}`,
                      note: [`${s.layers?.length ?? 0} layers`, s.plan?.machine, s.plan?.model].filter(Boolean).join(" · "),
                      width_px: session.result?.info.width ?? null,
                      height_px: session.result?.info.height ?? null,
                      credits: cost,
                    });
                    setShownId(v.id);
                    refresh();
                  } catch (e) {
                    toast.error(`The AI layers were made but could not be saved to the design: ${errorText(e)}`);
                  }
                }}
              />
            </TabsContent>
          </Tabs>
        </aside>
      </div>
    </div>
  );
}

function rawCaption(v: DesignVersion) {
  return ["Raw", v.note, `uploaded ${shortDate(v.created_at)}`].filter(Boolean).join(" · ");
}

function resultCaption(v: DesignVersion) {
  return [
    v.label,
    sizeLabel(v.width_mm, v.height_mm),
    v.dpi && `${v.dpi} DPI`,
    v.closed_boxes != null && `${v.closed_boxes} closed boxes`,
    v.kind === "ai" && v.note,
  ]
    .filter(Boolean)
    .join(" · ");
}

/** A short note for the version chain: what changed since the last applied settings. */
function changeNote(before: OutlineSettings, after: OutlineSettings): string | null {
  const parts: string[] = [];
  if (before.thickness !== after.thickness || before.uniform_width !== after.uniform_width) parts.push("thickness");
  if (before.join_gaps !== after.join_gaps) parts.push("gap fill");
  if (before.smooth !== after.smooth) parts.push("smooth");
  if (before.sharpness !== after.sharpness) parts.push("sharpness");
  if (before.width_cm !== after.width_cm || before.dpi !== after.dpi) parts.push("size");
  if (before.color !== after.color) parts.push("colour");
  if (!parts.length && JSON.stringify(before) !== JSON.stringify(after)) parts.push("settings");
  if (!parts.length) return null;
  const s = parts.join(" + ");
  return s[0]!.toUpperCase() + s.slice(1);
}

function Pane({ src, caption, checker }: { src: string | null; caption: string; checker?: boolean }) {
  return (
    <figure className="flex min-h-[280px] flex-1 flex-col">
      <div className={cn("relative flex-1 overflow-hidden rounded-xl border border-line", checker ? "checker" : "bg-white")}>
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt={caption} className="absolute inset-0 h-full w-full object-contain p-2" />
        ) : (
          <div className="grid h-full place-items-center text-sm text-muted">Nothing here yet</div>
        )}
      </div>
      <figcaption className="mt-2 truncate text-xs text-muted">{caption}</figcaption>
    </figure>
  );
}

function UploadBox({ onFile, busy }: { onFile: (f: File) => void; busy: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <button
        onClick={() => ref.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          const f = e.dataTransfer.files[0];
          if (f) onFile(f);
        }}
        disabled={busy}
        className={cn(
          "flex w-full max-w-xl flex-col items-center rounded-2xl border-2 border-dashed bg-surface px-8 py-16 text-center transition-colors",
          over ? "border-accent bg-accent-soft" : "border-line hover:border-accent/50",
        )}
      >
        {busy ? <Loader2 className="h-10 w-10 animate-spin text-accent" /> : <ImagePlus className="h-10 w-10 text-accent" />}
        <p className="mt-4 text-lg font-semibold">{busy ? "Scanning the photo…" : "Upload raw image"}</p>
        <p className="mt-1 text-sm text-muted">
          {busy ? "This takes a few seconds." : "Phone photo, scan or sketch. Drop it here or click. JPG or PNG, up to 20 MB."}
        </p>
        <input
          ref={ref}
          type="file"
          accept={IMAGE_TYPES}
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onFile(f);
            e.target.value = "";
          }}
        />
      </button>
    </div>
  );
}

function DesignName({ design, onSaved }: { design: Design; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(design.name);
  useEffect(() => setName(design.name), [design.name]);
  async function save() {
    setEditing(false);
    if (name.trim() && name.trim() !== design.name) {
      await designsApi.update(design.id, { name: name.trim() });
      onSaved();
    } else setName(design.name);
  }
  if (editing)
    return (
      <Input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => e.key === "Enter" && save()}
        className="h-7 w-56"
      />
    );
  return (
    <button onClick={() => setEditing(true)} className="group flex min-w-0 items-center gap-1 font-medium" title="Rename">
      <span className="truncate">{design.name}</span>
      <Pencil className="h-3 w-3 shrink-0 text-muted opacity-0 group-hover:opacity-100" />
    </button>
  );
}
