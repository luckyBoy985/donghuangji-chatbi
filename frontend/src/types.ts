export interface ProductInfo {
  name: string;
  documents: number;
  chunks: number;
  sections: string[];
}

export interface Catalog {
  documents: number;
  chunks: number;
  embedding_dim: number;
  products: ProductInfo[];
}

export interface Citation {
  citation_key: string;
  chunk_id: string;
  doc_id: string;
  product: string;
  section: string;
  title: string;
  source_type: string;
  published_at: string;
  url: string;
  snippet: string;
  score: number;
  used_in_answer: boolean;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: string;
  generation_status: string;
  model: string;
  created_at: string;
  citations: Citation[];
}

export interface ConversationSummary {
  id: string;
  owner_user_id: string;
  access_role: "owner" | "read";
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: Message[];
}

export interface Report {
  id: string;
  conversation_id: string;
  title: string;
  products: string[];
  markdown: string;
  html: string;
  created_at: string;
}

export interface StreamCallbacks {
  onStage?: (stage: string, message: string) => void;
  onToken?: (delta: string) => void;
  onCitations?: (citations: Citation[]) => void;
  onWarning?: (code: string, message: string) => void;
  onDone?: (payload: Record<string, unknown>) => void;
  onError?: (code: string, message: string) => void;
}

export interface UserTeam {
  id: string;
  name: string;
  role: "owner" | "admin" | "member";
}

export interface UserInfo {
  id: string;
  username: string;
  display_name: string;
  platform_role: "admin" | "user";
  status: string;
  must_change_password: boolean;
  teams: UserTeam[];
}

export interface TeamInfo {
  id: string;
  name: string;
  description: string;
  role: "owner" | "admin" | "member";
  member_count: number;
}

export interface TeamMember {
  user_id: string;
  username: string;
  display_name: string;
  role: "owner" | "admin" | "member";
  created_at: string;
}

export interface ConversationShare {
  id: string;
  conversation_id: string;
  team_id: string;
  team_name: string;
  created_at: string;
}

export interface InvitationCreated {
  id: string;
  code: string;
  team_id: string;
  role: string;
  max_uses: number;
  used_count: number;
  expires_at: string;
}

export interface AdminUser {
  id: string;
  username: string;
  display_name: string;
  platform_role: "admin" | "user";
  status: "active" | "disabled";
  must_change_password: boolean;
  created_at: string;
}

export interface AdminPasswordReset {
  user_id: string;
  temporary_password: string;
}

export interface AdminTeam {
  id: string;
  name: string;
  description: string;
  status: "active" | "archived";
  owner_count: number;
  member_count: number;
  created_at: string;
}

export interface AuditItem {
  id: string;
  actor_user_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string;
  result: string;
  metadata: Record<string, unknown>;
  ip_address: string;
  created_at: string;
}

export interface IngestJob {
  id: string;
  kind: "upload" | "crawl" | "reindex";
  status: "queued" | "running" | "completed" | "failed";
  product: string;
  section: string;
  title: string;
  original_name: string;
  object_key: string;
  source_id: string | null;
  progress: number;
  message: string;
  stats: Record<string, unknown>;
  error: string;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface DataDocument {
  doc_id: string;
  product: string;
  source_type: string;
  section: string;
  title: string;
  published_at: string;
  url: string;
  original_name: string;
  content_hash: string;
  chars: number;
  status: "active" | "archived";
  origin: "baseline" | "upload" | "crawler";
  source_id: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface DataDocumentDetail extends DataDocument {
  content: string;
}

export interface DataDocumentPage {
  items: DataDocument[];
  total: number;
  page: number;
  page_size: number;
}

export interface DataSource {
  id: string;
  name: string;
  kind: string;
  crawler_key: string | null;
  product: string;
  status: string;
  last_run_at: string | null;
  active_job_id: string | null;
}

export interface DataOverview {
  documents: number;
  active_documents: number;
  archived_documents: number;
  chunks: number;
  products: Array<{
    product: string;
    documents: number;
    chars: number;
  }>;
  recent_jobs: IngestJob[];
}
