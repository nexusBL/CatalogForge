"use client";

import { ArrowRightIcon, ChevronDownIcon } from "@radix-ui/react-icons";
import Link from "next/link";
import { useState } from "react";
import { BabaMutationConfirm } from "@/components/baba-mutation-confirm";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { BABA_AI_PROMPTS } from "@/lib/assistant-ui";
import type { AssistantTurnResponse, MutationProposalView } from "@/lib/assistant-types";
import type { StoredCatalogue } from "@/lib/catalog-types";
import { catalogueTypeLabel, venueDisplayName, venueLocation } from "@/lib/restaurant-identity";
import { cn } from "@/lib/utils";

export type BabaChatMessage =
  | { id: string; role: "user"; text: string }
  | {
      id: string;
      role: "assistant";
      text: string;
      actions: AssistantTurnResponse["actions"];
      unavailable: string | null;
      proposal?: MutationProposalView | null;
    };

export function catalogueOptionLabel(row: StoredCatalogue): { name: string; detail: string } {
  const name = venueDisplayName(row.result);
  const detail = [catalogueTypeLabel(row.result.catalogue_type), venueLocation(row.result)]
    .filter(Boolean)
    .join(" · ");
  return { name, detail };
}

export function BabaAiWorkspace({
  catalogues,
  selectedId,
  onSelectCatalogue,
  messages,
  value,
  onChange,
  onSend,
  sending,
  error,
  onRetry,
  onConfirmProposal,
  onCancelProposal,
}: {
  catalogues: StoredCatalogue[];
  selectedId: string | null;
  onSelectCatalogue: (id: string) => void;
  messages: BabaChatMessage[];
  value: string;
  onChange: (value: string) => void;
  onSend: (message: string) => void;
  sending: boolean;
  error: string | null;
  onRetry?: () => void;
  onConfirmProposal?: (proposal: MutationProposalView) => void;
  onCancelProposal?: (proposal: MutationProposalView) => void;
}) {
  const [localError, setLocalError] = useState<string | null>(null);
  const selected = catalogues.find((row) => row.id === selectedId) ?? null;
  const selectedLabel = selected ? catalogueOptionLabel(selected) : null;
  const hasThread = messages.length > 0;

  function submit(message: string) {
    const text = message.trim();
    if (!text) {
      setLocalError(selectedId ? "Ask Baba AI a short question about this catalogue." : "Ask Baba AI a short question.");
      return;
    }
    setLocalError(null);
    onSend(text);
  }

  return (
    <div className="flex min-h-[calc(100dvh-4rem)] flex-col">
      <header className="border-b border-border px-6 py-4 tablet:px-10 desktop:px-14">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-3">
          <div>
            <p className="text-sm font-medium tracking-tight">Baba AI</p>
            <p className="text-xs text-muted-foreground">CatalogForge assistant</p>
          </div>
          <CatalogueSelector
            catalogues={catalogues}
            selectedId={selectedId}
            selectedLabel={selectedLabel}
            onSelect={onSelectCatalogue}
          />
        </div>
      </header>

      <div className="flex flex-1 flex-col">
        {!selectedId && !hasThread ? (
          <EmptyNeedCatalogue onPrompt={(prompt) => submit(prompt)} sending={sending} />
        ) : !hasThread ? (
          <Landing selectedLabel={selectedLabel} sending={sending} onPrompt={(prompt) => submit(prompt)} />
        ) : (
          <Thread
            messages={messages}
            sending={sending}
            selectedLabel={selectedLabel}
            onConfirmProposal={onConfirmProposal}
            onCancelProposal={onCancelProposal}
          />
        )}
      </div>

      <div className="border-t border-border px-6 py-4 tablet:px-10 desktop:px-14">
        <div className="mx-auto w-full max-w-3xl space-y-2">
          {error || localError ? (
            <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
              <p>{error || localError}</p>
              {error && onRetry ? (
                <Button type="button" variant="outline" size="sm" onClick={onRetry}>
                  Retry
                </Button>
              ) : null}
            </div>
          ) : null}
          <form
            className="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5"
            onSubmit={(event) => {
              event.preventDefault();
              submit(value);
            }}
          >
            <Input
              value={value}
              onChange={(event) => onChange(event.target.value)}
              placeholder={selectedId ? "Ask Baba AI about this catalogue..." : "Ask about restaurants with poor grades..."}
              aria-label={selectedId ? "Ask Baba AI about this catalogue" : "Ask Baba AI about your restaurants"}
              disabled={sending}
              className="h-9 border-0 bg-transparent shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
            />
            <Button type="submit" size="icon" disabled={sending} aria-label="Send">
              <ArrowRightIcon />
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}

function CatalogueSelector({
  catalogues,
  selectedId,
  selectedLabel,
  onSelect,
}: {
  catalogues: StoredCatalogue[];
  selectedId: string | null;
  selectedLabel: { name: string; detail: string } | null;
  onSelect: (id: string) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex w-full max-w-md items-center justify-between rounded-md border border-border bg-background px-3 py-2 text-left hover:bg-selected"
          aria-label="Choose catalogue"
        >
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium">
              {selectedLabel?.name || "Choose a catalogue"}
            </span>
            <span className="block truncate text-xs text-muted-foreground">
              {selectedLabel?.detail || "Baba AI answers for one authorized catalogue at a time"}
            </span>
          </span>
          <ChevronDownIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[min(28rem,calc(100vw-3rem))]">
        {catalogues.length === 0 ? (
          <DropdownMenuItem disabled>No catalogues in this organization</DropdownMenuItem>
        ) : (
          catalogues.map((row) => {
            const label = catalogueOptionLabel(row);
            return (
              <DropdownMenuItem
                key={row.id}
                onSelect={() => onSelect(row.id)}
                className={cn("flex flex-col items-start gap-0.5", row.id === selectedId && "bg-selected")}
              >
                <span>{label.name}</span>
                {label.detail ? <span className="text-xs text-muted-foreground">{label.detail}</span> : null}
              </DropdownMenuItem>
            );
          })
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function EmptyNeedCatalogue({ onPrompt, sending }: { onPrompt: (prompt: string) => void; sending: boolean }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-16 text-center">
      <p className="text-lg font-medium tracking-tight">Choose a catalogue to start</p>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        Baba AI can also answer organization-wide grade questions without a selected catalogue. It does not invent grades.
      </p>
      <Button
        type="button"
        variant="outline"
        className="mt-4"
        disabled={sending}
        onClick={() => onPrompt("Show me my restaurants with poor grades")}
      >
        Show restaurants with poor grades
      </Button>
    </div>
  );
}

function Landing({
  selectedLabel,
  sending,
  onPrompt,
}: {
  selectedLabel: { name: string; detail: string } | null;
  sending: boolean;
  onPrompt: (prompt: string) => void;
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-12">
      <div className="flex max-w-xl flex-col items-center text-center">
        <span className="text-3xl text-muted-foreground" aria-hidden>
          ✦
        </span>
        <h2 className="mt-6 text-2xl font-medium tracking-tight">What can I help you with?</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {selectedLabel
            ? `${selectedLabel.name}${selectedLabel.detail ? ` · ${selectedLabel.detail}` : ""}`
            : "Your AI assistant for CatalogForge"}
        </p>
        <ul className="mt-8 grid w-full gap-2 tablet:grid-cols-2">
          {BABA_AI_PROMPTS.map((prompt) => (
            <li key={prompt}>
              <button
                type="button"
                disabled={sending}
                onClick={() => onPrompt(prompt)}
                className="h-full w-full rounded-md border border-border px-3 py-3 text-left text-sm text-foreground hover:bg-selected disabled:opacity-50"
              >
                {prompt}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Thread({
  messages,
  sending,
  selectedLabel,
  onConfirmProposal,
  onCancelProposal,
}: {
  messages: BabaChatMessage[];
  sending: boolean;
  selectedLabel: { name: string; detail: string } | null;
  onConfirmProposal?: (proposal: MutationProposalView) => void;
  onCancelProposal?: (proposal: MutationProposalView) => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-6 py-8 tablet:px-10">
      {selectedLabel ? (
        <p className="text-xs text-muted-foreground">
          Answering for {selectedLabel.name}
          {selectedLabel.detail ? ` · ${selectedLabel.detail}` : ""}
        </p>
      ) : null}
      {messages.map((entry) =>
        entry.role === "user" ? (
          <div key={entry.id} className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">You</p>
            <p className="text-sm">{entry.text}</p>
          </div>
        ) : (
          <div key={entry.id} className="space-y-3">
            <p className="text-xs font-medium text-muted-foreground">Baba AI</p>
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{entry.text}</p>
            {entry.unavailable ? <p className="text-sm text-muted-foreground">{entry.unavailable}</p> : null}
            {entry.actions.length ? (
              <div className="flex flex-wrap gap-2">
                {entry.actions.map((action) => (
                  <Button key={`${action.label}-${action.href}`} variant="outline" size="sm" asChild>
                    <Link href={action.href}>{action.label}</Link>
                  </Button>
                ))}
              </div>
            ) : null}
            {entry.proposal && onConfirmProposal && onCancelProposal ? (
              <BabaMutationConfirm
                proposal={entry.proposal}
                disabled={sending}
                onConfirm={() => onConfirmProposal(entry.proposal!)}
                onCancel={() => onCancelProposal(entry.proposal!)}
              />
            ) : null}
          </div>
        ),
      )}
      {sending ? (
        <p className="text-sm text-muted-foreground">
          <span className="baba-spark-pulse mr-2 inline-block" aria-hidden>
            ✦
          </span>
          Baba AI is thinking…
        </p>
      ) : null}
    </div>
  );
}
