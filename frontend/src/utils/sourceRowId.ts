/** Content identity keeps recurring source IDs independently selectable. */
export function sourceRowId(section: string, version: string, row: {
  "Bug ID"?: string; "Feature ID"?: string; category?: string;
  Description: string; markdown?: string;
}): string {
  return JSON.stringify([section, version, row["Bug ID"] ?? row["Feature ID"] ?? "",
    row.category ?? "", row.Description, row.markdown ?? ""]);
}
