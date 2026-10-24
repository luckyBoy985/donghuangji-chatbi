import { describe, expect, it } from "vitest";

import {
  passwordChangeError,
  requiresPasswordChange,
} from "./authFlow";

describe("authentication flow helpers", () => {
  it("requires a change for users with a temporary password", () => {
    expect(requiresPasswordChange({ must_change_password: true })).toBe(true);
    expect(requiresPasswordChange({ must_change_password: false })).toBe(false);
  });

  it("rejects short or unchanged replacement passwords", () => {
    expect(passwordChangeError("temporary", "short")).toContain("12");
    expect(passwordChangeError("same-password", "same-password")).toContain(
      "相同",
    );
    expect(passwordChangeError("temporary", "long-enough-password")).toBe("");
  });
});
