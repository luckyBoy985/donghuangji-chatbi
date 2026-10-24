import { describe, expect, it } from "vitest";

import { canWriteConversation } from "./sharing";

describe("canWriteConversation", () => {
  it("allows only conversation owners to write", () => {
    expect(canWriteConversation("owner")).toBe(true);
    expect(canWriteConversation("read")).toBe(false);
    expect(canWriteConversation(null)).toBe(false);
  });
});
