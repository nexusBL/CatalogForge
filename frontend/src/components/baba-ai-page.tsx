"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { BabaAiWorkspace, type BabaChatMessage } from "@/components/baba-ai-workspace";
import { DashboardShell } from "@/components/dashboard-shell";
import { babaAiHref } from "@/lib/assistant-ui";
import type { MutationProposalView } from "@/lib/assistant-types";
import { authClient } from "@/lib/auth-client";
import { assistantTurnApi, cancelMutationApi, CatalogApiError, confirmMutationApi, listCataloguesApi } from "@/lib/catalog-api";
import { listCatalogues } from "@/lib/catalogue-store";
import { persistCatalogueAfterMutation } from "@/lib/persist-catalogue-after-mutation";
import type { StoredCatalogue } from "@/lib/catalog-types";

function unavailableMessage(error: unknown): string {
  if (error instanceof CatalogApiError && error.status >= 500) {
    return "Baba AI is temporarily unavailable.";
  }
  if (error instanceof CatalogApiError) {
    return error.message;
  }
  return "Baba AI is temporarily unavailable.";
}

export function BabaAiPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedId = searchParams.get("catalogue");
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const [catalogues, setCatalogues] = useState<StoredCatalogue[]>([]);
  const [value, setValue] = useState("");
  const [messages, setMessages] = useState<BabaChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);

  const selectedId = catalogues.some((row) => row.id === requestedId) ? requestedId : null;

  useEffect(() => {
    if (!organizationId) {
      setCatalogues([]);
      return;
    }
    let cancelled = false;
    setCatalogues(listCatalogues(organizationId));
    listCataloguesApi(organizationId)
      .then((rows) => {
        if (!cancelled) {
          setCatalogues(rows);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCatalogues(listCatalogues(organizationId));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [organizationId]);

  function selectCatalogue(id: string) {
    setMessages([]);
    setError(null);
    setValue("");
    setLastQuestion(null);
    router.replace(babaAiHref(id));
  }

  function onSend(message: string) {
    if (!organizationId) {
      return;
    }
    setSending(true);
    setError(null);
    setLastQuestion(message);
    const userId = `user-${Date.now()}`;
    setMessages((current) => [...current, { id: userId, role: "user", text: message }]);
    setValue("");
    const currentRoute = selectedId ? `/baba-ai?catalogue=${encodeURIComponent(selectedId)}` : "/baba-ai";
    assistantTurnApi(selectedId, organizationId, message, { currentRoute })
      .then((row) => {
        setMessages((current) => [
          ...current,
          {
            id: `assistant-${Date.now()}`,
            role: "assistant",
            text: row.message,
            actions: row.actions,
            unavailable: row.unavailable,
            proposal: row.proposal ?? null,
          },
        ]);
      })
      .catch((caught: unknown) => {
        setError(unavailableMessage(caught));
      })
      .finally(() => setSending(false));
  }

  function resolveProposal(proposal: MutationProposalView, action: "confirm" | "cancel") {
    if (!organizationId || !selectedId || !proposal?.confirm_token) {
      return;
    }
    setSending(true);
    setError(null);
    const request =
      action === "confirm"
        ? confirmMutationApi(selectedId, organizationId, proposal.proposal_id, proposal.confirm_token)
        : cancelMutationApi(selectedId, organizationId, proposal.proposal_id, proposal.confirm_token);
    request
      .then((row) => {
        persistCatalogueAfterMutation(row.proposal, selectedId, organizationId);
        setMessages((current) => [
          ...current,
          {
            id: `assistant-${Date.now()}`,
            role: "assistant",
            text: row.message,
            actions: row.actions,
            unavailable: row.unavailable,
            proposal: row.proposal ?? null,
          },
        ]);
      })
      .catch((caught: unknown) => {
        setError(unavailableMessage(caught));
      })
      .finally(() => setSending(false));
  }

  function onRetry() {
    if (lastQuestion) {
      onSend(lastQuestion);
    }
  }

  return (
    <DashboardShell title="Baba AI">
      <BabaAiWorkspace
        catalogues={catalogues}
        selectedId={selectedId}
        onSelectCatalogue={selectCatalogue}
        messages={messages}
        value={value}
        onChange={setValue}
        onSend={onSend}
        sending={sending}
        error={error}
        onRetry={lastQuestion ? onRetry : undefined}
        onConfirmProposal={(proposal) => resolveProposal(proposal, "confirm")}
        onCancelProposal={(proposal) => resolveProposal(proposal, "cancel")}
      />
    </DashboardShell>
  );
}
