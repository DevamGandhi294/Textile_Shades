"use client";

import { useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronsLeft,
  ChevronsRight,
  CircleQuestionMark,
  ClipboardPaste,
  Clock,
  Download,
  Lightbulb,
  Menu,
  Play,
  Settings as SettingsIcon,
  SlidersHorizontal,
  TriangleAlert,
  Upload,
} from "lucide-react";
import SettingsPanel from "@/components/SettingsPanel";
import { BigButton, Modal, Spinner } from "@/components/controls";
import { ApiError, createSession, downloadUrl, getHealth, updateSession, type Result, type Settings } from "@/lib/api";
import { ALL_FORMATS, DEFAULTS, FORMATS, isDefault } from "@/lib/settings";

const VIEWS = [
  { key: "photo", label: "Your photo" },
  { key: "scan", label: "Scanned" },
  { key: "clean", label: "Cleaned" },
  { key: "final", label: "Final result" },
  { key: "check", label: "Gap check" },
] as const;
type View = (typeof VIEWS)[number]["key"];

const WIDTH_KEY = "sketch-cleaner-sidebar-width";
const SIDE_DEFAULT = 320;
const SIDE_MIN = 260;
const SIDE_MAX = 560;
const clampSide = (w: number) => Math.round(Math.min(SIDE_MAX, Math.max(SIDE_MIN, w)));

