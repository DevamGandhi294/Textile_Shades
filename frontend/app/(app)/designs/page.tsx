"use client";

import { Plus, Search } from "lucide-react";
import { useState } from "react";
import { PageHeader } from "@/components/app-shell";
import { DesignCard } from "@/components/design-card";
import { NewDesignDialog } from "@/components/new-design-dialog";
import { Button, Empty, ErrorBox, Input, Select, Skeleton } from "@/components/ui/primitives";
import { useDesigns, useParties } from "@/lib/queries";

export default function DesignsPage() {
  const [q, setQ] = useState("");
  const [partyId, setPartyId] = useState("");
  const [open, setOpen] = useState(false);
  const parties = useParties();
  const designs = useDesigns({ partyId: partyId || undefined, q });
  const nameOf = new Map(parties.data?.map((p) => [p.id, p.name]));

  return (
    <div>
      <PageHeader
        title="Designs"
        actions={
          <Button variant="primary" onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" /> New design
          </Button>
        }
      />
      <div className="p-4 sm:p-6">
        <div className="mb-5 flex flex-wrap gap-2">
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search designs" className="pl-9" />
          </div>
          <Select value={partyId} onChange={(e) => setPartyId(e.target.value)} className="w-full sm:w-56" aria-label="Party">
            <option value="">All parties</option>
            {parties.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        </div>
        {designs.error && <ErrorBox error={designs.error} onRetry={() => designs.refetch()} />}
        {designs.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-56" />)}
          </div>
        ) : designs.data?.length ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {designs.data.map((d) => (
              <DesignCard key={d.id} design={d} partyName={d.party_id ? nameOf.get(d.party_id) : undefined} />
            ))}
          </div>
        ) : (
          <Empty title={q || partyId ? "No designs match" : "No designs yet"}>Upload a raw image to make your first outline.</Empty>
        )}
      </div>
      <NewDesignDialog open={open} onOpenChange={setOpen} partyId={partyId || null} />
    </div>
  );
}
