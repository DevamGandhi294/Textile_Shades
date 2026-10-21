"use client";

import { useEffect, useRef, useState } from "react";
import {
  Check,
  CircleQuestionMark,
  ClipboardPaste,
  Clock,
  Download,
  ImagePlus,
  Info,
  LoaderCircle,
  Play,
  RefreshCw,
  SlidersHorizontal,
  TriangleAlert,
  Upload,
  X,
} from "lucide-react";
import LayersPanel from "@/components/LayersPanel";
import SettingsPanel from "@/components/SettingsPanel";
import { Button, ChoiceCard, Modal, Spinner } from "@/components/controls";
import {
  ApiError,
  DEFAULT_LAYER_OPTIONS,
  createSession,
  downloadFile,
  getHealth,
  getLayers,
  makePerfect,
  sendChat,
  updateSession,
  type LayerOptions,
  type LayersAnswer,
  type Result,
  type Settings,
} from "@/lib/api";
import { ALL_FORMATS, DEFAULTS, FORMATS, LIMITS, isDefault, outputTooLarge } from "@/lib/settings";

const VIEWS = [
  { key: "scan", label: "Scanned" },
  { key: "clean", label: "Cleaned" },
  { key: "final", label: "Final result" },
  { key: "layers", label: "Layers" },
  { key: "perfect", label: "Perfect border" },
  { key: "check", label: "Gap check" },
] as const;
type View = (typeof VIEWS)[number]["key"];

const WIDE = 1024; // from this width the settings panel sits next to the page instead of covering it
const isWide = () => typeof window !== "undefined" && window.innerWidth >= WIDE;

