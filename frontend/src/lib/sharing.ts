export function canWriteConversation(
  accessRole: "owner" | "read" | null | undefined,
): boolean {
  return accessRole === "owner";
}
