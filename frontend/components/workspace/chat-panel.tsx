"use client";

import { Plus, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { MAX_CHAT_CHARS } from "@/lib/api/outline";
import { CREDIT_COST, type Chat, type DesignVersion } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { MessageBubble } from "../chat-list";
import { Button, Select, Textarea } from "../ui/primitives";

export function ChatPanel({
  chats,
  chatId,
  onChatChange,
  versions,
  onGenerate,
  busy,
  disabled,
  disabledReason,
}: {
  chats: Chat[];
  chatId: string | null;
  onChatChange: (id: string | null) => void;
  versions: DesignVersion[];
  onGenerate: (message: string) => Promise<boolean>;
  busy: boolean;
  disabled?: boolean;
  disabledReason?: string;
}) {
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const chat = chats.find((c) => c.id === chatId) ?? null;
  const byId = new Map(versions.map((v) => [v.id, v]));

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [chat?.messages.length, busy]);

  async function send() {
    if (busy || disabled) return;
    if (await onGenerate(text.trim())) setText("");
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        <Select
          value={chatId ?? ""}
          onChange={(e) => onChatChange(e.target.value || null)}
          className="h-8 flex-1 text-[13px]"
          aria-label="Chat"
        >
          {!chatId && <option value="">New chat</option>}
          {chats.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </Select>
        <Button size="icon" variant="ghost" onClick={() => onChatChange(null)} title="New chat" aria-label="New chat">
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-3 py-4">
        {!chat?.messages.length && (
          <div className="rounded-xl bg-canvas p-4 text-sm text-muted">
            <p className="font-medium text-ink">Ask for a change in your own words</p>
            <p className="mt-1">“Clean this sketch, keep my lines close”, “make the lines thinner”, “close the small gaps”.</p>
            <p className="mt-2">Leave the box empty and press Generate to redraw the whole design as clean line art.</p>
          </div>
        )}
        {chat?.messages.map((m) => (
          <MessageBubble key={m.id} m={m} version={m.attachment_version_id ? byId.get(m.attachment_version_id) : null} />
        ))}
        {busy && (
          <div className="flex items-center gap-2 text-sm text-muted">
            <span className="flex gap-1">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:120ms]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:240ms]" />
            </span>
            Drawing… this can take up to a minute.
          </div>
        )}
        <div ref={end} />
      </div>

      <div className="border-t border-line p-3">
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value.slice(0, MAX_CHAT_CHARS))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          rows={3}
          placeholder="Ask for a change"
          disabled={disabled}
          aria-label="Ask for a change"
        />
        <div className="mt-2 flex items-center justify-between gap-2">
          <span className={cn("text-xs text-muted", text.length > MAX_CHAT_CHARS - 30 && "text-warn")}>
            {disabled ? disabledReason : `About ${CREDIT_COST.final} credits · ${text.length}/${MAX_CHAT_CHARS}`}
          </span>
          <Button variant="primary" onClick={send} loading={busy} disabled={disabled}>
            <Send className="h-4 w-4" /> Generate
          </Button>
        </div>
      </div>
    </div>
  );
}
