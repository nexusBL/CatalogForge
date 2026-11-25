"use client";

import { Cross2Icon } from "@radix-ui/react-icons";
import Link from "next/link";
import { useState } from "react";
import { BabaMutationConfirm } from "@/components/baba-mutation-confirm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { babaAiHref } from "@/lib/assistant-ui";
import type { AssistantTurnResponse, MutationProposalView } from "@/lib/assistant-types";
import { authClient } from "@/lib/auth-client";
import { assistantTurnApi, cancelMutationApi, CatalogApiError, confirmMutationApi } from "@/lib/catalog-api";
import { persistCatalogueAfterMutation } from "@/lib/persist-catalogue-after-mutation";
import { cn } from "@/lib/utils";

const SUGGESTIONS = ["Why is my grade low?", "What should I fix first?", "What are customers complaining about?"];

type DockMessage =
  | { id: string; role: "user"; text: string }
  | {
      id: string;
      role: "assistant";
      text: string;
      actions: AssistantTurnResponse["actions"];
      unavailable: string | null;
      proposal: MutationProposalView | null;
    };

export function BabaAiDock({ catalogueId, currentRoute }: { catalogueId: string; currentRoute?: string }) {
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [value, setValue] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<DockMessage[]>([]);

  function send(text: string) {
    const message = text.trim();
    if (!organizationId || !message) {
      return;
    }
    setSending(true);
    setError(null);
    setMessages((current) => [...current, { id: `u-${Date.now()}`, role: "user", text: message }]);
    setValue("");
    assistantTurnApi(catalogueId, organizationId, message, currentRoute ? { currentRoute } : undefined)
      .then((row) => {
        setMessages((current) => [
          ...current,
          {
            id: `a-${Date.now()}`,
            role: "assistant",
            text: row.message,
            actions: row.actions,
            unavailable: row.unavailable,
            proposal: row.proposal ?? null,
          },
        ]);
      })
      .catch((caught: unknown) => {
        setError(
          caught instanceof CatalogApiError && caught.status >= 500
            ? "Baba AI is temporarily unavailable."
            : caught instanceof CatalogApiError
              ? caught.message
              : "Baba AI is temporarily unavailable.",
        );
      })
      .finally(() => setSending(false));
  }

  function resolveProposal(proposal: MutationProposalView, action: "confirm" | "cancel") {
    if (!organizationId || !proposal.confirm_token) {
      return;
    }
    setSending(true);
    setError(null);
    const request =
      action === "confirm"
        ? confirmMutationApi(catalogueId, organizationId, proposal.proposal_id, proposal.confirm_token)
        : cancelMutationApi(catalogueId, organizationId, proposal.proposal_id, proposal.confirm_token);
    request
      .then((row) => {
        persistCatalogueAfterMutation(row.proposal, catalogueId, organizationId);
        setMessages((current) => [
          ...current,
          {
            id: `a-${Date.now()}`,
            role: "assistant",
            text: row.message,
            actions: row.actions,
            unavailable: row.unavailable,
            proposal: row.proposal ?? null,
          },
        ]);
      })
      .catch((caught: unknown) => {
        setError(
          caught instanceof CatalogApiError && caught.status >= 500
            ? "Baba AI is temporarily unavailable."
            : caught instanceof CatalogApiError
              ? caught.message
              : "Baba AI is temporarily unavailable.",
        );
      })
      .finally(() => setSending(false));
  }

  return (
    <div className="fixed bottom-4 right-4 z-40 flex flex-col items-end gap-2">
      {open ? (
        <section
          className={cn(
            "flex flex-col overflow-hidden rounded-lg border border-border bg-card shadow-lg",
            expanded ? "h-[min(36rem,80vh)] w-[min(28rem,calc(100vw-2rem))]" : "h-[28rem] w-[22rem]",
          )}
          aria-label="Baba AI"
        >
          <header className="flex items-center justify-between border-b border-border px-3 py-2">
            <div>
              <p className="text-sm font-medium">Baba AI</p>
              <p className="text-xs text-muted-foreground">This catalogue</p>
            </div>
            <div className="flex items-center gap-1">
              <Button type="button" variant="ghost" size="sm" onClick={() => setExpanded((current) => !current)}>
                {expanded ? "Compact" : "Expand"}
              </Button>
              <Button type="button" variant="ghost" size="icon" aria-label="Close Baba AI" onClick={() => setOpen(false)}>
                <Cross2Icon />
              </Button>
            </div>
          </header>
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
            {messages.length === 0 ? (
              <div className="space-y-3">
                <p className="text-sm">
                  I can explain this catalogue’s grade, show affected items, and open the right improvement tools.
                </p>
                <ul className="space-y-2">
                  {SUGGESTIONS.map((prompt) => (
                    <li key={prompt}>
                      <button
                        type="button"
                        className="w-full rounded-md border border-border px-2 py-1.5 text-left text-sm hover:bg-selected"
                        onClick={() => send(prompt)}
                        disabled={sending || !organizationId}
                      >
                        {prompt}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              messages.map((entry) =>
                entry.role === "user" ? (
                  <p key={entry.id} className="text-sm">
                    <span className="text-xs text-muted-foreground">You · </span>
                    {entry.text}
                  </p>
                ) : (
                  <div key={entry.id} className="space-y-2">
                    <p className="whitespace-pre-wrap text-sm">
                      <span className="text-xs text-muted-foreground">Baba AI · </span>
                      {entry.text}
                    </p>
                    {entry.unavailable ? <p className="text-xs text-muted-foreground">{entry.unavailable}</p> : null}
                    {entry.actions.map((action) => (
                      <Button key={`${action.label}-${action.href}`} type="button" size="sm" variant="outline" asChild>
                        <Link href={action.href}>{action.label}</Link>
                      </Button>
                    ))}
                    {entry.proposal ? (
                      <BabaMutationConfirm
                        proposal={entry.proposal}
                        disabled={sending}
                        onConfirm={() => resolveProposal(entry.proposal!, "confirm")}
                        onCancel={() => resolveProposal(entry.proposal!, "cancel")}
                      />
                    ) : null}
                  </div>
                ),
              )
            )}
            {sending ? <p className="text-xs text-muted-foreground">✦ Baba AI is thinking…</p> : null}
            {error ? <p className="text-xs text-destructive">{error}</p> : null}
          </div>
          <form
            className="border-t border-border p-2"
            onSubmit={(event) => {
              event.preventDefault();
              send(value);
            }}
          >
            <div className="flex gap-2">
              <Input
                value={value}
                onChange={(event) => setValue(event.target.value)}
                placeholder="Ask Baba about this catalogue..."
                aria-label="Ask Baba about this catalogue"
                disabled={sending || !organizationId}
              />
              <Button type="submit" disabled={sending || !organizationId}>
                Send
              </Button>
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">
              <Link className="underline" href={babaAiHref(catalogueId)}>
                Open full Baba AI
              </Link>
            </p>
          </form>
        </section>
      ) : null}
      {!open ? (
        <Button type="button" onClick={() => setOpen(true)} aria-label="Open Baba AI">
          ✦ Baba AI
        </Button>
      ) : null}
    </div>
  );
}