export default function Home() {
  const [splash, setSplash] = useState(true);
  const [welcome, setWelcome] = useState(false);
  const [server, setServer] = useState<"checking" | "ready" | "waking">("checking");
  const [aiReady, setAiReady] = useState(true);
  const [aiStatus, setAiStatus] = useState("");
  const [perfectReady, setPerfectReady] = useState(false); // OpenAI key set on the server
  const [perfectImg, setPerfectImg] = useState<string | null>(null); // "Make border perfect" result

  const [file, setFile] = useState<File | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [asking, setAsking] = useState(false); // "recommended or my own settings?" popup
  const [waiting, setWaiting] = useState(false); // photo chosen, not started yet
  const [result, setResult] = useState<Result | null>(null);
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [autoCrop, setAutoCrop] = useState(true);
  const [formats, setFormats] = useState<string[]>(ALL_FORMATS);
  const [busy, setBusy] = useState<"" | "upload" | "update" | "perfect" | "chat" | "layers">("");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const [view, setView] = useState<View>("final");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [downloading, setDownloading] = useState(""); // file type being prepared for download
  const [chatOpen, setChatOpen] = useState(false); // "Chat to improve it" panel
  const [layersData, setLayersData] = useState<LayersAnswer | null>(null); // colour layers (Layers tab)
  const [layerOpts, setLayerOpts] = useState<LayerOptions>(DEFAULT_LAYER_OPTIONS);
  const [chatLog, setChatLog] = useState<ChatLine[]>([]);
  const [chatInput, setChatInput] = useState("");
  const chatBoxRef = useRef<HTMLDivElement>(null);

  const latest = useRef(settings); // newest settings, also while a slider is moving
  const sent = useRef(""); // settings the server last processed, to skip repeat calls
  const pickRef = useRef<HTMLInputElement>(null);

  // Splash screen, then every time the site opens: recommended or own settings?
  useEffect(() => {
    const t = setTimeout(() => {
      setSplash(false);
      setWelcome(true);
    }, 1600);
    return () => clearTimeout(t);
  }, []);

  // The free server sleeps when nobody uses it; wake it as soon as the page opens.
  useEffect(() => {
    let stop = false;
    (async () => {
      for (let i = 0; !stop && i < 40; i++) {
        const h = await getHealth();
        if (stop) return;
        if (h) {
          setServer("ready");
          setAiReady(h.ai);
          setAiStatus(h.ai_status);
          setPerfectReady(!!h.perfect);
          return;
        }
        setServer("waking");
        await new Promise((r) => setTimeout(r, 5000));
      }
    })();
    return () => {
      stop = true;
    };
  }, []);

  // A seconds counter while working, so the user knows it has not frozen.
  useEffect(() => {
    if (!busy) return;
    const start = Date.now();
    const t = setInterval(() => setSeconds(Math.round((Date.now() - start) / 1000)), 1000);
    return () => {
      clearInterval(t);
      setSeconds(0);
    };
  }, [busy]);

  // Paste a picture with Ctrl+V.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const f = Array.from(e.clipboardData?.files ?? []).find((x) => x.type.startsWith("image/"));
      if (f) choose(f);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  });

  useEffect(() => () => void (photoUrl && URL.revokeObjectURL(photoUrl)), [photoUrl]);

  useEffect(() => {
    const box = chatBoxRef.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [chatLog, busy, chatOpen]);

  // ------------------------------------------------------------------ welcome popup answers

  function welcomeRecommended() {
    setWelcome(false);
    edit(DEFAULTS);
  }

  function welcomeOwn() {
    setWelcome(false);
    setSettingsOpen(true);
  }

  // ------------------------------------------------------------------ photo and processing

  function choose(f: File) {
    if (busy) return;
    setFile(f);
    setPhotoUrl(URL.createObjectURL(f));
    setResult(null);
    setPerfectImg(null);
    setLayersData(null);
    setLayerOpts(DEFAULT_LAYER_OPTIONS);
    setChatLog([]);
    setChatOpen(false);
    setError("");
    setWaiting(true);
    setAsking(true); // always ask before any processing starts
  }

  function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (f) choose(f);
  }

  // "Paste from clipboard" button (Ctrl+V works too, see the paste listener above).
  async function pasteImage() {
    try {
      for (const item of await navigator.clipboard.read()) {
        const type = item.types.find((t) => t.startsWith("image/"));
        if (type) {
          const blob = await item.getType(type);
          return choose(new File([blob], `pasted.${type.split("/")[1]}`, { type }));
        }
      }
      setError("There is no image in the clipboard. Copy an image first, then try again.");
    } catch {
      setError("Could not read the clipboard. Copy an image, click on this page and press Ctrl + V.");
    }
  }

  async function upload(f: File, s: Settings, crop: boolean) {
    setError("");
    setWaiting(false);
    if (!isWide()) setSettingsOpen(false); // on phones the panel would cover the progress
    setBusy("upload");
    sent.current = JSON.stringify(s);
    try {
      setResult(await createSession(f, s, crop));
      setLayersData(null);
      setLayerOpts(DEFAULT_LAYER_OPTIONS);
      setView("final");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setWaiting(true);
    } finally {
      setBusy("");
    }
  }

  function start(s: Settings = latest.current) {
    setAsking(false);
    if (file) upload(file, s, autoCrop);
  }

  function startWithRecommended() {
    edit(DEFAULTS);
    start(DEFAULTS);
  }

  function chooseFirst() {
    setAsking(false);
    setSettingsOpen(true);
  }

  // ------------------------------------------------------------------ settings

  function edit(patch: Partial<Settings>) {
    latest.current = { ...latest.current, ...patch };
    setSettings(latest.current);
  }

  async function apply(patch: Partial<Settings> = {}) {
    edit(patch);
    const next = latest.current;
    if (!result || !file || busy || JSON.stringify(next) === sent.current) return;
    sent.current = JSON.stringify(next);
    setError("");
    setBusy("update");
    try {
      const fresh = await updateSession(result.id, next);
      setResult(fresh);
      setLayersData(null);
      setLayerOpts(DEFAULT_LAYER_OPTIONS);
      if (view === "layers") await loadLayers(fresh.id, DEFAULT_LAYER_OPTIONS);
    } catch (e) {
      // the server forgot this photo (restart or too long ago): just process it again
      if (e instanceof ApiError && e.status === 404) return upload(file, next, autoCrop);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  function changeCrop(v: boolean) {
    setAutoCrop(v);
    if (result && file) upload(file, latest.current, v);
  }

  function reset() {
    setFormats(ALL_FORMATS);
    if (autoCrop) return apply(DEFAULTS);
    // crop was off: the photo has to be cleaned again from the start
    setAutoCrop(true);
    edit(DEFAULTS);
    if (result && file) upload(file, DEFAULTS, true);
  }

  // Colour layers: asked from the server whenever the user opens the tab or changes a choice (free).
  async function loadLayers(id: string, options: LayerOptions) {
    setError("");
    setBusy("layers");
    try {
      setLayersData(await getLayers(id, options));
      setLayerOpts(options);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setView("final");
    } finally {
      setBusy("");
    }
  }

  // Tab click; the layers are worked out the first time the tab is opened for this result.
  function openView(v: View) {
    setView(v);
    if (v === "layers" && !layersData && result && !busy) loadLayers(result.id, layerOpts);
  }

  // OpenAI redraws the final lines with clean, smooth curves; shown as its own view.
  async function runPerfect() {
    if (!result || busy) return;
    setError("");
    setBusy("perfect");
    try {
      const answer = await makePerfect(result.id);
      setPerfectImg(answer.image);
      setResult((r) => (r ? { ...r, perfect: answer.perfect } : r));
      setView("perfect");
    } catch (e) {
      // limit for this photo reached: show the counter as full so the button is disabled
      if (e instanceof ApiError && e.status === 429 && e.message.includes("per photo"))
        setResult((r) => (r?.perfect ? { ...r, perfect: { ...r.perfect, used: r.perfect.limit } } : r));
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  // "Chat to improve it": one message. The server checks it is about editing the border image;
  // an allowed edit comes back with a new Perfect border, anything else with a short refusal.
  async function sendMessage(text: string) {
    const message = text.trim().slice(0, LIMITS.chatMaxChars);
    if (!message || !result || busy) return;
    setError("");
    setChatInput("");
    setChatLog((l) => [...l, { role: "user", text: message }]);
    setBusy("chat");
    try {
      const answer = await sendChat(result.id, message);
      setChatLog((l) => [...l, { role: "assistant", text: answer.reply }]);
      setResult((r) => (r ? { ...r, perfect: answer.perfect, chat: answer.chat } : r));
      if (answer.image) {
        setPerfectImg(answer.image);
        setView("perfect");
      }
    } catch (e) {
      const reason = e instanceof Error ? e.message : String(e);
      // a limit was reached: show that counter as full so the box says so
      if (e instanceof ApiError && e.status === 429) {
        const which = reason.includes("chat messages") ? "chat" : reason.includes("Make border perfect") ? "perfect" : null;
        if (which) setResult((r) => (r?.[which] ? { ...r, [which]: { ...r[which], used: r[which].limit } } : r));
      }
      setChatLog((l) => [...l, { role: "assistant", text: reason, error: true }]);
    } finally {
      setBusy("");
    }
  }

  function startOver() {
    setFile(null);
    setPhotoUrl(null);
    setResult(null);
    setPerfectImg(null);
    setLayersData(null);
    setLayerOpts(DEFAULT_LAYER_OPTIONS);
    setChatLog([]);
    setChatOpen(false);
    setWaiting(false);
    setError("");
  }

  // ------------------------------------------------------------------ downloads

  const bw = settings.output === "bw";
  const ready = result ? FORMATS.filter((f) => result.formats.includes(f.fmt)) : [];
  const chosen = ready.filter((f) => formats.includes(f.fmt));

  const tooLarge = !!result && outputTooLarge(result.info.width, result.info.height, settings);
  const usage = result?.perfect;
  const perfectUsedUp = !!usage && usage.used >= usage.limit;
  const chatUsage = result?.chat;
  const chatUsedUp = !!chatUsage && chatUsage.used >= chatUsage.limit;

  // Save one file; errors (for example "That size is too large") are shown on the page.
  async function save(fmt: string, ext: string) {
    if (!result || downloading) return;
    setError("");
    setDownloading(fmt);
    try {
      await downloadFile(result.id, fmt, `${result.name}.${ext}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDownloading("");
    }
  }

  async function downloadChosen() {
    for (const f of chosen) {
      await save(f.fmt, f.fmt);
      await new Promise((r) => setTimeout(r, 600)); // browsers block many saves at the same moment
    }
  }

  const blocked = !!busy || !!downloading;

  const shownViews = VIEWS.filter(
    (v) =>
      (v.key !== "check" || result?.previews.check) &&
      (v.key !== "perfect" || perfectImg) &&
      (v.key !== "layers" || result?.info.output === "bw"),
  );
  const shown =
    view === "perfect" && perfectImg
      ? perfectImg
      : view === "layers" && layersData
        ? layersData.image
        : result
          ? (result.previews[view as Exclude<View, "perfect" | "layers">] ?? result.previews.final)
          : null;
  const shownLabel = VIEWS.find((v) => v.key === view)?.label ?? "Result";

  return (
    <>
      {splash && <Splash />}

      <header className="border-b border-sand bg-white">
        <div className="mx-auto flex w-full max-w-[90rem] items-center gap-4 px-4 py-3 sm:px-8 sm:py-4">
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-bold tracking-tight sm:text-2xl">
              TextileBorder <span className="text-brand">OutlineTool</span>
            </h1>
            <p className="hidden text-sm text-muted md:block">
              Upload a photo or scan of a sketch. It becomes a clean scan automatically; adjust only if needed, then download.
            </p>
          </div>
          <Button kind="ghost" onClick={() => setWelcome(true)} className="px-3">
            <CircleQuestionMark className="h-5 w-5" aria-hidden /> <span className="hidden sm:inline">Help</span>
          </Button>
          <Button onClick={() => setSettingsOpen(!settingsOpen)} className="px-4">
            <SlidersHorizontal className="h-5 w-5" aria-hidden /> Settings
          </Button>
        </div>
      </header>

      {server === "waking" && (
        <p className="flex items-center justify-center gap-2 bg-sand px-4 py-2.5 text-center text-sm">
          <Clock className="h-4 w-4 shrink-0 text-btn" aria-hidden />
          The service is starting up. The first time this can take about one minute. You can already choose your photo.
        </p>
      )}

      <div className="mx-auto flex w-full max-w-[90rem] items-start gap-6 px-4 py-4 sm:px-8 sm:py-5">
        <main className="flex min-w-0 flex-1 flex-col gap-6">
          {error && (
            <div role="alert" className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-red-900">
              <TriangleAlert className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
              <span className="flex-1">{error}</span>
              <button type="button" onClick={() => setError("")} aria-label="Close message" className="rounded-full p-1 hover:bg-red-100">
                <X className="h-4 w-4" aria-hidden />
              </button>
            </div>
          )}

          {/* Step 1: upload (empty page) */}
          {!file && (
            <Card>
              <div className="flex flex-col gap-1.5">
                <span className="mb-1 inline-flex items-center gap-2 self-start rounded-full bg-mint-soft px-3 py-1 text-xs font-bold tracking-wider text-btn-hover uppercase">
                  <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden /> Start here
                </span>
                <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Bring your sketch to life.</h2>
                <p className="max-w-2xl text-muted">
                  Add a photo of your border drawing. We&apos;ll help turn it into clean lines you can use for embroidery, printing or design.
                </p>
              </div>

              <input ref={pickRef} type="file" accept="image/*" className="hidden" onChange={onPick} />
              <div
                role="button"
                tabIndex={0}
                aria-label="Upload a sketch photo"
                onClick={() => !busy && pickRef.current?.click()}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !busy && pickRef.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  const f = e.dataTransfer.files?.[0];
                  if (f) choose(f);
                }}
                className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed px-6 py-5 text-center transition ${
                  dragging ? "border-brand bg-mint-soft" : "border-mint bg-mint-soft/50 hover:bg-gray-50"
                }`}
              >
                <span className="mb-1.5 flex h-11 w-11 items-center justify-center rounded-xl bg-mint-soft text-btn shadow-sm ring-1 ring-mint/50">
                  <ImagePlus className="h-6 w-6" aria-hidden />
                </span>
                <span className="text-lg font-semibold">Drop image here</span>
                <span className="text-sm text-muted">— or —</span>
                <span className="text-sm text-muted">Click to upload · JPG, PNG or TIFF</span>
                <span className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-xl bg-btn px-5 font-semibold text-white shadow-sm">
                  <Upload className="h-5 w-5" aria-hidden /> Upload photo
                </span>
              </div>

              <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
                <Button kind="outline" onClick={pasteImage} disabled={!!busy} className="min-h-11">
                  <ClipboardPaste className="h-5 w-5" aria-hidden /> Paste from clipboard
                </Button>
                <p className="text-sm text-muted">You can also copy an image and press Ctrl + V on this page.</p>
              </div>

              <p className="flex items-start gap-3 rounded-2xl bg-sand px-4 py-3 text-sm">
                <Info className="mt-0.5 h-5 w-5 shrink-0 text-btn" aria-hidden />
                <span>
                  <b className="font-semibold">A little photo tip:</b> Good light and a straight-above photo help us find the lines in your drawing.
                </span>
              </p>
            </Card>
          )}

          {/* Photo chosen, waiting for the user to start */}
          {waiting && file && !busy && (
            <Card>
              <CardTitle step="Step 2" title="Your photo is ready" />
              {photoUrl && (
                // eslint-disable-next-line @next/next/no-img-element -- local photo preview
                <img src={photoUrl} alt="Your photo" className="max-h-96 w-full rounded-2xl bg-gray-50 object-contain" />
              )}
              <p className="text-muted">Check the settings, then press Start cleaning.</p>
              <div className="flex flex-wrap gap-3">
                <Button onClick={() => start()}>
                  <Play className="h-5 w-5" aria-hidden /> Start cleaning
                </Button>
                <Button kind="outline" onClick={() => setSettingsOpen(true)}>
                  <SlidersHorizontal className="h-5 w-5" aria-hidden /> Settings
                </Button>
                <Button kind="ghost" onClick={startOver}>
                  Choose another photo
                </Button>
              </div>
            </Card>
          )}

          {busy === "upload" && (
            <Card>
              <div className="flex flex-col items-center gap-3 py-16 text-center">
                <Spinner />
                <p className="text-xl font-semibold">Cleaning your sketch… {seconds} s</p>
                <p className="text-muted">
                  This usually takes 20 to 40 seconds. Please keep this page open.
                  {server === "waking" && " The service is still starting, so the first time can take longer."}
                </p>
              </div>
            </Card>
          )}

          {/* Step 2: result */}
          {result && busy !== "upload" && (
            <Card>
              <div className="flex flex-wrap items-end justify-between gap-3">
                <CardTitle step="Step 2" title="Check the result" />
                <div className="flex flex-wrap gap-1 rounded-xl bg-gray-100 p-1" role="tablist">
                  {shownViews.map((v) => (
                    <button
                      key={v.key}
                      type="button"
                      role="tab"
                      aria-selected={view === v.key}
                      onClick={() => openView(v.key)}
                      className={`min-h-10 rounded-lg px-3 text-sm font-semibold transition ${
                        view === v.key ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink"
                      }`}
                    >
                      {v.label}
                    </button>
                  ))}
                </div>
              </div>
              {view === "check" && (
                <p className="rounded-xl bg-gray-50 px-4 py-2.5 text-sm text-muted">
                  Every closed area has its own colour. <b className="text-green-800">Green</b> = gaps that were joined.{" "}
                  <b className="text-red-800">Red circle</b> = open line end, where colour fill could leak.
                </p>
              )}
              {/* left: always the original photo · right: the tab that is selected */}
              <div className="grid gap-4 md:grid-cols-2">
                <figure className="flex min-w-0 flex-col gap-2">
                  <figcaption className="text-sm font-semibold text-muted">Original photo</figcaption>
                  <div className="flex min-h-72 flex-1 items-center justify-center overflow-hidden rounded-2xl border border-line bg-gray-50">
                    {photoUrl && (
                      // eslint-disable-next-line @next/next/no-img-element -- local photo preview
                      <img src={photoUrl} alt="Original photo" className="max-h-[70vh] w-full object-contain" />
                    )}
                  </div>
                </figure>
                <figure className="flex min-w-0 flex-col gap-2">
                  <figcaption className="text-sm font-semibold text-muted">{shownLabel}</figcaption>
                  <div className="relative flex min-h-72 flex-1 items-center justify-center overflow-hidden rounded-2xl border border-line bg-gray-50">
                    {shown && (
                      // eslint-disable-next-line @next/next/no-img-element -- previews are data URLs from the API
                      <img src={shown} alt={shownLabel} className="max-h-[70vh] w-full object-contain" />
                    )}
                    {(busy === "update" || busy === "perfect" || busy === "layers") && (
                      <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-white/80 px-4 text-center backdrop-blur-[1px]">
                        <Spinner />
                        <p className="font-semibold">
                          {busy === "perfect" ? "Making the border perfect…" : busy === "layers" ? "Finding the colours…" : "Updating…"}{" "}
                          {seconds} s
                        </p>
                        {busy === "perfect" && (
                          <p className="text-sm text-muted">Usually under a minute, sometimes up to a few minutes.</p>
                        )}
                      </div>
                    )}
                  </div>
                </figure>
              </div>
              {view === "layers" && layersData && result && (
                <LayersPanel
                  data={layersData}
                  options={layerOpts}
                  busy={!!busy}
                  downloading={downloading}
                  onChange={(next) => loadLayers(result.id, next)}
                  onDownload={(fmt) => save(fmt, fmt === "layers-svg" ? "svg" : fmt === "layers-psd" ? "psd" : "zip")}
                />
              )}
              <Summary result={result} />
              {perfectReady && (
                <div className="flex flex-col gap-3 rounded-2xl border border-brand/40 bg-mint-soft p-4">
                  <div className="flex flex-col gap-1">
                    <p className="font-semibold">Make this perfect outline border</p>
                    <p className="text-sm text-muted">
                      Get a clean, smooth outline of your design. The result appears as “Perfect border” next to Final
                      result. Choose how:
                    </p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="flex flex-col gap-1">
                      <Button onClick={runPerfect} disabled={!!busy || perfectUsedUp}>
                        {perfectImg ? "Make it again" : "Make perfect outline border"}
                      </Button>
                      <span className="text-xs text-muted">One click. Uses our default settings.</span>
                    </div>
                    <div className="flex flex-col gap-1">
                      <Button kind="outline" onClick={() => setChatOpen((o) => !o)} disabled={busy === "perfect"}>
                        {chatOpen ? "Close chat" : "Chat to improve it"}
                      </Button>
                      <span className="text-xs text-muted">Tell us what to change, in your own words.</span>
                    </div>
                  </div>
                  {usage && (
                    <span className="text-xs text-muted">
                      {perfectUsedUp
                        ? "Image limit reached for this photo. Upload it again to try more."
                        : `Images used ${usage.used} of ${usage.limit} for this photo`}
                    </span>
                  )}

                  {chatOpen && (
                    <div className="flex flex-col gap-3 rounded-xl bg-white p-3">
                      <p className="text-sm text-muted">
                        You can ask only for changes to your border image, for example “make the lines thinner”, “close the
                        small gaps” or “remove the dots”. Other questions will not be answered.
                      </p>
                      <div
                        ref={chatBoxRef}
                        role="log"
                        aria-live="polite"
                        className="flex max-h-72 min-h-24 flex-col gap-2 overflow-y-auto rounded-lg bg-gray-50 p-3"
                      >
                        {chatLog.length === 0 && busy !== "chat" && (
                          <p className="text-sm text-muted">No messages yet. Type what you want to change, or tap an example.</p>
                        )}
                        {chatLog.map((m, i) => (
                          <div
                            key={i}
                            className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                              m.role === "user"
                                ? "self-end bg-btn text-white"
                                : m.error
                                  ? "self-start bg-red-50 text-red-900"
                                  : "self-start border border-line bg-white text-ink"
                            }`}
                          >
                            {m.text}
                          </div>
                        ))}
                        {busy === "chat" && (
                          <div className="self-start rounded-2xl border border-line bg-white px-3 py-2 text-sm text-muted">
                            Working on it… {seconds} s
                            <span className="block text-xs">Changing the image can take up to a minute.</span>
                          </div>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {["Make the lines thinner", "Close the small gaps", "Remove the small dots"].map((example) => (
                          <button
                            key={example}
                            type="button"
                            onClick={() => setChatInput(example)}
                            disabled={!!busy || chatUsedUp}
                            className="rounded-full border border-line bg-white px-3 py-1 text-xs hover:bg-gray-100 disabled:opacity-50"
                          >
                            {example}
                          </button>
                        ))}
                      </div>
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          sendMessage(chatInput);
                        }}
                        className="flex gap-2"
                      >
                        <input
                          type="text"
                          value={chatInput}
                          maxLength={LIMITS.chatMaxChars}
                          onChange={(e) => setChatInput(e.target.value)}
                          disabled={!!busy || chatUsedUp}
                          placeholder="Type what you want to change…"
                          aria-label="Your message"
                          className="h-11 min-w-0 flex-1 rounded-xl border border-line bg-white px-3 disabled:opacity-50"
                        />
                        <Button onClick={() => sendMessage(chatInput)} disabled={!!busy || chatUsedUp || !chatInput.trim()}>
                          Send
                        </Button>
                      </form>
                      {chatUsage && (
                        <span className="text-xs text-muted">
                          {chatUsedUp
                            ? "Message limit reached for this photo. Upload it again to continue."
                            : `Messages used ${chatUsage.used} of ${chatUsage.limit} for this photo`}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )}
            </Card>
          )}

          {/* Step 3: download */}
          {result && busy !== "upload" && (
            <Card>
              <CardTitle step="Step 3" title="Download" />
              {tooLarge && (
                <p role="alert" className="flex items-start gap-2 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-900">
                  <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                  That size is too large to download. Lower the DPI or the width in Settings → Download settings.
                </p>
              )}
              <button
                type="button"
                onClick={() => save("zip", "zip")}
                disabled={blocked || tooLarge}
                className="inline-flex min-h-14 items-center justify-center gap-2 rounded-xl bg-btn px-6 text-lg font-semibold text-white shadow-sm hover:bg-btn-hover disabled:cursor-not-allowed disabled:opacity-50"
              >
                <DownloadIcon busy={downloading === "zip"} className="h-5 w-5" />
                {downloading === "zip" ? "Preparing the ZIP…" : "Download all files (ZIP)"}
              </button>
              {perfectImg && (
                <button
                  type="button"
                  onClick={() => save("perfect", "png")}
                  disabled={blocked}
                  className="flex items-center gap-3 rounded-xl border border-brand bg-mint-soft px-4 py-3 text-left transition hover:bg-mint/40 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <span className="flex flex-col">
                    <span className="font-semibold">
                      {downloading === "perfect" ? "Preparing…" : "Perfect border (transparent PNG)"}
                    </span>
                    <span className="text-sm text-muted">
                      Black lines on a transparent background, with no colour: open it in Photoshop as one layer and
                      add colour layers under it. A picture only, so it is not in the SVG, PDF, EPS or DXF files. Also
                      included in the ZIP.
                    </span>
                  </span>
                </button>
              )}
              {perfectImg && (
                <button
                  type="button"
                  onClick={() => save("perfect-psd", "psd")}
                  disabled={blocked}
                  className="flex items-center gap-3 rounded-xl border border-brand bg-mint-soft px-4 py-3 text-left transition hover:bg-mint/40 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <span className="flex flex-col">
                    <span className="font-semibold">
                      {downloading === "perfect-psd" ? "Preparing…" : "Perfect border with layers (PSD)"}
                    </span>
                    <span className="text-sm text-muted">
                      One Photoshop file with separate layers: a white background, a layer for each colour of your photo,
                      and your perfect border on top. If the photo has no colour, it has the background and the border.
                      No extra cost.
                    </span>
                  </span>
                </button>
              )}
              {chosen.length > 0 && (
                <>
                  <p className="text-sm text-muted">Or download one file at a time:</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {chosen.map((f) => (
                      <button
                        key={f.fmt}
                        type="button"
                        onClick={() => save(f.fmt, f.fmt === "tiff" ? "tif" : f.fmt)}
                        disabled={blocked || tooLarge}
                        className="flex items-center gap-3 rounded-xl border border-line bg-white px-4 py-3 text-left transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-mint-soft text-btn">
                          <DownloadIcon busy={downloading === f.fmt} className="h-4 w-4" />
                        </span>
                        <span className="flex flex-col">
                          <span className="font-semibold">{f.label}</span>
                          <span className="text-sm text-muted">{f.hint}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                  {chosen.length > 1 && chosen.length < ready.length && (
                    <Button kind="outline" onClick={downloadChosen} disabled={blocked || tooLarge} className="self-start">
                      <Download className="h-5 w-5" aria-hidden /> Download my {chosen.length} chosen files
                    </Button>
                  )}
                </>
              )}
              <p className="text-sm text-muted">
                Choose which file types to show in Settings → Download settings → Formats.
                {!bw && " Vector, CAD and print files need the black & white output."}
              </p>
              <Button kind="ghost" onClick={startOver} className="self-start px-3">
                <RefreshCw className="h-4 w-4" aria-hidden /> Start again with a new photo
              </Button>
            </Card>
          )}
        </main>

        {/* Settings panel: next to the page on big screens, full screen on phones */}
        {settingsOpen && (
          <>
            <div className="fixed inset-0 z-30 bg-ink/30 lg:hidden" onClick={() => setSettingsOpen(false)} aria-hidden />
            <aside
              aria-label="Settings"
              className="panel-in fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col bg-white shadow-2xl lg:sticky lg:top-6 lg:z-auto lg:max-h-[calc(100vh-3rem)] lg:w-96 lg:shrink-0 lg:rounded-3xl lg:border lg:border-line lg:shadow-sm"
            >
              <div className="flex items-start gap-3 border-b border-line px-6 py-5">
                <SlidersHorizontal className="mt-1 h-5 w-5 shrink-0 text-brand" aria-hidden />
                <div className="flex-1">
                  <h2 className="text-xl font-semibold">Settings</h2>
                  <p className="text-sm text-muted">Adjust your outline and file types.</p>
                </div>
                <button
                  type="button"
                  onClick={() => setSettingsOpen(false)}
                  aria-label="Close settings"
                  className="flex h-9 w-9 items-center justify-center rounded-full text-ink hover:bg-gray-100"
                >
                  <X className="h-5 w-5" aria-hidden />
                </button>
              </div>
              <div className="relative flex-1 overflow-y-auto px-6 py-5">
                <SettingsPanel
                  settings={settings}
                  edit={edit}
                  apply={apply}
                  autoCrop={autoCrop}
                  setAutoCrop={changeCrop}
                  formats={formats}
                  setFormats={setFormats}
                  aiReady={aiReady}
                  aiStatus={aiStatus}
                  busy={!!busy}
                  waitingToStart={waiting && !!file}
                  onStart={() => start()}
                  onReset={reset}
                  sizeTooLarge={tooLarge}
                />
              </div>
            </aside>
          </>
        )}
      </div>

      {/* When the site opens: how it works, then recommended or own settings */}
      <Modal open={welcome && !splash} title="Welcome" onClose={() => setWelcome(false)}>
        <p className="text-muted">Make a clean drawing from a photo in 3 easy steps:</p>
        <ol className="flex flex-col gap-2">
          {(
            [
              [Upload, "Upload or paste a photo of your sketch."],
              [SlidersHorizontal, "Use our recommended settings, or choose your own."],
              [Download, "Download your files for embroidery, printing or CAD."],
            ] as const
          ).map(([Icon, text], i) => (
            <li key={i} className="flex items-center gap-3 rounded-xl bg-gray-50 px-3 py-2.5">
              <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-mint-soft text-sm font-bold text-btn">
                {i + 1}
              </span>
              <Icon className="h-5 w-5 shrink-0 text-btn" aria-hidden />
              <span>{text}</span>
            </li>
          ))}
        </ol>
        <p className="mt-1 font-semibold">Which settings do you want to use?</p>
        <ChoiceCard
          primary
          icon={<Check className="h-5 w-5" aria-hidden />}
          title="Use recommended settings"
          text="Best for most sketches. You do not need to change anything."
          onClick={welcomeRecommended}
        />
        <ChoiceCard
          icon={<SlidersHorizontal className="h-5 w-5" aria-hidden />}
          title="Choose my own settings"
          text="Opens the settings panel. Then upload your photo."
          onClick={welcomeOwn}
        />
      </Modal>

      {/* Before any processing: recommended or own settings? */}
      <Modal open={asking} title="How should we clean your photo?" onClose={() => setAsking(false)}>
        {photoUrl && (
          // eslint-disable-next-line @next/next/no-img-element -- local photo preview
          <img src={photoUrl} alt="Your photo" className="max-h-44 w-full rounded-2xl bg-gray-50 object-contain" />
        )}
        <ChoiceCard
          primary
          icon={<Check className="h-5 w-5" aria-hidden />}
          title="Use recommended settings"
          text="Best for most sketches. Starts now."
          onClick={startWithRecommended}
        />
        {!isDefault(settings) && (
          <ChoiceCard
            icon={<Play className="h-5 w-5" aria-hidden />}
            title="Use my settings"
            text="The settings you chose before. Starts now."
            onClick={() => start()}
          />
        )}
        <ChoiceCard
          icon={<SlidersHorizontal className="h-5 w-5" aria-hidden />}
          title="Let me choose settings first"
          text="Opens the settings. Press Start cleaning when you are ready."
          onClick={chooseFirst}
        />
      </Modal>
    </>
  );
}

type ChatLine = { role: "user" | "assistant"; text: string; error?: boolean };

function DownloadIcon({ busy, className }: { busy: boolean; className: string }) {
  return busy ? (
    <LoaderCircle className={`${className} animate-spin`} aria-hidden />
  ) : (
    <Download className={className} aria-hidden />
  );
}

function Splash() {
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 bg-white" role="status" aria-label="Loading">
      <div className="splash-pop flex flex-col items-center gap-3 text-center">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          TextileBorder <span className="text-brand">OutlineTool</span>
        </h1>
        <p className="text-lg text-muted">Clean lines from your sketch photos</p>
      </div>
      <div className="h-1.5 w-48 overflow-hidden rounded-full bg-mint-soft">
        <div className="splash-bar h-full w-1/3 rounded-full bg-brand" />
      </div>
    </div>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return <section className="flex flex-col gap-4 rounded-3xl border border-line bg-white p-5 shadow-sm sm:p-6">{children}</section>;
}

function CardTitle({ step, title }: { step: string; title: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-bold tracking-widest text-brand uppercase">{step}</span>
      <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
    </div>
  );
}

function Summary({ result }: { result: Result }) {
  const i = result.info;
  const secs = Math.round(Object.values(i.seconds).reduce((a, b) => a + b, 0));
  const items: string[] = [];
  if (i.output === "bw") {
    items.push(i.lines_from === "ai" ? "AI lines" : "Classic lines");
    if (i.closed_boxes != null) items.push(`${i.closed_boxes} closed boxes`);
    if (i.gaps_joined) items.push(`${i.gaps_joined} gaps joined`);
    items.push(i.loose_ends ? `${i.loose_ends} loose line ends (see Gap check)` : "All lines closed");
  } else {
    items.push("Scanner output");
  }
  items.push(`${i.width} × ${i.height} pixels`, `took ${secs} s`);
  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-wrap gap-2 text-sm">
        {items.map((t) => (
          <li key={t} className="rounded-full bg-mint-soft px-3 py-1 font-medium text-btn-hover">
            {t}
          </li>
        ))}
      </ul>
      {i.ai_note && <p className="text-sm text-amber-900">Note: {i.ai_note}</p>}
    </div>
  );
}
