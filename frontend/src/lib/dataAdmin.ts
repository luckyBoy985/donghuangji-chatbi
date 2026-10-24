export interface DocumentQuery {
  q?: string;
  product?: string;
  section?: string;
  status?: string;
  page?: number;
  pageSize?: number;
}

export function buildDocumentQuery(filters: DocumentQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") {
      params.set(key === "pageSize" ? "page_size" : key, String(value));
    }
  }
  return params.toString();
}

export function canRunCrawler(
  status: string,
  activeJobId: string | null,
): boolean {
  return status === "active" && !activeJobId;
}

export function jobStatusLabel(status: string): string {
  return (
    {
      queued: "排队中",
      running: "处理中",
      completed: "已完成",
      failed: "失败",
    }[status] || status
  );
}
