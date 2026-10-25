import { redirect } from "next/navigation";

// Login is skipped for now, so the app opens straight into the workspace.
export default function Home() {
  redirect("/workspace");
}
