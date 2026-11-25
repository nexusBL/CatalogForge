import type { MutationProposalView } from "@/lib/assistant-types";
import { getCatalogueApi } from "@/lib/catalog-api";
import { saveCatalogue } from "@/lib/catalogue-store";

export function persistCatalogueAfterMutation(
  proposal: MutationProposalView | null | undefined,
  catalogueId: string,
  organizationId: string,
): void {
  if (!proposal || proposal.status !== "APPLIED" || !proposal.writes_payload) {
    return;
  }
  void getCatalogueApi(catalogueId, organizationId).then((row) => {
    if (row) {
      saveCatalogue(row);
    }
  });
}
