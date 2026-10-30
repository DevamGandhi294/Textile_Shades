import { Suspense } from "react";
import { JoinCard } from "@/components/auth-card";

export const metadata = { title: "Join your team · Magic Outline" };

export default function JoinPage() {
  return (
    <Suspense>
      <JoinCard />
    </Suspense>
  );
}
