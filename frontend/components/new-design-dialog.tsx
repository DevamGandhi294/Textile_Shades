"use client";

import { useMutation } from "@tanstack/react-query";
import { ImagePlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { designsApi } from "@/lib/api/data";
import { setPendingUpload } from "@/lib/pending-upload";
import { useParties, useRefreshAll } from "@/lib/queries";
import { Button, Dialog, DialogContent, Field, Input, Select } from "./ui/primitives";

const IMAGE_TYPES = ".png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff";

/** Name + party (+ optional first photo), then open the new design in the workspace. */
export function NewDesignDialog({
  open,
  onOpenChange,
  partyId,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  partyId?: string | null;
}) {
  const router = useRouter();
  const refresh = useRefreshAll();
  const parties = useParties();
  const [name, setName] = useState("");
  const [party, setParty] = useState(partyId ?? "");
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setName("");
      setParty(partyId ?? "");
      setFile(null);
    }
  }, [open, partyId]);

  const create = useMutation({
    mutationFn: () => designsApi.create({ party_id: party || null, name: name || file?.name.replace(/\.[^.]+$/, "") || "" }),
    onSuccess: (d) => {
      if (file) setPendingUpload(d.id, file);
      refresh();
      onOpenChange(false);
      router.push(`/workspace/${d.id}`);
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New design" description="Give it a name your team will recognise, like “Paisley saree border”.">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <Field label="Design name">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Paisley saree border" autoFocus />
          </Field>
          <Field label="Party">
            <Select value={party} onChange={(e) => setParty(e.target.value)}>
              <option value="">No party</option>
              {parties.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Raw image (optional)" hint="Phone photo, scan or sketch. JPG or PNG, up to 20 MB.">
            <input
              ref={fileRef}
              type="file"
              accept={IMAGE_TYPES}
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <Button type="button" onClick={() => fileRef.current?.click()} className="w-full justify-start">
              <ImagePlus className="h-4 w-4" />
              <span className="truncate">{file ? file.name : "Choose a photo"}</span>
            </Button>
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={create.isPending}>
              Open in workspace
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
