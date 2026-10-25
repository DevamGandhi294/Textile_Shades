"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Archive, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { partiesApi } from "@/lib/api/data";
import type { Party, PartyInput } from "@/lib/api/types";
import { useDesigns, useRefreshAll } from "@/lib/queries";
import { cn, initials, shortDate } from "@/lib/utils";
import {
  Button,
  Dialog,
  DialogContent,
  Field,
  Input,
  PendingTag,
  Select,
  Switch,
  Textarea,
} from "./ui/primitives";

const SOFTWARE = [
  { value: "wilcom", label: "Wilcom" },
  { value: "coreldraw", label: "CorelDRAW" },
  { value: "photoshop", label: "Photoshop" },
  { value: "illustrator", label: "Illustrator" },
  { value: "textronic", label: "Textronic" },
  { value: "emcad", label: "emCAD" },
  { value: "other", label: "Other" },
];
export const FORMATS = ["svg", "eps", "pdf", "dxf", "psd", "bmp", "tiff", "png"] as const;

export function softwareLabel(v: string | null) {
  return SOFTWARE.find((s) => s.value === v)?.label ?? v ?? "";
}

const schema = z.object({
  name: z.string().trim().min(1, "Please enter the party name.").max(80),
  contact_person: z.string().trim().max(80),
  phone: z
    .string()
    .trim()
    .refine((v) => v === "" || v.replace(/\D/g, "").length >= 10, "Enter a 10-digit number."),
  area: z.string().trim().max(80),
  gstin: z
    .string()
    .trim()
    .toUpperCase()
    .refine((v) => v === "" || /^[0-9]{2}[A-Z0-9]{13}$/.test(v), "A GSTIN has 15 letters and digits."),
  usual_motifs: z.string().trim().max(120),
  border_width: z.string().trim().max(40),
  line_thickness: z.enum(["", "thin", "medium", "bold"]),
  software: z.string(),
  default_formats: z.array(z.string()),
  ai_summary: z.string().trim(),
  ai_summary_auto: z.boolean(),
});
type FormValues = z.infer<typeof schema>;

const toForm = (p?: Party | null): FormValues => ({
  name: p?.name ?? "",
  contact_person: p?.contact_person ?? "",
  phone: p?.phone ?? "",
  area: p?.area ?? "",
  gstin: p?.gstin ?? "",
  usual_motifs: p?.usual_motifs ?? "",
  border_width: p?.border_width ?? "",
  line_thickness: p?.line_thickness ?? "",
  software: p?.software ?? "",
  default_formats: p?.default_formats ?? [],
  ai_summary: p?.ai_summary ?? "",
  ai_summary_auto: p?.ai_summary_auto ?? true,
});

const nullIfEmpty = (v: string) => (v.trim() === "" ? null : v.trim());

function toInput(v: FormValues): PartyInput {
  return {
    name: v.name,
    contact_person: nullIfEmpty(v.contact_person),
    phone: nullIfEmpty(v.phone),
    area: nullIfEmpty(v.area),
    gstin: nullIfEmpty(v.gstin),
    usual_motifs: nullIfEmpty(v.usual_motifs),
    border_width: nullIfEmpty(v.border_width),
    line_thickness: v.line_thickness === "" ? null : v.line_thickness,
    software: nullIfEmpty(v.software),
    default_formats: v.default_formats,
    ai_summary: nullIfEmpty(v.ai_summary),
    ai_summary_auto: v.ai_summary_auto,
  };
}

const words = (s: string) => s.trim().split(/\s+/).filter(Boolean).length;

