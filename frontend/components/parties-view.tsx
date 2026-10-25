"use client";

import { useMutation } from "@tanstack/react-query";
import { FileUp, Pencil, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { designsApi } from "@/lib/api/data";
import type { Party } from "@/lib/api/types";
import { demoImage } from "@/lib/mock/images";
import { useChats, useDesigns, useParties, useParty, useRefreshAll } from "@/lib/queries";
import { cn, fileToDataUrl, shortAgo } from "@/lib/utils";
import { ChatListItem } from "./chat-list";
import { DesignCard, Thumb, rawOf } from "./design-card";
import { NewDesignDialog } from "./new-design-dialog";
import { PartyDialog, softwareLabel } from "./party-dialog";
import {
  Badge,
  Button,
  Empty,
  ErrorBox,
  Input,
  PendingTag,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "./ui/primitives";

/** Screen 3: party list with search, and the selected party's profile. */
export function PartiesView({ partyId }: { partyId?: string }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const list = useParties({ q, archived: showArchived });
  const selectedId = partyId ?? list.data?.[0]?.id;

  return (
    <div className="flex min-h-[calc(100vh-48px)] flex-col lg:min-h-screen lg:flex-row">
      <section
        className={cn(
          "w-full shrink-0 border-b border-line bg-surface lg:w-80 lg:border-b-0 lg:border-r",
          partyId && "hidden lg:block",
        )}
      >
        <div className="flex items-center justify-between px-4 pb-3 pt-4">
          <h1 className="text-lg font-semibold">Parties</h1>
          <Button size="sm" variant="primary" onClick={() => setNewOpen(true)}>
            <Plus className="h-4 w-4" /> New party
          </Button>
        </div>
        <div className="px-4 pb-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search parties" className="pl-9" />
          </div>
        </div>
        <div className="max-h-[50vh] overflow-y-auto lg:max-h-[calc(100vh-170px)]">
          {list.isLoading && (
            <div className="space-y-2 px-4">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          )}
          {list.error && (
            <div className="px-4">
              <ErrorBox error={list.error} onRetry={() => list.refetch()} />
            </div>
          )}
          {list.data?.length === 0 && (
            <p className="px-4 py-6 text-sm text-muted">{q ? "No party matches your search." : "No parties yet."}</p>
          )}
          {list.data?.map((p) => (
            <Link
              key={p.id}
              href={`/parties/${p.id}`}
              className={cn(
                "flex items-start justify-between gap-3 border-l-2 border-transparent px-4 py-3 hover:bg-canvas",
                p.id === selectedId && "border-accent bg-accent-soft/60 hover:bg-accent-soft/60",
              )}
            >
              <div className="min-w-0">
                <p className="truncate font-medium">{p.name}</p>
                <p className="truncate text-xs text-muted">
                  {[(p.area ?? "").split(",")[0], `${p.design_count} design${p.design_count === 1 ? "" : "s"}`].filter(Boolean).join(" · ")}
                </p>
              </div>
              <span className="shrink-0 text-xs text-muted">{shortAgo(p.last_activity_at)}</span>
            </Link>
          ))}
        </div>
        <button
          className="px-4 py-3 text-xs text-muted hover:text-ink"
          onClick={() => setShowArchived((v) => !v)}
        >
          {showArchived ? "← Back to active parties" : "Show archived parties"}
        </button>
      </section>

      <section className="min-w-0 flex-1">
        {selectedId ? (
          <PartyProfile partyId={selectedId} />
        ) : (
          !list.isLoading && (
            <div className="p-6">
              <Empty
                title="Add your first party"
                action={
                  <Button variant="primary" onClick={() => setNewOpen(true)}>
                    <Plus className="h-4 w-4" /> New party
                  </Button>
                }
              >
                A party is one customer. Their designs, chats and preferences stay together.
              </Empty>
            </div>
          )
        )}
      </section>

      <PartyDialog open={newOpen} onOpenChange={setNewOpen} onSaved={(p) => router.push(`/parties/${p.id}`)} />
    </div>
  );
}

function PartyProfile({ partyId }: { partyId: string }) {
  const party = useParty(partyId);
  const designs = useDesigns({ partyId });
  const chats = useChats({ partyId });
  const refresh = useRefreshAll();
  const [editOpen, setEditOpen] = useState(false);
  const [newDesign, setNewDesign] = useState(false);
  const importRef = useRef<HTMLInputElement>(null);

  // Import designs: every chosen image becomes a design with its raw version.
  const importDesigns = useMutation({
    mutationFn: async (files: File[]) => {
      for (const f of files) {
        const d = await designsApi.create({ party_id: partyId, name: f.name.replace(/\.[^.]+$/, "") });
        await designsApi.addVersion(d.id, {
          parent_id: null,
          kind: "raw",
          label: "Raw",
          note: "Imported",
          image_url: f.size < 3_000_000 ? await fileToDataUrl(f) : demoImage("floral", "raw"),
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
        });
      }
      return files.length;
    },
    onSuccess: (n) => {
      toast.success(`${n} design${n === 1 ? "" : "s"} imported.`);
      refresh();
    },
    onError: (e) => toast.error(e.message),
  });

  if (party.isLoading) return <div className="p-6"><Skeleton className="h-40" /></div>;
  if (party.error) return <div className="p-6"><ErrorBox error={party.error} onRetry={() => party.refetch()} /></div>;
  const p = party.data!;
  const raws = (designs.data ?? []).map((d) => ({ d, raw: rawOf(d) })).filter((x) => x.raw);

  return (
    <div className="p-4 sm:p-6">
      <Link href="/parties" className="mb-3 inline-block text-sm text-muted hover:text-ink lg:hidden">
        ← All parties
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-2xl font-semibold">{p.name}</h2>
          <p className="mt-1 text-sm text-muted">
            {[p.area, p.phone, `party since ${new Date(p.created_at).toLocaleDateString("en-IN", { month: "short", year: "numeric" })}`]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <PartyChips party={p} />
        </div>
        <div className="flex gap-6 text-center">
          <Stat n={p.design_count} label="Designs" />
          <Stat n={p.chat_count} label="Chats" />
          <Stat n={p.raw_count} label="Raw images" />
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={() => setNewDesign(true)}>
          <Plus className="h-4 w-4" /> New design for this party
        </Button>
        <Button onClick={() => setEditOpen(true)}>
          <Pencil className="h-4 w-4" /> Edit party
        </Button>
        <input
          ref={importRef}
          type="file"
          multiple
          accept=".png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.svg"
          className="hidden"
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            if (files.length) importDesigns.mutate(files);
            e.target.value = "";
          }}
        />
        <Button onClick={() => importRef.current?.click()} loading={importDesigns.isPending}>
          <FileUp className="h-4 w-4" /> Import designs
        </Button>
        <PendingTag />
      </div>

      <Tabs defaultValue="designs" className="mt-6">
        <TabsList>
          <TabsTrigger value="designs">Designs (raw + outline)</TabsTrigger>
          <TabsTrigger value="chats">Chats ({p.chat_count})</TabsTrigger>
          <TabsTrigger value="raw">Raw images only</TabsTrigger>
        </TabsList>

        <TabsContent value="designs" className="pt-5">
          {designs.isLoading ? (
            <Grid>{[0, 1, 2].map((i) => <Skeleton key={i} className="h-56" />)}</Grid>
          ) : designs.data?.length ? (
            <Grid>
              {designs.data.map((d) => (
                <DesignCard key={d.id} design={d} />
              ))}
            </Grid>
          ) : (
            <Empty
              title="No designs yet"
              action={
                <Button variant="primary" onClick={() => setNewDesign(true)}>
                  <Plus className="h-4 w-4" /> New design
                </Button>
              }
            >
              Upload a raw image to make this party&apos;s first outline.
            </Empty>
          )}
        </TabsContent>

        <TabsContent value="chats" className="pt-5">
          <p className="mb-3 text-sm text-muted">
            Same list as the{" "}
            <Link className="text-accent-ink underline" href={`/chats?party=${p.id}`}>
              Chats page
            </Link>
            , filtered by this party.
          </p>
          <div className="divide-y divide-line overflow-hidden rounded-[var(--radius-card)] border border-line bg-surface">
            {chats.data?.map((c) => <ChatListItem key={c.id} chat={c} href={`/chats?party=${p.id}&chat=${c.id}`} />)}
            {chats.data?.length === 0 && <p className="p-4 text-sm text-muted">No chats yet.</p>}
          </div>
        </TabsContent>

        <TabsContent value="raw" className="pt-5">
          {raws.length ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
              {raws.map(({ d, raw }) => (
                <Link key={raw!.id} href={`/designs/${d.id}`} className="block">
                  <Thumb src={raw!.image_url} />
                  <p className="mt-1.5 truncate text-xs text-muted">{d.name}</p>
                </Link>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted">No raw images yet.</p>
          )}
        </TabsContent>
      </Tabs>

      <PartyDialog party={p} open={editOpen} onOpenChange={setEditOpen} />
      <NewDesignDialog open={newDesign} onOpenChange={setNewDesign} partyId={p.id} />
    </div>
  );
}

export function PartyChips({ party: p }: { party: Party }) {
  const chips = [
    p.usual_motifs,
    p.border_width && `Border ${p.border_width}`,
    p.line_thickness && `${p.line_thickness[0]!.toUpperCase()}${p.line_thickness.slice(1)} lines`,
    [softwareLabel(p.software), p.default_formats.map((f) => f.toUpperCase()).join(" + ")].filter(Boolean).join(" · "),
  ].filter(Boolean);
  if (!chips.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {chips.map((c) => (
        <Badge key={c as string} tone="accent">
          {c}
        </Badge>
      ))}
    </div>
  );
}

function Stat({ n, label }: { n: number; label: string }) {
  return (
    <div>
      <p className="text-2xl font-semibold tabular-nums">{n}</p>
      <p className="text-xs text-muted">{label}</p>
    </div>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{children}</div>;
}
