import { describe, expect, it } from "vitest";

import { formatRequestError } from "./errors";

describe("request error formatting", () => {
  it("includes the backend request id for support", () => {
    expect(formatRequestError("处理失败", "req-123")).toBe(
      "处理失败（请求 ID: req-123）",
    );
  });

  it("keeps the original message when no request id exists", () => {
    expect(formatRequestError("处理失败", "")).toBe("处理失败");
  });
});