/** Screen 5: Party card (popup). With no party it creates a new one. */
export function PartyDialog({
  party,
  open,
  onOpenChange,
  onSaved,
}: {
  party?: Party | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onSaved?: (p: Party) => void;
}) {
  const refresh = useRefreshAll();
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: toForm(party) });
  const { register, handleSubmit, formState, watch, setValue, reset } = form;
  const [refs, setRefs] = useState<string[]>(party?.reference_version_ids ?? []);
  const designs = useDesigns({ partyId: party?.id });

  useEffect(() => {
    if (open) {
      reset(toForm(party));
      setRefs(party?.reference_version_ids ?? []);
    }
  }, [open, party, reset]);

  const save = useMutation({
    mutationFn: async (v: FormValues) => {
      const input = toInput(v);
      const saved = party ? await partiesApi.update(party.id, input) : await partiesApi.create(input);
      if (party && refs.join() !== party.reference_version_ids.join()) await partiesApi.setReferences(party.id, refs);
      return saved;
    },
    onSuccess: (p) => {
      toast.success(party ? "Party saved." : "Party added.");
      refresh();
      onSaved?.(p);
      onOpenChange(false);
    },
    onError: (e) => toast.error(e.message),
  });

  const rebuild = useMutation({
    mutationFn: () => partiesApi.rebuildSummary(party!.id),
    onSuccess: (p) => {
      setValue("ai_summary", p.ai_summary ?? "", { shouldDirty: true });
      toast.success("Summary rebuilt from this party's chats.");
      refresh();
    },
    onError: (e) => toast.error(e.message),
  });

  const archive = useMutation({
    mutationFn: () => partiesApi.setArchived(party!.id, !party!.archived),
    onSuccess: () => {
      toast.success(party!.archived ? "Party restored." : "Party archived.");
      refresh();
      onOpenChange(false);
    },
    onError: (e) => toast.error(e.message),
  });

  const formats = watch("default_formats");
  const summary = watch("ai_summary");
  const auto = watch("ai_summary_auto");
  const outlines = (designs.data ?? []).flatMap((d) =>
    d.versions.filter((v) => v.kind === "outline" && v.id === d.current_version_id).map((v) => ({ v, d })),
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-4xl"
        title={party ? "Edit party" : "New party"}
        description={
          party ? (
            <span className="flex items-center gap-2">
              <span className="grid h-6 w-6 place-items-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent-ink">
                {initials(party.name)}
              </span>
              {party.name} · {party.design_count} designs · {party.chat_count} chats
            </span>
          ) : (
            "A party is one customer. Their designs, chats and preferences stay together."
          )
        }
      >
        <form onSubmit={handleSubmit((v) => save.mutate(v))} className="grid gap-8 md:grid-cols-2">
          <div className="space-y-4">
            <p className="text-xs font-semibold tracking-wide text-muted">DETAILS</p>
            <Field label="Party name" error={formState.errors.name?.message}>
              <Input {...register("name")} placeholder="Shree Textiles" autoFocus />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Contact person">
                <Input {...register("contact_person")} />
              </Field>
              <Field label="Phone / WhatsApp" error={formState.errors.phone?.message}>
                <Input {...register("phone")} inputMode="tel" placeholder="+91" />
              </Field>
              <Field label="Area">
                <Input {...register("area")} placeholder="Ring Road, Surat" />
              </Field>
              <Field label="GST (optional)" error={formState.errors.gstin?.message}>
                <Input {...register("gstin")} className="uppercase" />
              </Field>
            </div>

            <p className="pt-2 text-xs font-semibold tracking-wide text-muted">DESIGN PREFERENCES</p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Usual motifs">
                <Input {...register("usual_motifs")} placeholder="Paisley, peacock" />
              </Field>
              <Field label="Border width">
                <Input {...register("border_width")} placeholder="8–12 cm" />
              </Field>
              <Field label="Line thickness">
                <Select {...register("line_thickness")}>
                  <option value="">Not set</option>
                  <option value="thin">Thin</option>
                  <option value="medium">Medium</option>
                  <option value="bold">Bold</option>
                </Select>
              </Field>
              <Field label="Software they use">
                <Select {...register("software")}>
                  <option value="">Not set</option>
                  {SOFTWARE.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            <Field label="Files they usually want">
              <div className="flex flex-wrap gap-1.5">
                {FORMATS.map((f) => {
                  const on = formats.includes(f);
                  return (
                    <button
                      key={f}
                      type="button"
                      onClick={() =>
                        setValue("default_formats", on ? formats.filter((x) => x !== f) : [...formats, f], { shouldDirty: true })
                      }
                      className={cn(
                        "rounded-full border px-2.5 py-1 text-xs font-medium uppercase",
                        on ? "border-accent bg-accent-soft text-accent-ink" : "border-line text-muted hover:bg-canvas",
                      )}
                    >
                      {f}
                    </button>
                  );
                })}
              </div>
            </Field>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold tracking-wide text-muted">WHAT AI REMEMBERS</p>
              <Sparkles className="h-4 w-4 text-accent" />
            </div>
            <p className="text-sm text-muted">
              AI gets this short summary, not all {party?.chat_count ?? 0} chats and {party?.raw_count ?? 0} images. That keeps each
              request small and cheap.
            </p>
            <Field
              label="Party summary sent to AI"
              hint={`${words(summary)} of about 60 words${
                party?.ai_summary_updated ? ` · updated ${auto ? "automatically after each chat" : ""} ${shortDate(party.ai_summary_updated)}` : ""
              }`}
            >
              <Textarea {...register("ai_summary")} rows={5} placeholder="What this party usually wants, in about 60 words." />
            </Field>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                onClick={() => rebuild.mutate()}
                loading={rebuild.isPending}
                disabled={!party}
                title={party ? undefined : "Save the party first"}
              >
                <RefreshCw className="h-3.5 w-3.5" /> Rebuild from chats
              </Button>
              <PendingTag />
              </div>
              <label className="flex items-center gap-2 text-sm">
                Auto-update
                <Switch checked={auto} onChange={(v) => setValue("ai_summary_auto", v, { shouldDirty: true })} />
              </label>
            </div>

            <div className="pt-2">
              <p className="mb-1 text-[13px] font-medium">Favourite designs used as reference</p>
              <p className="mb-3 text-xs text-muted">Up to 4 images. Only these are sent, never the full library.</p>
              {!party ? (
                <p className="text-xs text-muted">Add designs to this party first.</p>
              ) : outlines.length === 0 ? (
                <p className="text-xs text-muted">No outlines yet for this party.</p>
              ) : (
                <div className="grid grid-cols-4 gap-2">
                  {outlines.slice(0, 12).map(({ v, d }) => {
                    const pos = refs.indexOf(v.id);
                    return (
                      <button
                        key={v.id}
                        type="button"
                        title={d.name}
                        onClick={() =>
                          setRefs((r) => (pos >= 0 ? r.filter((x) => x !== v.id) : r.length < 4 ? [...r, v.id] : r))
                        }
                        className={cn(
                          "relative aspect-square overflow-hidden rounded-lg border-2 bg-white",
                          pos >= 0 ? "border-accent" : "border-line opacity-70 hover:opacity-100",
                        )}
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={v.image_url} alt={d.name} className="h-full w-full object-contain" />
                        {pos >= 0 && (
                          <span className="absolute right-1 top-1 grid h-5 w-5 place-items-center rounded-full bg-accent text-[11px] font-semibold text-white">
                            {pos + 1}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4 md:col-span-2">
            {party ? (
              <Button type="button" variant="ghost" onClick={() => archive.mutate()} loading={archive.isPending}>
                <Archive className="h-4 w-4" /> {party.archived ? "Restore party" : "Archive party"}
              </Button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button type="button" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" loading={save.isPending}>
                Save party
              </Button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
