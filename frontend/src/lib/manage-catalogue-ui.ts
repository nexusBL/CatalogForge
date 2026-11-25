export function catalogueManageHref(catalogueId: string): string {
  return `/catalogues/${catalogueId}/manage`;
}

export type CatalogueMutationOperation =
  | "add_item"
  | "remove_item"
  | "rename_item"
  | "change_price"
  | "update_description"
  | "update_labels"
  | "move_item";

export type CatalogueMutationDraft = {
  operation: CatalogueMutationOperation;
  item_name?: string | null;
  new_item_name?: string | null;
  category_name?: string | null;
  source_category_name?: string | null;
  target_category_name?: string | null;
  price?: number | null;
  description?: string | null;
  labels?: string[] | null;
};
