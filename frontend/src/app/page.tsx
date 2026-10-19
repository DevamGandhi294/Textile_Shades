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
  Play,
  RefreshCw,
  SlidersHorizontal,
  TriangleAlert,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import SettingsPanel from "@/components/SettingsPanel";
import { Button, ChoiceCard, Modal, Spinner } from "@/components/controls";
import { ApiError, createSession, downloadUrl, getHealth, makePerfect, updateSession, type Result, type Settings } from "@/lib/api";
import { ALL_FORMATS, DEFAULTS, FORMATS, isDefault } from "@/lib/settings";

const VIEWS = [
  { key: "photo", label: "Your photo" },
  { key: "scan", label: "Scanned" },
  { key: "clean", label: "Cleaned" },
  { key: "final", label: "Final result" },
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
  const [perfectSource, setPerfectSource] = useState<"sketch" | "color">("sketch"); // which picture is redrawn

  const [file, setFile] = useState<File | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [asking, setAsking] = useState(false); // "recommended or my own settings?" popup
  const [waiting, setWaiting] = useState(false); // photo chosen, not started yet
  const [result, setResult] = useState<Result | null>(null);
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [autoCrop, setAutoCrop] = useState(true);
  const [formats, setFormats] = useState<string[]>(ALL_FORMATS);
  const [busy, setBusy] = useState<"" | "upload" | "update" | "perfect">("");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const [view, setView] = useState<View>("final");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dragging, setDragging] = useState(false);

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
      setResult(await updateSession(result.id, next));
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

  // OpenAI redraws the final lines with clean, smooth curves; shown as its own view.
  async function runPerfect() {
    if (!result || busy) return;
    setError("");
    setBusy("perfect");
    try {
      setPerfectImg((await makePerfect(result.id, perfectSource)).image);
      setView("perfect");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  function startOver() {
    setFile(null);
    setPhotoUrl(null);
    setResult(null);
    setPerfectImg(null);
    setWaiting(false);
    setError("");
  }

  // ------------------------------------------------------------------ downloads

  const bw = settings.output === "bw";
  const ready = result ? FORMATS.filter((f) => result.formats.includes(f.fmt)) : [];
  const chosen = ready.filter((f) => formats.includes(f.fmt));

  function downloadChosen() {
    if (!result) return;
    chosen.forEach((f, i) =>
      setTimeout(() => {
        const a = document.createElement("a");
        a.href = downloadUrl(result.id, f.fmt);
        a.download = "";
        document.body.appendChild(a);
        a.click();
        a.remove();
      }, i * 1500),
    );
  }

  const shownViews = VIEWS.filter(
    (v) => (v.key !== "check" || result?.previews.check) && (v.key !== "perfect" || perfectImg),
  );
  const shown =
    view === "photo"
      ? photoUrl
      : view === "perfect" && perfectImg
        ? perfectImg
        : result
          ? (result.previews[view as Exclude<View, "photo" | "perfect">] ?? result.previews.final)
          : photoUrl;

  return (
    <>
      {splash && <Splash />}

      <header className="border-b border-sand bg-white">
        <div className="mx-auto flex w-full max-w-[90rem] items-center gap-4 px-4 py-3 sm:px-8 sm:py-4">
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-medium tracking-tight sm:text-2xl">
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
                      onClick={() => setView(v.key)}
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
              <div className="relative flex min-h-72 items-center justify-center overflow-hidden rounded-2xl border border-line bg-gray-50">
                {shown && (
                  // eslint-disable-next-line @next/next/no-img-element -- previews are data URLs from the API
                  <img src={shown} alt={VIEWS.find((v) => v.key === view)?.label} className="max-h-[70vh] w-full object-contain" />
                )}
                {(busy === "update" || busy === "perfect") && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-white/80 backdrop-blur-[1px]">
                    <Spinner />
                    <p className="font-semibold">
                      {busy === "perfect" ? "Making the border perfect…" : "Updating…"} {seconds} s
                    </p>
                    {busy === "perfect" && <p className="text-sm text-muted">This takes about 30–60 seconds.</p>}
                  </div>
                )}
              </div>
              <Summary result={result} />
              {perfectReady && (
                <div className="flex flex-col items-start gap-3 rounded-2xl border border-brand/40 bg-mint-soft p-4 sm:flex-row sm:items-center">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-btn text-white">
                    <Sparkles className="h-5 w-5" aria-hidden />
                  </span>
                  <div className="flex flex-1 flex-col gap-2">
                    <p className="font-semibold">Make the border perfect</p>
                    <p className="text-sm text-muted">
                      AI redraws your design as clean line art with smooth curves, keeping the same design. Takes about 30–60
                      seconds. The result appears as “Perfect border” next to Final result.
                    </p>
                    <fieldset className="flex flex-wrap items-center gap-2" disabled={!!busy}>
                      <legend className="sr-only">My picture is</legend>
                      <span className="text-sm font-semibold">My picture is:</span>
                      {(
                        [
                          ["sketch", "Sketch", "uses your original photo"],
                          ["color", "Coloured design", "uses the scanned image"],
                        ] as const
                      ).map(([value, label, hint]) => (
                        <label
                          key={value}
                          title={hint}
                          className={`relative flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition ${
                            perfectSource === value ? "border-brand bg-white font-semibold" : "border-line bg-white/60 hover:bg-white"
                          }`}
                        >
                          <input
                            type="radio"
                            name="perfect-source"
                            checked={perfectSource === value}
                            onChange={() => setPerfectSource(value)}
                            className="sr-only"
                          />
                          <span
                            className={`flex h-4 w-4 items-center justify-center rounded-full border-2 ${perfectSource === value ? "border-btn" : "border-gray-300"}`}
                            aria-hidden
                          >
                            {perfectSource === value && <span className="h-2 w-2 rounded-full bg-btn" />}
                          </span>
                          {label}
                          <span className="text-xs font-normal text-muted">({hint})</span>
                        </label>
                      ))}
                    </fieldset>
                  </div>
                  <Button onClick={runPerfect} disabled={!!busy}>
                    <Sparkles className="h-5 w-5" aria-hidden /> {perfectImg ? "Make it again" : "Make border perfect"}
                  </Button>
                </div>
              )}
            </Card>
          )}

          {/* Step 3: download */}
          {result && busy !== "upload" && (
            <Card>
              <CardTitle step="Step 3" title="Download" />
              <a
                href={downloadUrl(result.id, "zip")}
                className={`inline-flex min-h-14 items-center justify-center gap-2 rounded-xl bg-btn px-6 text-lg font-semibold text-white shadow-sm hover:bg-btn-hover ${busy ? "pointer-events-none opacity-50" : ""}`}
              >
                <Download className="h-5 w-5" aria-hidden /> Download all files (ZIP)
              </a>
              {perfectImg && (
                <a
                  href={downloadUrl(result.id, "perfect")}
                  className={`flex items-center gap-3 rounded-xl border border-brand bg-mint-soft px-4 py-3 transition hover:bg-mint/40 ${busy ? "pointer-events-none opacity-50" : ""}`}
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-btn text-white">
                    <Sparkles className="h-4 w-4" aria-hidden />
                  </span>
                  <span className="flex flex-col">
                    <span className="font-semibold">Perfect border (PNG)</span>
                    <span className="text-sm text-muted">The AI-smoothed version. Also included in the ZIP.</span>
                  </span>
                </a>
              )}
              {chosen.length > 0 && (
                <>
                  <p className="text-sm text-muted">Or download one file at a time:</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {chosen.map((f) => (
                      <a
                        key={f.fmt}
                        href={downloadUrl(result.id, f.fmt)}
                        className={`flex items-center gap-3 rounded-xl border border-line bg-white px-4 py-3 transition hover:bg-gray-50 ${busy ? "pointer-events-none opacity-50" : ""}`}
                      >
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-mint-soft text-btn">
                          <Download className="h-4 w-4" aria-hidden />
                        </span>
                        <span className="flex flex-col">
                          <span className="font-semibold">{f.label}</span>
                          <span className="text-sm text-muted">{f.hint}</span>
                        </span>
                      </a>
                    ))}
                  </div>
                  {chosen.length > 1 && chosen.length < ready.length && (
                    <Button kind="outline" onClick={downloadChosen} disabled={!!busy} className="self-start">
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

function Splash() {
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 bg-white" role="status" aria-label="Loading">
      <div className="splash-pop flex flex-col items-center gap-3 text-center">
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
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
