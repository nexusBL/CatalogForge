import { redirect } from "next/navigation";
import { babaAiHref } from "@/lib/assistant-ui";

export default async function CatalogueAssistantRedirectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(babaAiHref(id));
}