export default function Home() {
  const [splash, setSplash] = useState(true);
  const [welcome, setWelcome] = useState(false);
  const [server, setServer] = useState<"checking" | "ready" | "waking">("checking");
  const [aiReady, setAiReady] = useState(true);
  const [aiStatus, setAiStatus] = useState("");

  const [file, setFile] = useState<File | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [asking, setAsking] = useState(false); // "recommended or my own settings?" popup
  const [waiting, setWaiting] = useState(false); // photo chosen, not started yet
  const [result, setResult] = useState<Result | null>(null);
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [autoCrop, setAutoCrop] = useState(true);
  const [formats, setFormats] = useState<string[]>(ALL_FORMATS);
  const [busy, setBusy] = useState<"" | "upload" | "update">("");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const [view, setView] = useState<View>("final");
  const [panelOpen, setPanelOpen] = useState(false); // settings drawer on phones
  const [collapsed, setCollapsed] = useState(false); // settings sidebar folded to a thin strip (big screens)
  const [sideWidth, setSideWidth] = useState(SIDE_DEFAULT); // dragged by the handle on its right edge
  const [resizing, setResizing] = useState(false);
  const [dragging, setDragging] = useState(false);

  const latest = useRef(settings); // newest settings, also while a slider is moving
  const sent = useRef(""); // settings the server last processed, to skip repeat calls
  const pickRef = useRef<HTMLInputElement>(null);

  // Splash screen, then every time the site opens: recommended or own settings?
  useEffect(() => {
    const t = setTimeout(() => {
      setSplash(false);
      setWelcome(true);
      try {
        const w = Number(localStorage.getItem(WIDTH_KEY));
        if (w) setSideWidth(clampSide(w));
      } catch {}
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

  // Welcome popup answers: start with the recommended settings, or open the settings first.
  function welcomeRecommended() {
    setWelcome(false);
    edit(DEFAULTS);
  }

  function welcomeOwn() {
    setWelcome(false);
    openSettings();
  }

  // ------------------------------------------------------------------ photo and processing

  function choose(f: File) {
    if (busy) return;
    setFile(f);
    setPhotoUrl(URL.createObjectURL(f));
    setResult(null);
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
    setPanelOpen(false);
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
    latest.current = DEFAULTS;
    setSettings(DEFAULTS);
    start(DEFAULTS);
  }

  function chooseFirst() {
    setAsking(false);
    setPanelOpen(true);
    setCollapsed(false);
  }

  function resizeSide(w: number) {
    const next = clampSide(w);
    setSideWidth(next);
    try {
      localStorage.setItem(WIDTH_KEY, String(next));
    } catch {}
  }

  function openSettings() {
    setPanelOpen(true);
    setCollapsed(false);
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

  function startOver() {
    setFile(null);
    setPhotoUrl(null);
    setResult(null);
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

  const shownViews = VIEWS.filter((v) => v.key !== "check" || result?.previews.check);
  const shown = view === "photo" ? photoUrl : result ? (result.previews[view] ?? result.previews.final) : photoUrl;

  return (
    <>
      {splash && <Splash />}

      <div className="flex min-h-screen">
        {/* Settings sidebar: left side, folds to a thin strip on big screens, slides in on phones */}
        {panelOpen && <div className="fixed inset-0 z-30 bg-ink/50 lg:hidden" onClick={() => setPanelOpen(false)} aria-hidden />}
        <aside
          aria-label="Settings"
          style={{ "--side-w": `${sideWidth}px` } as React.CSSProperties}
          className={`fixed inset-y-0 left-0 z-40 flex w-[min(21rem,100%)] shrink-0 flex-col bg-side text-white shadow-2xl duration-200 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0 lg:shadow-none ${
            resizing ? "transition-none select-none" : "transition-[transform,width]"
          } ${panelOpen ? "translate-x-0" : "-translate-x-full"} ${collapsed ? "lg:w-16" : "lg:w-(--side-w)"}`}
        >
          {/* drag this edge to make the sidebar wider or narrower; double-click to reset */}
          {!collapsed && (
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Drag to change the settings width"
              aria-valuemin={SIDE_MIN}
              aria-valuemax={SIDE_MAX}
              aria-valuenow={sideWidth}
              tabIndex={0}
              title="Drag to make wider or narrower · double-click to reset"
              onPointerDown={(e) => {
                e.preventDefault();
                e.currentTarget.setPointerCapture(e.pointerId);
                setResizing(true);
              }}
              onPointerMove={(e) => resizing && setSideWidth(clampSide(e.clientX))}
              onPointerUp={(e) => {
                e.currentTarget.releasePointerCapture(e.pointerId);
                setResizing(false);
                resizeSide(e.clientX);
              }}
              onDoubleClick={() => resizeSide(SIDE_DEFAULT)}
              onKeyDown={(e) => {
                if (e.key === "ArrowRight") resizeSide(sideWidth + 20);
                if (e.key === "ArrowLeft") resizeSide(sideWidth - 20);
              }}
              className={`group absolute top-0 -right-1.5 z-10 hidden h-full w-3 cursor-col-resize lg:block`}
            >
              <span
                className={`mx-auto block h-full w-1 transition-colors ${resizing ? "bg-mint" : "bg-transparent group-hover:bg-mint/70 group-focus-visible:bg-mint"}`}
              />
            </div>
          )}
          <div className={`flex items-center gap-3 border-b border-white/15 px-4 py-4 ${collapsed ? "lg:justify-center lg:px-2" : ""}`}>
            <h2 className={`flex flex-1 items-center gap-3 text-xl font-bold ${collapsed ? "lg:hidden" : ""}`}>
              <SlidersHorizontal className="h-6 w-6 shrink-0 text-mint" aria-hidden />
              Settings
            </h2>
            <button
              type="button"
              onClick={() => setCollapsed(!collapsed)}
              aria-label={collapsed ? "Open settings" : "Close settings"}
              title={collapsed ? "Open settings" : "Close settings"}
              className="hidden h-10 w-10 items-center justify-center rounded-lg text-white hover:bg-white/10 lg:inline-flex"
            >
              {collapsed ? <ChevronsRight className="h-5 w-5" aria-hidden /> : <ChevronsLeft className="h-5 w-5" aria-hidden />}
            </button>
            <button
              type="button"
              onClick={() => setPanelOpen(false)}
              className="min-h-10 rounded-lg bg-mint px-4 font-bold text-ink lg:hidden"
            >
              Done
            </button>
          </div>

          {/* folded: only icons */}
          <div className={`flex-col items-center gap-2 py-4 ${collapsed ? "hidden lg:flex" : "hidden"}`}>
            <button
              type="button"
              onClick={() => setCollapsed(false)}
              title="Open settings"
              aria-label="Open settings"
              className="flex h-12 w-12 items-center justify-center rounded-lg bg-white/10 hover:bg-white/20"
            >
              <SettingsIcon className="h-6 w-6" aria-hidden />
            </button>
            <span className="mt-2 text-xs font-bold tracking-widest text-mint uppercase [writing-mode:vertical-rl]">Settings</span>
          </div>

          {/* open: all settings */}
          <div className={`relative flex-1 overflow-y-auto px-4 pt-3 pb-6 ${collapsed ? "lg:hidden" : ""}`}>
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

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="border-b-4 border-brand bg-sand">
            <div className="mx-auto flex w-full max-w-5xl items-center gap-3 px-4 py-3 sm:px-6">
              <button
                type="button"
                onClick={openSettings}
                className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-side px-3 font-bold text-white lg:hidden"
              >
                <Menu className="h-5 w-5" aria-hidden /> Settings
              </button>
              <div className="flex-1">
                <h1 className="text-xl font-bold leading-tight sm:text-2xl">TextileBorder OutlineTool</h1>
                <p className="hidden text-sm text-muted sm:block">
                  Upload a photo or scan of a sketch. It becomes a clean scan automatically; adjust only if needed, then download.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setWelcome(true)}
                className="inline-flex min-h-11 items-center gap-2 rounded-lg border-2 border-brand-dark bg-white px-4 font-bold text-brand-dark hover:bg-gray-100"
              >
                <CircleQuestionMark className="h-5 w-5" aria-hidden /> Help
              </button>
            </div>
          </header>

          {server === "waking" && (
            <p className="flex items-center justify-center gap-2 bg-amber-100 px-4 py-2.5 text-center text-amber-950">
              <Clock className="h-5 w-5 shrink-0" aria-hidden />
              The service is starting up. The first time this can take about one minute. You can already choose your photo.
            </p>
          )}

          <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-5 px-4 py-5 sm:px-6">
            {/* Step 1 */}
            <Card>
              <StepTitle n={1}>Choose your sketch photo</StepTitle>
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
                className={`flex min-h-56 cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed p-6 text-center transition hover:bg-gray-100 ${
                  dragging ? "border-brand-dark bg-gray-100" : "border-brand bg-white"
                } ${busy ? "pointer-events-none opacity-50" : ""}`}
              >
                <Upload className="mb-2 h-10 w-10 text-brand-dark" aria-hidden />
                <span className="text-xl font-bold">Drop image here</span>
                <span className="text-muted">- or -</span>
                <span className="text-xl font-bold text-brand-darker">Click to upload</span>
              </div>
              <div className="flex flex-wrap items-center justify-center gap-3">
                <BigButton onClick={() => pickRef.current?.click()} disabled={!!busy} className="flex-1 sm:flex-none">
                  <Upload className="h-5 w-5" aria-hidden /> Upload photo
                </BigButton>
                <BigButton onClick={pasteImage} disabled={!!busy} kind="light" className="flex-1 sm:flex-none">
                  <ClipboardPaste className="h-5 w-5" aria-hidden /> Paste from clipboard
                </BigButton>
              </div>
              <p className="text-center text-sm text-muted">You can also copy an image and press Ctrl + V on this page.</p>
              <p className="flex items-start gap-2">
                <Lightbulb className="mt-0.5 h-5 w-5 shrink-0 text-brand-dark" aria-hidden />
                Put the paper on a table in good light and take the photo from straight above.
              </p>
            </Card>

            {error && (
              <div role="alert" className="flex items-start gap-3 rounded-xl border-2 border-red-300 bg-red-50 px-4 py-3 text-lg text-red-900">
                <TriangleAlert className="mt-1 h-5 w-5 shrink-0" aria-hidden />
                {error}
              </div>
            )}

            {/* Photo chosen, waiting for the user to start */}
            {waiting && file && !busy && (
              <Card>
                <StepTitle n={2}>Your photo is ready</StepTitle>
                {photoUrl && (
                  // eslint-disable-next-line @next/next/no-img-element -- local photo preview
                  <img src={photoUrl} alt="Your photo" className="max-h-72 w-full rounded-lg bg-white object-contain" />
                )}
                <p>Check the settings on the left, then press Start.</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <BigButton kind="go" onClick={() => start()}>
                    <Play className="h-5 w-5" aria-hidden /> Start cleaning
                  </BigButton>
                  <BigButton kind="light" onClick={openSettings}>
                    <SettingsIcon className="h-5 w-5" aria-hidden /> Settings
                  </BigButton>
                </div>
              </Card>
            )}

            {busy === "upload" && (
              <Card>
                <div className="flex flex-col items-center gap-3 py-5 text-center">
                  <Spinner />
                  <p className="text-xl font-bold">Cleaning your sketch… {seconds} s</p>
                  <p className="text-muted">
                    This usually takes 20 to 40 seconds. Please keep this page open.
                    {server === "waking" && " The service is still starting, so the first time can take longer."}
                  </p>
                </div>
              </Card>
            )}

            {/* Step 2 */}
            {result && busy !== "upload" && (
              <Card>
                <StepTitle n={2}>Check the result</StepTitle>
                <div className="flex flex-wrap gap-2" role="tablist">
                  {shownViews.map((v) => (
                    <button
                      key={v.key}
                      type="button"
                      role="tab"
                      aria-selected={view === v.key}
                      onClick={() => setView(v.key)}
                      className={`min-h-11 flex-1 rounded-lg px-3 font-semibold whitespace-nowrap ${
                        view === v.key ? "bg-side text-white" : "bg-white text-ink hover:bg-gray-100"
                      }`}
                    >
                      {v.label}
                    </button>
                  ))}
                </div>
                {view === "check" && (
                  <p className="rounded-lg bg-white px-3 py-2 text-sm">
                    Every closed area has its own colour. <b className="text-green-800">Green</b> = gaps that were joined.{" "}
                    <b className="text-red-800">Red circle</b> = open line end, where colour fill could leak.
                  </p>
                )}
                <div className="relative flex min-h-64 items-center justify-center overflow-hidden rounded-lg bg-white">
                  {shown && (
                    // eslint-disable-next-line @next/next/no-img-element -- previews are data URLs from the API
                    <img src={shown} alt={VIEWS.find((v) => v.key === view)?.label} className="max-h-[70vh] w-full object-contain" />
                  )}
                  {busy === "update" && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-white/80">
                      <Spinner />
                      <p className="text-lg font-bold">Updating… {seconds} s</p>
                    </div>
                  )}
                </div>
                <Summary result={result} />
                <BigButton kind="light" onClick={openSettings} className="lg:hidden">
                  <SettingsIcon className="h-5 w-5" aria-hidden /> Change settings
                </BigButton>
              </Card>
            )}

            {/* Step 3 */}
            {result && busy !== "upload" && (
              <Card>
                <StepTitle n={3}>Download</StepTitle>
                <a
                  href={downloadUrl(result.id, "zip")}
                  className={`flex min-h-14 items-center justify-center gap-2 rounded-xl bg-green-700 px-5 text-xl font-bold text-white hover:bg-green-800 ${busy ? "pointer-events-none opacity-50" : ""}`}
                >
                  <Download className="h-6 w-6" aria-hidden /> Download all files (ZIP)
                </a>
                {chosen.length > 0 && (
                  <>
                    <p>Or download one file at a time:</p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {chosen.map((f) => (
                        <a
                          key={f.fmt}
                          href={downloadUrl(result.id, f.fmt)}
                          className={`flex flex-col rounded-lg border-2 border-white bg-white px-3 py-2 hover:border-brand-dark hover:bg-gray-100 ${busy ? "pointer-events-none opacity-50" : ""}`}
                        >
                          <span className="flex items-center gap-2 font-bold">
                            <Download className="h-4 w-4 shrink-0" aria-hidden /> {f.label}
                          </span>
                          <span className="text-sm text-muted">{f.hint}</span>
                        </a>
                      ))}
                    </div>
                    {chosen.length > 1 && chosen.length < ready.length && (
                      <BigButton kind="light" onClick={downloadChosen} disabled={!!busy}>
                        <Download className="h-5 w-5" aria-hidden /> Download my {chosen.length} chosen files
                      </BigButton>
                    )}
                  </>
                )}
                <p className="text-sm text-muted">
                  Choose which file types to show in Settings → Download settings → Formats.
                  {!bw && " Vector, CAD and print files need the black & white output."}
                </p>
                <button type="button" onClick={startOver} className="self-start font-bold text-brand-darker underline">
                  Start again with a new photo
                </button>
              </Card>
            )}
          </main>

        </div>
      </div>

      {/* When the site opens: how it works, then recommended or own settings */}
      <Modal open={welcome && !splash} title="Welcome" onClose={() => setWelcome(false)}>
        <p className="text-lg">Make a clean drawing from a photo in 3 easy steps:</p>
        <ol className="flex flex-col gap-2">
          {(
            [
              [Upload, "Upload or paste a photo of your sketch."],
              [SettingsIcon, "Use our recommended settings, or choose your own."],
              [Download, "Download your files for embroidery, printing or CAD."],
            ] as const
          ).map(([Icon, text], i) => (
            <li key={i} className="flex items-center gap-3 rounded-xl bg-mint px-3 py-2.5">
              <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-side font-bold text-white">{i + 1}</span>
              <Icon className="h-5 w-5 shrink-0 text-side" aria-hidden />
              <span>{text}</span>
            </li>
          ))}
        </ol>
        <p className="text-lg font-bold">Which settings do you want to use?</p>
        <button
          type="button"
          onClick={welcomeRecommended}
          className="flex flex-col rounded-xl bg-green-700 px-4 py-3 text-left text-white hover:bg-green-800"
        >
          <span className="flex items-center gap-2 text-xl font-bold">
            <Check className="h-5 w-5" aria-hidden /> Use recommended settings
          </span>
          <span className="text-white/90">Best for most sketches. You do not need to change anything.</span>
        </button>
        <button
          type="button"
          onClick={welcomeOwn}
          className="flex flex-col rounded-xl border-2 border-brand-dark bg-white px-4 py-3 text-left text-brand-darker hover:bg-gray-100"
        >
          <span className="flex items-center gap-2 text-xl font-bold">
            <SettingsIcon className="h-5 w-5" aria-hidden /> Choose my own settings
          </span>
          <span className="text-muted">Opens the settings on the left. Then upload your photo.</span>
        </button>
      </Modal>

      {/* Before any processing: recommended or own settings? */}
      <Modal open={asking} title="How should we clean your photo?" onClose={() => setAsking(false)}>
        {photoUrl && (
          // eslint-disable-next-line @next/next/no-img-element -- local photo preview
          <img src={photoUrl} alt="Your photo" className="max-h-44 w-full rounded-lg border-2 border-sand object-contain" />
        )}
        <button
          type="button"
          onClick={startWithRecommended}
          className="flex flex-col rounded-xl bg-green-700 px-4 py-3 text-left text-white hover:bg-green-800"
        >
          <span className="flex items-center gap-2 text-xl font-bold">
            <Check className="h-5 w-5" aria-hidden /> Use recommended settings
          </span>
          <span className="text-white/90">Best for most sketches. Starts now.</span>
        </button>
        {!isDefault(settings) && (
          <button
            type="button"
            onClick={() => start()}
            className="flex flex-col rounded-xl bg-brand-dark px-4 py-3 text-left text-white hover:bg-brand-darker"
          >
            <span className="flex items-center gap-2 text-xl font-bold">
              <Play className="h-5 w-5" aria-hidden /> Use my settings
            </span>
            <span className="text-white/90">The settings you chose before. Starts now.</span>
          </button>
        )}
        <button
          type="button"
          onClick={chooseFirst}
          className="flex flex-col rounded-xl border-2 border-brand-dark bg-white px-4 py-3 text-left text-brand-darker hover:bg-gray-100"
        >
          <span className="flex items-center gap-2 text-xl font-bold">
            <SettingsIcon className="h-5 w-5" aria-hidden /> Let me choose settings first
          </span>
          <span className="text-muted">Opens the settings. Press Start when you are ready.</span>
        </button>
      </Modal>
    </>
  );
}

function Splash() {
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 bg-white" role="status" aria-label="Loading">
      <div className="splash-pop flex flex-col items-center gap-4">
        <h1 className="text-3xl font-bold text-ink sm:text-4xl">Sketch Cleaner</h1>
        <p className="text-lg text-muted">Clean lines from your sketch photos</p>
      </div>
      <div className="h-2 w-52 overflow-hidden rounded-full bg-sand">
        <div className="splash-bar h-full w-1/3 rounded-full bg-brand" />
      </div>
    </div>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return <section className="flex flex-col gap-4 rounded-2xl bg-mint p-4 sm:p-5">{children}</section>;
}

function StepTitle({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <h2 className="flex items-center gap-3 text-xl font-bold">
      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-side text-lg text-white">{n}</span>
      {children}
    </h2>
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
          <li key={t} className="rounded-md bg-white px-2.5 py-1 font-medium">
            {t}
          </li>
        ))}
      </ul>
      {i.ai_note && <p className="text-sm text-amber-900">Note: {i.ai_note}</p>}
    </div>
  );
}
