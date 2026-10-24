import { describe, expect, it } from "vitest";

import {
  buildDocumentQuery,
  canRunCrawler,
  jobStatusLabel,
} from "./dataAdmin";

describe("data administration helpers", () => {
  it("encodes document filters and omits empty values", () => {
    const query = new URLSearchParams(
      buildDocumentQuery({
        q: "灵兽 & 属性",
        product: "东煌纪",
        status: "active",
        page: 2,
        pageSize: 20,
      }),
    );

    expect(query.get("q")).toBe("灵兽 & 属性");
    expect(query.get("product")).toBe("东煌纪");
    expect(query.get("section")).toBeNull();
    expect(query.get("page")).toBe("2");
  });

  it("only allows an idle active crawler to run", () => {
    expect(canRunCrawler("active", null)).toBe(true);
    expect(canRunCrawler("active", "job-1")).toBe(false);
    expect(canRunCrawler("disabled", null)).toBe(false);
  });

  it("maps background job states to operator-facing labels", () => {
    expect(jobStatusLabel("queued")).toBe("排队中");
    expect(jobStatusLabel("running")).toBe("处理中");
    expect(jobStatusLabel("completed")).toBe("已完成");
    expect(jobStatusLabel("failed")).toBe("失败");
  });
});
