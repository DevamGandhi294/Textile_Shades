"use client";

import { useEffect, useRef } from "react";
import { ChevronDown, RotateCcw, X } from "lucide-react";

// ------------------------------------------------------------------ sidebar controls (dark background)

/** Bordered box that groups a few controls, like the panels in the Python app. */
export function Group({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-col gap-4 rounded-lg border border-white/15 bg-white/5 p-3">{children}</div>;
}

/** Section that opens and closes ("2 · Clean the lines"). */
export function Accordion({ title, open, children }: { title: string; open?: boolean; children: React.ReactNode }) {
  return (
    <details open={open} className="group rounded-lg border border-white/15 bg-white/5">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2.5 font-semibold text-white [&::-webkit-details-marker]:hidden">
        {title}
        <ChevronDown className="h-5 w-5 shrink-0 transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <div className="flex flex-col gap-4 border-t border-white/15 p-3">{children}</div>
    </details>
  );
}

function Label({ label, info }: { label: string; info?: string }) {
  return (
    <>
      <span className="font-semibold text-white">{label}</span>
      {info && <span className="text-sm leading-snug text-white/75">{info}</span>}
    </>
  );
}

/** One choice out of a few, shown as round radio buttons. */
export function Radio<T extends string | number>({
  label,
  info,
  options,
  value,
  onChange,
  disabled,
}: {
  label: string;
  info?: string;
  options: { label: string; value: T }[];
  value: T;
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset className="flex flex-col gap-1" disabled={disabled}>
      <legend className="contents">
        <Label label={label} info={info} />
      </legend>
      <div className="mt-1.5 flex flex-wrap gap-2">
        {options.map((o) => {
          const on = o.value === value;
          return (
            <label
              key={String(o.value)}
              className={`relative flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium text-white transition has-disabled:cursor-not-allowed has-disabled:opacity-50 ${
                on ? "border-mint bg-white/15" : "border-white/20 hover:bg-white/10"
              }`}
            >
              <input type="radio" checked={on} onChange={() => onChange(o.value)} className="sr-only" />
              <span
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 ${on ? "border-mint" : "border-white/50"}`}
                aria-hidden
              >
                {on && <span className="h-2 w-2 rounded-full bg-mint" />}
              </span>
              {o.label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

/** Yes / no setting with a tick box. */
export function Checkbox({
  label,
  info,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  info?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="flex cursor-pointer gap-2.5 has-disabled:cursor-not-allowed has-disabled:opacity-50">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-5 w-5 shrink-0 cursor-pointer accent-mint"
      />
      <span className="flex flex-col">
        <Label label={label} info={info} />
      </span>
    </label>
  );
}

/**
 * Slider with a number box and a reset button. `onChange` while dragging or typing,
 * `onCommit` when done, so the server only works once per change.
 */
export function SliderRow({
  label,
  info,
  min,
  max,
  step,
  value,
  reset,
  onChange,
  onCommit,
  disabled,
}: {
  label: string;
  info?: string;
  min: number;
  max: number;
  step: number;
  value: number;
  reset: number;
  onChange: (v: number) => void;
  onCommit: (v?: number) => void;
  disabled?: boolean;
}) {
  const clamp = (v: number) => Math.min(max, Math.max(min, v));
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-start justify-between gap-3">
        <span className="flex flex-col">
          <Label label={label} info={info} />
        </span>
        <span className="flex shrink-0 overflow-hidden rounded-md border border-white/25">
          <input
            type="number"
            aria-label={label}
            min={min}
            max={max}
            step={step}
            value={value}
            disabled={disabled}
            onChange={(e) => onChange(Number(e.target.value))}
            onBlur={(e) => onCommit(clamp(Number(e.target.value) || 0))}
            onKeyDown={(e) => e.key === "Enter" && onCommit(clamp(Number(e.currentTarget.value) || 0))}
            className="h-9 w-16 bg-white/10 px-2 text-center text-sm text-white disabled:opacity-50"
          />
          <button
            type="button"
            onClick={() => onCommit(reset)}
            disabled={disabled}
            title="Reset"
            aria-label={`Reset ${label}`}
            className="flex h-9 w-9 items-center justify-center border-l border-white/25 text-white hover:bg-white/15 disabled:opacity-50"
          >
            <RotateCcw className="h-4 w-4" aria-hidden />
          </button>
        </span>
      </div>
      <div className="flex items-center gap-2 text-sm text-white/75">
        <span className="w-6 text-right">{min}</span>
        <input
          type="range"
          aria-label={label}
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value))}
          onPointerUp={() => onCommit()}
          onKeyUp={() => onCommit()}
          className="flex-1 accent-mint disabled:cursor-not-allowed disabled:opacity-50"
        />
        <span className="w-6">{max}</span>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ page controls (light background)

/** Popup window in the middle of the screen. */
export function Modal({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onClose?: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onClose?.();
      }}
      className="m-auto w-[min(32rem,calc(100%-2rem))] rounded-2xl border-4 border-brand bg-white p-0 text-ink shadow-2xl backdrop:bg-ink/60"
    >
      <div className="flex flex-col gap-4 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <h2 className="text-xl font-bold sm:text-2xl">{title}</h2>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="flex h-9 w-9 items-center justify-center rounded-full text-muted hover:bg-gray-100"
            >
              <X className="h-5 w-5" aria-hidden />
            </button>
          )}
        </div>
        {children}
      </div>
    </dialog>
  );
}

export function BigButton({
  children,
  onClick,
  disabled,
  kind = "main",
  className = "",
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  kind?: "main" | "light" | "go";
  className?: string;
}) {
  const look = {
    main: "bg-brand-dark text-white hover:bg-brand-darker",
    go: "bg-green-700 text-white hover:bg-green-800",
    light: "border-2 border-brand-dark bg-white text-brand-dark hover:bg-gray-100",
  }[kind];
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex min-h-13 items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-lg font-bold transition disabled:cursor-not-allowed disabled:opacity-50 ${look} ${className}`}
    >
      {children}
    </button>
  );
}

export function Spinner() {
  return <div className="h-12 w-12 animate-spin rounded-full border-[5px] border-sand border-t-brand-dark" aria-hidden />;
}
