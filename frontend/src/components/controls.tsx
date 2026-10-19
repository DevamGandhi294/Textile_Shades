"use client";

import { useEffect, useRef } from "react";
import { RotateCcw, X } from "lucide-react";

// ------------------------------------------------------------------ settings panel controls

/** A titled block of settings, separated from the next by a thin line. */
export function Section({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-5 border-b border-line py-5 first:pt-0 last:border-b-0">
      {title && <h3 className="text-xs font-bold tracking-widest text-brand uppercase">{title}</h3>}
      {children}
    </section>
  );
}

function Label({ label, info }: { label: string; info?: string }) {
  return (
    <>
      <span className="font-semibold text-ink">{label}</span>
      {info && <span className="text-sm leading-relaxed text-muted">{info}</span>}
    </>
  );
}

/** One choice out of a few, shown as full-width rows with a round marker. */
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
  options: { label: string; hint?: string; value: T }[];
  value: T;
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset className="flex flex-col gap-1" disabled={disabled}>
      <legend className="contents">
        <Label label={label} info={info} />
      </legend>
      <div className="mt-2 flex flex-col gap-2">
        {options.map((o) => {
          const on = o.value === value;
          return (
            <label
              key={String(o.value)}
              className={`relative flex cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 transition has-disabled:cursor-not-allowed has-disabled:opacity-50 ${
                on ? "border-brand bg-mint-soft" : "border-line bg-white hover:bg-gray-50"
              }`}
            >
              <input type="radio" checked={on} onChange={() => onChange(o.value)} className="sr-only" />
              <span
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 ${on ? "border-btn" : "border-gray-300"}`}
                aria-hidden
              >
                {on && <span className="h-2.5 w-2.5 rounded-full bg-btn" />}
              </span>
              <span>
                {o.label}
                {o.hint && <span className="ml-1 text-btn">{o.hint}</span>}
              </span>
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
    <label className="flex cursor-pointer gap-3 has-disabled:cursor-not-allowed has-disabled:opacity-50">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-5 w-5 shrink-0 cursor-pointer accent-btn"
      />
      <span className="flex flex-col gap-0.5">
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
        <span className="flex flex-col gap-0.5">
          <Label label={label} info={info} />
        </span>
        <span className="flex shrink-0 overflow-hidden rounded-lg border border-line">
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
            className="h-9 w-16 bg-white px-2 text-center text-sm disabled:opacity-50"
          />
          <button
            type="button"
            onClick={() => onCommit(reset)}
            disabled={disabled}
            title="Reset"
            aria-label={`Reset ${label}`}
            className="flex h-9 w-9 items-center justify-center border-l border-line text-muted hover:bg-gray-100 disabled:opacity-50"
          >
            <RotateCcw className="h-4 w-4" aria-hidden />
          </button>
        </span>
      </div>
      <div className="flex items-center gap-2 text-sm text-muted">
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
          className="flex-1 accent-btn disabled:cursor-not-allowed disabled:opacity-50"
        />
        <span className="w-6">{max}</span>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ page controls

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
      className="m-auto w-[min(32rem,calc(100%-2rem))] rounded-3xl border border-line bg-white p-0 text-ink shadow-2xl backdrop:bg-ink/40 backdrop:backdrop-blur-[2px]"
    >
      <div className="flex flex-col gap-4 p-6 sm:p-7">
        <div className="flex items-start justify-between gap-4">
          <h2 className="text-2xl font-semibold">{title}</h2>
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

export function Button({
  children,
  onClick,
  disabled,
  kind = "main",
  className = "",
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  kind?: "main" | "outline" | "ghost";
  className?: string;
}) {
  const look = {
    main: "bg-btn text-white shadow-sm hover:bg-btn-hover",
    outline: "border border-line bg-white text-btn-hover hover:bg-gray-100",
    ghost: "text-ink hover:bg-gray-100",
  }[kind];
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-5 font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${look} ${className}`}
    >
      {children}
    </button>
  );
}

/** Big choice in a popup: icon, title and one line of explanation. */
export function ChoiceCard({
  icon,
  title,
  text,
  onClick,
  primary,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
  onClick: () => void;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-start gap-4 rounded-2xl border px-4 py-3.5 text-left transition ${
        primary ? "border-brand bg-mint-soft hover:bg-mint/40" : "border-line bg-white hover:bg-gray-50"
      }`}
    >
      <span
        className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${primary ? "bg-btn text-white" : "bg-mint-soft text-btn"}`}
      >
        {icon}
      </span>
      <span className="flex flex-col">
        <span className="text-lg font-semibold">{title}</span>
        <span className="text-sm text-muted">{text}</span>
      </span>
    </button>
  );
}

export function Spinner() {
  return <div className="h-11 w-11 animate-spin rounded-full border-4 border-mint-soft border-t-btn" aria-hidden />;
}
