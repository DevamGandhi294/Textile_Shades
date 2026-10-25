"use client";

// Small shadcn-style building blocks in the app's light grey + indigo look.

import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as DropdownPrimitive from "@radix-ui/react-dropdown-menu";
import * as SliderPrimitive from "@radix-ui/react-slider";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2, X } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

// ------------------------------------------------------------------ button

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
  {
    variants: {
      variant: {
        primary: "bg-accent text-white hover:bg-accent-ink",
        secondary: "border border-line bg-surface text-ink hover:bg-canvas",
        ghost: "text-ink hover:bg-canvas",
        soft: "bg-accent-soft text-accent-ink hover:bg-[#e2e5ff]",
        danger: "border border-line bg-surface text-danger hover:bg-red-50",
      },
      size: { sm: "h-8 px-3", md: "h-9 px-4", lg: "h-11 px-5 text-[15px]", icon: "h-8 w-8" },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, children, disabled, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} disabled={disabled || loading} {...props}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  ),
);
Button.displayName = "Button";

export { buttonVariants };

// ------------------------------------------------------------------ inputs

const field =
  "w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink placeholder:text-muted/70 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15 disabled:opacity-60";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn(field, "h-9", className)} {...props} />,
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => <textarea ref={ref} className={cn(field, "py-2 leading-relaxed", className)} {...props} />,
);
Textarea.displayName = "Textarea";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...props }, ref) => <select ref={ref} className={cn(field, "h-9 pr-8", className)} {...props} />,
);
Select.displayName = "Select";

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("mb-1.5 block text-[13px] font-medium text-ink", className)} {...props} />;
}

export function Field({
  label,
  error,
  hint,
  children,
  className,
  htmlFor,
}: {
  label: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
  htmlFor?: string;
}) {
  return (
    <div className={className}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {error ? <p className="mt-1 text-xs text-danger">{error}</p> : hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

// ------------------------------------------------------------------ surfaces

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-[var(--radius-card)] border border-line bg-surface", className)} {...props} />;
}

export function Badge({
  className,
  tone = "neutral",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: "neutral" | "accent" | "ok" | "warn" }) {
  const tones = {
    neutral: "bg-canvas text-muted",
    accent: "bg-accent-soft text-accent-ink",
    ok: "bg-green-50 text-ok",
    warn: "bg-amber-50 text-warn",
  };
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", tones[tone], className)}
      {...props}
    />
  );
}

/** Marks a control whose backend endpoint does not exist yet. */
export function PendingTag({ className }: { className?: string }) {
  return (
    <span
      title="This feature still needs backend work. For now it only runs on demo data."
      className={cn("rounded-full bg-amber-50 px-1.5 py-px text-[10px] font-medium text-warn", className)}
    >
      Needs backend
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-line/60", className)} />;
}

export function Empty({ title, children, action }: { title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-[var(--radius-card)] border border-dashed border-line bg-surface px-6 py-12 text-center">
      <p className="font-medium">{title}</p>
      {children && <p className="mt-1 max-w-sm text-sm text-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-danger">
      {error instanceof Error ? error.message : "Something went wrong."}
      {onRetry && (
        <button className="ml-2 font-medium underline" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ slider, switch, segmented

export function Slider({
  value,
  onChange,
  min,
  max,
  step,
  className,
  disabled,
  "aria-label": ariaLabel,
}: {
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
  className?: string;
  disabled?: boolean;
  "aria-label"?: string;
}) {
  return (
    <SliderPrimitive.Root
      className={cn("relative flex h-5 w-full touch-none select-none items-center", disabled && "opacity-50", className)}
      value={[value]}
      min={min}
      max={max}
      step={step}
      disabled={disabled}
      onValueChange={(v) => onChange(v[0]!)}
    >
      <SliderPrimitive.Track className="relative h-1.5 grow rounded-full bg-line">
        <SliderPrimitive.Range className="absolute h-full rounded-full bg-accent" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb
        aria-label={ariaLabel}
        className="block h-4 w-4 rounded-full border-2 border-accent bg-white shadow focus-visible:outline-2 focus-visible:outline-accent"
      />
    </SliderPrimitive.Root>
  );
}

export function Switch({
  checked,
  onChange,
  disabled,
  "aria-label": ariaLabel,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  "aria-label"?: string;
}) {
  return (
    <SwitchPrimitive.Root
      checked={checked}
      onCheckedChange={onChange}
      disabled={disabled}
      aria-label={ariaLabel}
      className="relative h-5 w-9 shrink-0 rounded-full bg-line transition-colors data-[state=checked]:bg-accent disabled:opacity-50"
    >
      <SwitchPrimitive.Thumb className="block h-4 w-4 translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[18px]" />
    </SwitchPrimitive.Root>
  );
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: React.ReactNode }[];
  className?: string;
}) {
  return (
    <div className={cn("inline-flex rounded-lg border border-line bg-canvas p-0.5", className)} role="radiogroup">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "flex-1 rounded-md px-3 py-1 text-[13px] font-medium text-muted transition-colors",
            value === o.value && "bg-surface text-ink shadow-sm",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ tabs

export const Tabs = TabsPrimitive.Root;

export function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("flex gap-1 overflow-x-auto border-b border-line", className)} {...props} />;
}

export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "-mb-px whitespace-nowrap border-b-2 border-transparent px-3 py-2 text-sm font-medium text-muted transition-colors hover:text-ink data-[state=active]:border-accent data-[state=active]:text-ink",
        className,
      )}
      {...props}
    />
  );
}

export const TabsContent = TabsPrimitive.Content;

// ------------------------------------------------------------------ dialog

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/30" />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 max-h-[92vh] w-[calc(100vw-32px)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl bg-surface p-6 shadow-xl focus:outline-none",
          className,
        )}
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <DialogPrimitive.Title className="text-lg font-semibold">{title}</DialogPrimitive.Title>
            {description ? (
              <DialogPrimitive.Description className="mt-0.5 text-sm text-muted">{description}</DialogPrimitive.Description>
            ) : (
              <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
            )}
          </div>
          <DialogPrimitive.Close className="rounded-md p-1 text-muted hover:bg-canvas" aria-label="Close">
            <X className="h-5 w-5" />
          </DialogPrimitive.Close>
        </div>
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

// ------------------------------------------------------------------ dropdown

export const Dropdown = DropdownPrimitive.Root;
export const DropdownTrigger = DropdownPrimitive.Trigger;

export function DropdownContent({ className, ...props }: React.ComponentProps<typeof DropdownPrimitive.Content>) {
  return (
    <DropdownPrimitive.Portal>
      <DropdownPrimitive.Content
        sideOffset={6}
        align="end"
        className={cn("z-50 min-w-52 rounded-xl border border-line bg-surface p-1 shadow-lg", className)}
        {...props}
      />
    </DropdownPrimitive.Portal>
  );
}

export function DropdownItem({ className, ...props }: React.ComponentProps<typeof DropdownPrimitive.Item>) {
  return (
    <DropdownPrimitive.Item
      className={cn(
        "flex cursor-pointer items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm outline-none data-[disabled]:cursor-default data-[disabled]:opacity-50 data-[highlighted]:bg-canvas",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownLabel({ className, ...props }: React.ComponentProps<typeof DropdownPrimitive.Label>) {
  return <DropdownPrimitive.Label className={cn("px-3 pb-1 pt-2 text-xs font-medium text-muted", className)} {...props} />;
}

export function DropdownSeparator() {
  return <DropdownPrimitive.Separator className="my-1 h-px bg-line" />;
}
