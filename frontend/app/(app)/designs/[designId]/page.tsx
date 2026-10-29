"use client";

import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import { currentOf, rawOf } from "@/components/design-card";
import { DownloadMenu } from "@/components/download-menu";
import { ImageCompare } from "@/components/image-compare";
import { Button, Card, ErrorBox, Skeleton, buttonVariants } from "@/components/ui/primitives";
import { errorText } from "@/lib/api/client";
import { designsApi } from "@/lib/api/data";
import type { DesignVersion } from "@/lib/api/types";
import { useDesign, useDesignChats, useParty, useRefreshAll } from "@/lib/queries";
import { cn, longDate, shortDate, sizeLabel } from "@/lib/utils";

/** Screen 4: design detail with the linked chain raw → scan → AI → outline v1 → v2. */
export default function DesignPage({ params }: { params: Promise<{ designId: string }> }) {
  const { designId } = use(params);
  const design = useDesign(designId);
  const party = useParty(design.data?.party_id);
  const chats = useDesignChats(designId);
  const session = useQuery({ queryKey: ["session", designId], queryFn: () => designsApi.getSession(designId) });
  const [picked, setPicked] = useState<string | null>(null);
  const refresh = useRefreshAll();

  if (design.isLoading) return <div className="p-6"><Skeleton className="h-80" /></div>;
  if (design.error) return <div className="p-6"><ErrorBox error={design.error} /></div>;
  const d = design.data!;
  const raw = rawOf(d);
  const cur = currentOf(d);
  const shown = d.versions.find((v) => v.id === picked) ?? cur;
  const versionOf = (id: string | null) => d.versions.find((v) => v.id === id);

  async function deleteShown() {
    if (!shown || !window.confirm(`Delete "${shown.label}"? The image and its saved layers are removed. This cannot be undone.`)) return;
    try {
      await designsApi.removeVersion(d.id, shown.id);
      setPicked(null);
      toast.success(`${shown.label} deleted.`);
      refresh();
    } catch (e) {
      toast.error(errorText(e));
    }
  }

  return (
    <div>
      <PageHeader
        crumbs={[
          { label: "Parties", href: "/parties" },
          ...(party.data ? [{ label: party.data.name, href: `/parties/${party.data.id}` }] : []),
          { label: d.name },
        ]}
        actions={
          <>
            <Link href={`/workspace/${d.id}`} className={buttonVariants({ variant: "primary" })}>
              Open in workspace
            </Link>
            <DownloadMenu
              sid={session.data ?? null}
              designId={d.id}
              layersVersionId={shown?.layer_count ? shown.id : null}
              fallbackImage={cur?.image_url}
              fallbackName={d.name}
            />
          </>
        }
      />

      <div className="space-y-6 p-4 sm:p-6">
        <Card className="p-5">
          <h2 className="font-semibold">Linked images</h2>
          <p className="text-sm text-muted">Every step is saved and linked to the raw image it came from.</p>
          {d.versions.length === 0 ? (
            <p className="mt-4 text-sm text-muted">No images yet. Open the workspace and upload a raw image.</p>
          ) : (
            <div className="mt-4 flex items-start gap-2 overflow-x-auto pb-2">
              {d.versions.map((v, i) => (
                <div key={v.id} className="flex shrink-0 items-start gap-2">
                  {i > 0 && <ArrowRight className="mt-12 h-4 w-4 shrink-0 text-muted" />}
                  <ChainStep v={v} current={v.id === d.current_version_id} selected={v.id === shown?.id} onClick={() => setPicked(v.id)} />
                </div>
              ))}
            </div>
          )}
        </Card>

        <div className="grid gap-6 xl:grid-cols-[1fr_360px] [&>*]:min-w-0">
          <Card className="p-5">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-semibold">Raw vs {shown?.label ?? "outline"}</h2>
              <div className="flex items-center gap-3">
                <p className="text-sm text-muted">
                  {[
                    sizeLabel(shown?.width_mm, shown?.height_mm),
                    shown?.dpi && `${shown.dpi} DPI`,
                    shown?.closed_boxes != null && `${shown.closed_boxes} closed boxes`,
                    shown?.layer_count && `${shown.layer_count} layers saved`,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                {shown && (
                  <Button size="sm" variant="danger" onClick={deleteShown}>
                    Delete this image
                  </Button>
                )}
              </div>
            </div>
            {raw && shown && shown.id !== raw.id ? (
              <ImageCompare before={raw.image_url} after={shown.image_url} beforeLabel="Raw" afterLabel={shown.label} className="aspect-[4/3]" />
            ) : raw ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={raw.image_url} alt="Raw" className="aspect-[4/3] w-full rounded-xl border border-line bg-white object-contain" />
            ) : (
              <p className="text-sm text-muted">No raw image.</p>
            )}
          </Card>

          <div className="space-y-6">
            <Card className="p-5">
              <h2 className="mb-3 font-semibold">Chats for this design</h2>
              <div className="space-y-4">
                {chats.isLoading && [0, 1].map((i) => <Skeleton key={i} className="h-12" />)}
                {chats.data?.map((c) => {
                  const first = c.messages.find((m) => m.role === "user");
                  return (
                    <Link key={c.id} href={`/chats?chat=${c.id}`} className="block rounded-lg p-2 -m-2 hover:bg-canvas">
                      <div className="flex items-baseline justify-between gap-2">
                        <p className="font-medium">{c.title}</p>
                        <span className="text-xs text-muted">{shortDate(c.created_at)}</span>
                      </div>
                      {first && <p className="mt-0.5 text-sm text-muted">{first.content}</p>}
                      <p className="mt-0.5 text-xs text-muted/80">{c.result_label}</p>
                    </Link>
                  );
                })}
                {chats.data?.length === 0 && <p className="text-sm text-muted">No chats yet.</p>}
              </div>
              <Link href={`/workspace/${d.id}`} className={cn(buttonVariants({ variant: "soft", size: "sm" }), "mt-4")}>
                Continue chat →
              </Link>
            </Card>

            <Card className="p-5">
              <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
                <dt className="text-muted">Party</dt>
                <dd className="text-right">{party.data?.name ?? "No party"}</dd>
                <dt className="text-muted">Created</dt>
                <dd className="text-right">{longDate(d.created_at)}</dd>
                <dt className="text-muted">AI cost so far</dt>
                <dd className="text-right">{d.credits_used} credits</dd>
                <dt className="text-muted">Last export</dt>
                <dd className="text-right">{d.last_exports.length ? d.last_exports.map((f) => f.toUpperCase()).join(", ") : "None yet"}</dd>
                {shown?.chat_message_id && (
                  <>
                    <dt className="text-muted">Made by</dt>
                    <dd className="text-right">
                      {chats.data?.find((c) => c.messages.some((m) => m.id === shown.chat_message_id))?.title ?? "A chat"}
                    </dd>
                  </>
                )}
                {shown?.parent_id && (
                  <>
                    <dt className="text-muted">Made from</dt>
                    <dd className="text-right">{versionOf(shown.parent_id)?.label}</dd>
                  </>
                )}
              </dl>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChainStep({ v, current, selected, onClick }: { v: DesignVersion; current: boolean; selected: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-36 text-left">
      <div
        className={cn(
          "aspect-[4/3] overflow-hidden rounded-lg border-2 bg-white",
          selected ? "border-accent" : "border-line hover:border-accent/40",
        )}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={v.image_url} alt={v.label} className="h-full w-full object-contain" />
      </div>
      <p className="mt-1.5 text-sm font-medium">{v.label}</p>
      <p className="truncate text-xs text-muted">{[v.note, current && !v.note?.includes("current") && "current"].filter(Boolean).join(" · ") || " "}</p>
    </button>
  );
}
