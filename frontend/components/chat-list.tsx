"use client";

import Link from "next/link";
import type { Chat, ChatMessage, DesignVersion } from "@/lib/api/types";
import { cn, shortAgo } from "@/lib/utils";

export function ChatListItem({ chat, href, active }: { chat: Chat; href: string; active?: boolean }) {
  const last = chat.messages.filter((m) => m.role === "user").at(-1) ?? chat.messages.at(-1);
  return (
    <Link
      href={href}
      className={cn("block px-4 py-3 hover:bg-canvas", active && "bg-accent-soft/60 hover:bg-accent-soft/60")}
    >
      <div className="flex items-baseline justify-between gap-3">
        <p className="truncate font-medium">{chat.title}</p>
        <span className="shrink-0 text-xs text-muted">{shortAgo(chat.last_message_at)}</span>
      </div>
      <p className="mt-0.5 truncate text-sm text-muted">{last?.content ?? "No messages yet"}</p>
      <p className="mt-0.5 text-xs text-muted/80">{chat.result_label}</p>
    </Link>
  );
}

/** One chat message bubble; assistant messages can show the prompt sent to the image model. */
export function MessageBubble({
  m,
  version,
  showPrompt = true,
}: {
  m: ChatMessage;
  version?: DesignVersion | null;
  showPrompt?: boolean;
}) {
  const mine = m.role === "user";
  return (
    <div className={cn("flex flex-col", mine ? "items-end" : "items-start")}>
      <div
        className={cn(
          "max-w-[88%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed",
          mine ? "rounded-br-md bg-accent text-white" : "rounded-bl-md border border-line bg-surface",
        )}
      >
        {m.content}
        {version && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={version.image_url} alt={version.label} className="mt-2 max-h-40 rounded-lg border border-line bg-white" />
        )}
      </div>
      {!mine && showPrompt && m.final_prompt && (
        <details className="mt-1.5 max-w-[88%] rounded-xl border border-line bg-canvas px-3 py-2 text-xs">
          <summary className="cursor-pointer font-medium text-muted">Prompt sent to image model</summary>
          <p className="mt-1.5 leading-relaxed text-ink">{m.final_prompt}</p>
        </details>
      )}
      {!mine && m.model_label && <p className="mt-1 text-[11px] text-muted">{m.model_label}</p>}
    </div>
  );
}
