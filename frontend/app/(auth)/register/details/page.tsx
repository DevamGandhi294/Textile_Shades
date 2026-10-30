import { Suspense } from "react";
import { GoogleDetailsCard } from "@/components/auth-card";

export const metadata = { title: "Almost done · Magic Outline" };

export default function GoogleDetailsPage() {
  return (
    <Suspense>
      <GoogleDetailsCard />
    </Suspense>
  );
}
