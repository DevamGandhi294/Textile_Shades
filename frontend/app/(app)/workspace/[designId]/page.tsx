"use client";

import { Suspense, use } from "react";
import { Workspace } from "@/components/workspace/workspace";

export default function WorkspacePage({ params }: { params: Promise<{ designId: string }> }) {
  const { designId } = use(params);
  return (
    <Suspense>
      <Workspace designId={designId} />
    </Suspense>
  );
}
