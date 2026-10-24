import { describe, expect, it } from "vitest";

import { citationKeys } from "./citations";

describe("citationKeys", () => {
  it("returns unique citation keys in reading order", () => {
    expect(citationKeys("火克草[S1]，水克火[S2]，另有[S1]。")).toEqual([
      "S1",
      "S2",
    ]);
  });
});
