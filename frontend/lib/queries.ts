"use client";

// TanStack Query keys and hooks, so every screen reads the same cache.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { authApi, billingApi, chatsApi, designsApi, partiesApi } from "./api/data";
import { outlineApi } from "./api/outline";

export const keys = {
  me: ["me"] as const,
  parties: (opts: object = {}) => ["parties", opts] as const,
  party: (id: string) => ["party", id] as const,
  designs: (opts: object = {}) => ["designs", opts] as const,
  design: (id: string) => ["design", id] as const,
  chats: (opts: object = {}) => ["chats", opts] as const,
  chat: (id: string) => ["chat", id] as const,
  designChats: (id: string) => ["design-chats", id] as const,
  aiContext: (id: string) => ["ai-context", id] as const,
  billing: ["billing"] as const,
  usage: ["usage"] as const,
  invoices: ["invoices"] as const,
  members: ["members"] as const,
  plans: ["plans"] as const,
  health: ["health"] as const,
};

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: authApi.me, staleTime: Infinity });

export const useParties = (opts: { q?: string; archived?: boolean } = {}) =>
  useQuery({ queryKey: keys.parties(opts), queryFn: () => partiesApi.list(opts) });

export const useParty = (id: string | null | undefined) =>
  useQuery({ queryKey: keys.party(id ?? ""), queryFn: () => partiesApi.get(id!), enabled: !!id });

export const useDesigns = (opts: { partyId?: string; q?: string } = {}) =>
  useQuery({ queryKey: keys.designs(opts), queryFn: () => designsApi.list(opts) });

export const useDesign = (id: string | null | undefined) =>
  useQuery({ queryKey: keys.design(id ?? ""), queryFn: () => designsApi.get(id!), enabled: !!id });

export const useChats = (opts: { partyId?: string; q?: string } = {}) =>
  useQuery({ queryKey: keys.chats(opts), queryFn: () => chatsApi.list(opts) });

export const useChat = (id: string | null | undefined) =>
  useQuery({ queryKey: keys.chat(id ?? ""), queryFn: () => chatsApi.get(id!), enabled: !!id });

export const useDesignChats = (id: string | null | undefined) =>
  useQuery({ queryKey: keys.designChats(id ?? ""), queryFn: () => chatsApi.forDesign(id!), enabled: !!id });

export const useAiContext = (chatId: string | null | undefined) =>
  useQuery({ queryKey: keys.aiContext(chatId ?? ""), queryFn: () => chatsApi.aiContext(chatId!), enabled: !!chatId });

export const useBilling = () => useQuery({ queryKey: keys.billing, queryFn: billingApi.summary });
export const useUsage = () => useQuery({ queryKey: keys.usage, queryFn: billingApi.usage });
export const useInvoices = () => useQuery({ queryKey: keys.invoices, queryFn: billingApi.invoices });
export const useMembers = () => useQuery({ queryKey: keys.members, queryFn: billingApi.members });
export const usePlans = () => useQuery({ queryKey: keys.plans, queryFn: billingApi.plans, staleTime: Infinity });

/** Is the image backend up, and are the line model and OpenAI key there? */
export const useHealth = () =>
  useQuery({ queryKey: keys.health, queryFn: outlineApi.health, retry: false, refetchInterval: 60_000 });

/** After any change: refresh every list (they are cheap, and this keeps counts right everywhere). */
export function useRefreshAll() {
  const qc = useQueryClient();
  return () =>
    qc.invalidateQueries({
      predicate: (q) => !["me", "plans", "health"].includes(q.queryKey[0] as string),
    });
}
