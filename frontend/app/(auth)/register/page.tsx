import { Suspense } from "react";
import { RegisterCard } from "@/components/auth-card";

export const metadata = { title: "Create account · Magic Outline" };

export default function RegisterPage() {
  return (
    <Suspense>
      <RegisterCard />
    </Suspense>
  );
}
