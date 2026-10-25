import { Suspense } from "react";
import { LoginCard } from "@/components/auth-card";

export const metadata = { title: "Log in · Magic Outline" };

export default function LoginPage() {
  return (
    <Suspense>
      <LoginCard />
    </Suspense>
  );
}
