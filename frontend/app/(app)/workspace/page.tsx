"use client";

import { ImagePlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { NewDesignDialog } from "@/components/new-design-dialog";
import { Button, Skeleton } from "@/components/ui/primitives";
import { useDesigns } from "@/lib/queries";

/** Opens the most recent design, or offers to start the first one. */
export default function WorkspaceIndex() {
  const router = useRouter();
  const designs = useDesigns();
  const [open, setOpen] = useState(false);
  const first = designs.data?.[0];

  useEffect(() => {
    if (first) router.replace(`/workspace/${first.id}`);
  }, [first, router]);

  if (designs.isLoading || first) return <div className="p-6"><Skeleton className="h-[70vh]" /></div>;
  return (
    <div className="grid min-h-[80vh] place-items-center p-6">
      <div className="max-w-md text-center">
        <ImagePlus className="mx-auto h-10 w-10 text-accent" />
        <h1 className="mt-4 text-xl font-semibold">Make your first outline</h1>
        <p className="mt-1 text-sm text-muted">Upload a sketch or phone photo and get a clean, closed outline you can open in Wilcom or CorelDRAW.</p>
        <Button variant="primary" size="lg" className="mt-6" onClick={() => setOpen(true)}>
          New design
        </Button>
      </div>
      <NewDesignDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}
