import type {
  Catalog,
  Citation,
  AdminTeam,
  AdminUser,
  AdminPasswordReset,
  AuditItem,
  ConversationDetail,
  ConversationShare,
  ConversationSummary,
  DataDocument,
  DataDocumentDetail,
  DataDocumentPage,
  DataOverview,
  DataSource,
  IngestJob,
  InvitationCreated,
  Report,
  StreamCallbacks,
  TeamInfo,
  TeamMember,
  UserInfo,
} from "../types";
import { buildDocumentQuery, type DocumentQuery } from "../lib/dataAdmin";
import { formatRequestError } from "../lib/errors";

const API_BASE = (import.meta.env.VITE_API_BASE || "/api").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isForm = init?.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let detail = `请求失败 (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail || detail;
    } catch {
      // Keep the status-based message when the response is not JSON.
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  setupStatus: () => request<{ setup_required: boolean }>("/auth/setup-status"),
  setup: (payload: Record<string, string>) =>
    request<UserInfo>("/auth/setup", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  login: (username: string, password: string) =>
    request<UserInfo>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  me: () => request<UserInfo>("/me"),
  updateProfile: (displayName: string) =>
    request<UserInfo>("/me", {
      method: "PATCH",
      body: JSON.stringify({ display_name: displayName }),
    }),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<void>("/auth/password", {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    }),
  registerWithInvite: (payload: Record<string, string>) =>
    request<UserInfo>("/auth/register-with-invite", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  catalog: () => request<Catalog>("/catalog"),
  conversations: (scope: "mine" | "shared" = "mine") =>
    request<ConversationSummary[]>(`/conversations?scope=${scope}`),
  conversation: (id: string) =>
    request<ConversationDetail>(`/conversations/${id}`),
  createConversation: () =>
    request<ConversationSummary>("/conversations", {
      method: "POST",
      body: "{}",
    }),
  renameConversation: (id: string, title: string) =>
    request<ConversationSummary>(`/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  deleteConversation: (id: string) =>
    request<void>(`/conversations/${id}`, { method: "DELETE" }),
  cloneConversation: (id: string) =>
    request<ConversationSummary>(`/conversations/${id}/clone`, {
      method: "POST",
    }),
  shares: (id: string) =>
    request<ConversationShare[]>(`/conversations/${id}/shares`),
  setShares: (id: string, teamIds: string[]) =>
    request<ConversationShare[]>(`/conversations/${id}/shares`, {
      method: "PUT",
      body: JSON.stringify({ team_ids: teamIds }),
    }),
  createReport: (conversationId: string, products: string[]) =>
    request<Report>(`/conversations/${conversationId}/reports`, {
      method: "POST",
      body: JSON.stringify({ products }),
    }),
  reportDownloadUrl: (reportId: string) =>
    `${API_BASE}/reports/${reportId}/download.md`,
  teams: () => request<TeamInfo[]>("/teams"),
  teamMembers: (id: string) =>
    request<TeamMember[]>(`/teams/${id}/members`),
  updateMemberRole: (teamId: string, userId: string, role: string) =>
    request<TeamMember>(`/teams/${teamId}/members/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),
  createInvitation: (
    teamId: string,
    role: string,
    maxUses = 1,
    expiresInDays = 7,
  ) =>
    request<InvitationCreated>(`/teams/${teamId}/invitations`, {
      method: "POST",
      body: JSON.stringify({
        role,
        max_uses: maxUses,
        expires_in_days: expiresInDays,
      }),
    }),
  adminUsers: () => request<AdminUser[]>("/admin/users"),
  updateAdminUser: (id: string, payload: Record<string, string>) =>
    request<AdminUser>(`/admin/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  resetAdminUserPassword: (id: string) =>
    request<AdminPasswordReset>(`/admin/users/${id}/reset-password`, {
      method: "POST",
    }),
  adminTeams: () => request<AdminTeam[]>("/admin/teams"),
  createAdminTeam: (payload: Record<string, string>) =>
    request<AdminTeam>("/admin/teams", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  archiveTeam: (id: string) =>
    request<AdminTeam>(`/admin/teams/${id}/archive`, { method: "POST" }),
  restoreTeam: (id: string) =>
    request<AdminTeam>(`/admin/teams/${id}/restore`, { method: "POST" }),
  audit: () => request<AuditItem[]>("/admin/audit"),
  dataOverview: () => request<DataOverview>("/admin/data/overview"),
  dataDocuments: (filters: DocumentQuery) =>
    request<DataDocumentPage>(
      `/admin/data/documents?${buildDocumentQuery(filters)}`,
    ),
  dataDocument: (id: string) =>
    request<DataDocumentDetail>(`/admin/data/documents/${id}`),
  updateDataDocument: (
    id: string,
    payload: { title?: string; section?: string; status?: string },
  ) =>
    request<DataDocument>(`/admin/data/documents/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  dataJobs: () => request<IngestJob[]>("/admin/data/jobs"),
  dataSources: () => request<DataSource[]>("/admin/data/sources"),
  runCrawler: (id: string, maxPages = 60) =>
    request<IngestJob>(`/admin/data/sources/${id}/run`, {
      method: "POST",
      body: JSON.stringify({ max_pages: maxPages }),
    }),
  rebuildDataIndex: () =>
    request<IngestJob>("/admin/data/index/rebuild", { method: "POST" }),
  uploadData: (file: File, fields: Record<string, string>) => {
    const body = new FormData();
    body.set("file", file);
    for (const [key, value] of Object.entries(fields)) {
      body.set(key, value);
    }
    return request<IngestJob>("/admin/data/uploads", {
      method: "POST",
      body,
    });
  },
};

function dispatchSseBlock(block: string, callbacks: StreamCallbacks): void {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (!dataLines.length) {
    return;
  }
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
  } catch {
    callbacks.onError?.("invalid_event", "服务端返回了无法解析的事件");
    return;
  }
  if (event === "stage") {
    callbacks.onStage?.(String(data.stage || ""), String(data.message || ""));
  } else if (event === "token") {
    callbacks.onToken?.(String(data.delta || ""));
  } else if (event === "citations") {
    callbacks.onCitations?.((data.citations || []) as Citation[]);
  } else if (event === "warning") {
    callbacks.onWarning?.(String(data.code || ""), String(data.message || ""));
  } else if (event === "done") {
    callbacks.onDone?.(data);
  } else if (event === "error") {
    const message = formatRequestError(
      String(data.message || "流式请求失败"),
      String(data.request_id || ""),
    );
    callbacks.onError?.(
      String(data.code || "stream_failed"),
      message,
    );
  }
}

export async function streamMessage(
  conversationId: string,
  payload: { content: string; products: string[]; sections: string[] },
  callbacks: StreamCallbacks,
): Promise<void> {
  const response = await fetch(
    `${API_BASE}/conversations/${conversationId}/messages/stream`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok || !response.body) {
    let detail = `请求失败 (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail || detail;
    } catch {
      // Keep the status-based message.
    }
    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let separator = buffer.search(/\r?\n\r?\n/);
    while (separator >= 0) {
      const block = buffer.slice(0, separator);
      buffer = buffer.slice(separator + (buffer[separator] === "\r" ? 4 : 2));
      dispatchSseBlock(block, callbacks);
      separator = buffer.search(/\r?\n\r?\n/);
    }
    if (done) {
      if (buffer.trim()) {
        dispatchSseBlock(buffer, callbacks);
      }
      break;
    }
  }
}
