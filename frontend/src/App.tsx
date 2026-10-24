import {
  App as AntApp,
  Button,
  Checkbox,
  ConfigProvider,
  Empty,
  Input,
  Modal,
  Popover,
  Spin,
  Tag,
  Tooltip,
} from "antd";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, streamMessage } from "./api/client";
import { MarkdownMessage } from "./components/MarkdownMessage";
import { ShareDialog } from "./components/ShareDialog";
import { TopNav, type AppView } from "./components/TopNav";
import { AdminPage } from "./features/admin/AdminPage";
import { ForcedPasswordChange } from "./features/auth/ForcedPasswordChange";
import { LoginPage } from "./features/auth/LoginPage";
import { TeamsPage } from "./features/teams/TeamsPage";
import { canWriteConversation } from "./lib/sharing";
import type {
  Catalog,
  Citation,
  ConversationDetail,
  ConversationSummary,
  Report,
  TeamInfo,
  UserInfo,
} from "./types";

const EXAMPLES = [
  "东煌纪的灵兽属性克制关系是什么？",
  "对比东煌纪与乐趣萌宠的养成体系",
  "东煌纪和竞品的版本更新节奏有什么差异？",
];

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
}

function Workspace({ user }: { user: UserInfo }) {
  const { message, modal } = AntApp.useApp();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [teams, setTeams] = useState<TeamInfo[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [scope, setScope] = useState<"mine" | "shared">("mine");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [products, setProducts] = useState<string[]>(["东煌纪"]);
  const [sections, setSections] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [liveQuestion, setLiveQuestion] = useState("");
  const [liveText, setLiveText] = useState("");
  const [liveCitations, setLiveCitations] = useState<Citation[]>([]);
  const [stage, setStage] = useState("");
  const [warning, setWarning] = useState("");
  const [activeCitation, setActiveCitation] = useState<string | null>(null);
  const [editing, setEditing] = useState<ConversationSummary | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [shareOpen, setShareOpen] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(
    async (nextScope = scope) => {
      setConversations(await api.conversations(nextScope));
    },
    [scope],
  );

  const loadConversation = useCallback(async (id: string) => {
    const next = await api.conversation(id);
    setActiveId(id);
    setDetail(next);
    setLiveQuestion("");
    setLiveText("");
    setLiveCitations([]);
    setWarning("");
    setActiveCitation(null);
  }, []);

  useEffect(() => {
    Promise.all([api.catalog(), api.conversations(scope), api.teams()])
      .then(async ([catalogData, conversationData, teamData]) => {
        setCatalog(catalogData);
        setTeams(teamData);
        setConversations(conversationData);
        if (conversationData.length) {
          await loadConversation(conversationData[0].id);
        } else {
          setActiveId(null);
          setDetail(null);
        }
      })
      .catch((reason: Error) => message.error(reason.message))
      .finally(() => setLoading(false));
  }, [loadConversation, message, scope]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [detail, liveText]);

  const sectionOptions = useMemo(
    () => [
      ...new Set(
        catalog?.products
          .filter((product) => products.includes(product.name))
          .flatMap((product) => product.sections) || [],
      ),
    ].sort(),
    [catalog, products],
  );
  const citations =
    liveCitations.length
      ? liveCitations
      : [...(detail?.messages || [])]
          .reverse()
          .find((item) => item.role === "assistant")?.citations || [];
  const canWrite = canWriteConversation(detail?.access_role);
  const canShare = canWrite && Boolean(activeId);

  const createConversation = async () => {
    const created = await api.createConversation();
    setScope("mine");
    setConversations((current) => [created, ...current]);
    setActiveId(created.id);
    setDetail({ ...created, messages: [] });
    return created.id;
  };

  const send = async () => {
    const content = input.trim();
    if (!content || streaming) return;
    if (detail && !canWrite) {
      message.warning("共享会话仅可只读访问，请先复制为个人会话");
      return;
    }
    let id = activeId;
    try {
      if (!id) id = await createConversation();
      setInput("");
      setLiveQuestion(content);
      setLiveText("");
      setLiveCitations([]);
      setWarning("");
      setStreaming(true);
      setStage("正在检索资料");
      await streamMessage(
        id,
        { content, products, sections },
        {
          onStage: (_value, label) => setStage(label),
          onToken: (delta) => setLiveText((value) => value + delta),
          onCitations: setLiveCitations,
          onWarning: (_code, value) => setWarning(value),
          onError: (_code, value) => setWarning(value),
        },
      );
      await loadConversation(id);
      await refresh();
    } catch (reason) {
      setWarning((reason as Error).message);
    } finally {
      setStreaming(false);
      setStage("");
    }
  };

  const clone = async () => {
    if (!activeId) return;
    try {
      const copied = await api.cloneConversation(activeId);
      setScope("mine");
      setActiveId(copied.id);
      setConversations((current) => [copied, ...current]);
      await loadConversation(copied.id);
      message.success("已创建个人副本");
    } catch (reason) {
      message.error((reason as Error).message);
    }
  };

  const remove = (item: ConversationSummary) => {
    modal.confirm({
      title: "删除这份分析卷宗？",
      content: "会话、引用和报告将一起删除。",
      okText: "删除",
      okButtonProps: { danger: true },
      async onOk() {
        await api.deleteConversation(item.id);
        setConversations((rows) => rows.filter((row) => row.id !== item.id));
        if (activeId === item.id) {
          setActiveId(null);
          setDetail(null);
        }
      },
    });
  };

  const rename = async () => {
    if (!editing || !editTitle.trim()) return;
    try {
      const updated = await api.renameConversation(editing.id, editTitle.trim());
      setConversations((rows) =>
        rows.map((row) => (row.id === updated.id ? { ...row, ...updated } : row)),
      );
      if (activeId === editing.id) {
        setDetail((current) =>
          current ? { ...current, title: updated.title } : current,
        );
      }
      setEditing(null);
    } catch (reason) {
      message.error((reason as Error).message);
    }
  };

  const generateReport = async () => {
    if (!activeId || !canWrite) return;
    setReportLoading(true);
    try {
      setReport(await api.createReport(activeId, products));
    } catch (reason) {
      message.error((reason as Error).message);
    } finally {
      setReportLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="boot-screen">
        <div className="brand-seal">煌</div>
        <Spin />
        <p>正在展开你的分析空间...</p>
      </div>
    );
  }

  return (
    <>
      <main className="app-shell analysis-workspace">
        <aside className="conversation-sidebar">
          <div className="brand-block">
            <div className="brand-seal">煌</div>
            <div>
              <div className="brand-kicker">YOUR DOSSIERS</div>
              <div className="brand-name">分析卷宗</div>
            </div>
          </div>
          <Button
            className="new-analysis"
            type="primary"
            onClick={() => void createConversation().catch((error: Error) =>
              message.error(error.message),
            )}
          >
            ＋ 新建分析
          </Button>
          <div className="scope-tabs">
            <button
              type="button"
              className={scope === "mine" ? "active" : ""}
              onClick={() => setScope("mine")}
            >
              我的
            </button>
            <button
              type="button"
              className={scope === "shared" ? "active" : ""}
              onClick={() => setScope("shared")}
            >
              团队共享
            </button>
          </div>
          <div className="conversation-list">
            {!conversations.length && (
              <p className="sidebar-empty">
                {scope === "mine" ? "还没有分析记录。" : "还没有分享给你的会话。"}
              </p>
            )}
            {conversations.map((item) => (
              <div
                key={item.id}
                className={`conversation-item ${activeId === item.id ? "active" : ""}`}
              >
                <button
                  type="button"
                  className="conversation-main"
                  onClick={() => void loadConversation(item.id)}
                >
                  <span>{item.title}</span>
                  <small>{formatTime(item.updated_at)}</small>
                </button>
                {item.access_role === "owner" && (
                  <div className="conversation-actions">
                    <Tooltip title="重命名">
                      <button
                        type="button"
                        onClick={() => {
                          setEditing(item);
                          setEditTitle(item.title);
                        }}
                      >
                        改
                      </button>
                    </Tooltip>
                    <Tooltip title="删除">
                      <button type="button" onClick={() => remove(item)}>
                        删
                      </button>
                    </Tooltip>
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="sidebar-foot">
            <span>当前用户</span><b>{user.display_name}</b>
            <span>资料基线</span><b>{catalog?.documents || 0} 篇</b>
          </div>
        </aside>

        <section className="analysis-panel">
          <header className="analysis-header">
            <div>
              <span className="eyebrow">
                {detail?.access_role === "read" ? "TEAM SHARED · READ ONLY" : "ANALYSIS"}
              </span>
              <h1>{detail?.title || "新的分析"}</h1>
            </div>
            <div className="header-actions">
              {canShare && <Button onClick={() => setShareOpen(true)}>共享</Button>}
              {detail?.access_role === "read" && (
                <Button type="primary" onClick={() => void clone()}>
                  复制到我的会话
                </Button>
              )}
              {canWrite && (
                <Button loading={reportLoading} onClick={() => void generateReport()}>
                  生成报告
                </Button>
              )}
            </div>
          </header>

          <div className="filter-bar">
            <span className="filter-label">分析范围</span>
            <div className="product-chips">
              {catalog?.products.map((product) => (
                <button
                  key={product.name}
                  type="button"
                  className={products.includes(product.name) ? "selected" : ""}
                  onClick={() =>
                    setProducts((current) =>
                      current.includes(product.name)
                        ? current.length === 1
                          ? current
                          : current.filter((name) => name !== product.name)
                        : [...current, product.name],
                    )
                  }
                  disabled={!canWrite}
                >
                  {product.name}<small>{product.chunks}</small>
                </button>
              ))}
            </div>
            <Button
              size="small"
              disabled={!canWrite}
              onClick={() => setProducts(catalog?.products.map((item) => item.name) || [])}
            >
              全竞品
            </Button>
            <Popover
              trigger="click"
              content={
                <div className="section-picker">
                  <Checkbox
                    checked={sections.length === 0}
                    onChange={() => setSections([])}
                  >
                    全部栏目
                  </Checkbox>
                  {sectionOptions.map((section) => (
                    <Checkbox
                      key={section}
                      checked={sections.includes(section)}
                      onChange={(event) =>
                        setSections((current) =>
                          event.target.checked
                            ? [...current, section]
                            : current.filter((item) => item !== section),
                        )
                      }
                    >
                      {section}
                    </Checkbox>
                  ))}
                </div>
              }
            >
              <Button size="small" disabled={!canWrite}>
                栏目 {sections.length || "全部"}
              </Button>
            </Popover>
          </div>

          <div className="chat-scroll">
            {!detail?.messages.length && !liveQuestion && (
              <div className="welcome-panel">
                <span className="welcome-mark">问</span>
                <h2>从证据出发，看清竞品格局</h2>
                <p>每个 S 编号都能在右侧定位原文；团队共享内容为只读。</p>
                <div className="example-list">
                  {EXAMPLES.map((question) => (
                    <button type="button" key={question} onClick={() => setInput(question)}>
                      {question}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {detail?.messages.map((item) => (
              <article key={item.id} className={`message ${item.role}`}>
                <div className="message-role">
                  {item.role === "user" ? "你" : "情报分析"}
                  {item.role === "assistant" && (
                    <Tag bordered={false}>{item.generation_status}</Tag>
                  )}
                </div>
                {item.role === "user" ? (
                  <p className="user-content">{item.content}</p>
                ) : (
                  <MarkdownMessage
                    content={item.content}
                    onCitationClick={(key) => {
                      setActiveCitation(key);
                      document
                        .getElementById(`citation-${key}`)
                        ?.scrollIntoView({ behavior: "smooth", block: "center" });
                    }}
                  />
                )}
              </article>
            ))}
            {liveQuestion && (
              <article className="message user live">
                <div className="message-role">你</div>
                <p className="user-content">{liveQuestion}</p>
              </article>
            )}
            {(liveQuestion || streaming) && (
              <article className="message assistant live">
                <div className="message-role">情报分析</div>
                {stage && <div className="stage-line"><span />{stage}</div>}
                {liveText ? (
                  <MarkdownMessage content={liveText} />
                ) : (
                  <div className="thinking-lines"><i /><i /><i /></div>
                )}
                {warning && <div className="warning-line">{warning}</div>}
              </article>
            )}
            <div ref={endRef} />
          </div>

          <div className="composer">
            <Input.TextArea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
              autoSize={{ minRows: 2, maxRows: 6 }}
              maxLength={2000}
              disabled={streaming || !canWrite}
              placeholder={
                canWrite
                  ? "输入竞品问题，Enter 发送，Shift + Enter 换行..."
                  : "共享会话为只读，请复制到个人会话后继续分析"
              }
            />
            <div className="composer-foot">
              <span>仅依据当前资料回答，不推测未公开数据</span>
              <Button
                type="primary"
                disabled={!input.trim() || streaming || !canWrite}
                loading={streaming}
                onClick={() => void send()}
              >
                发起分析
              </Button>
            </div>
          </div>
        </section>

        <aside className="evidence-panel">
          <header className="evidence-header">
            <div>
              <span className="eyebrow">EVIDENCE DOSSIER</span>
              <h2>证据卷宗</h2>
            </div>
            <span className="evidence-count">{citations.length}</span>
          </header>
          <div className="evidence-list">
            {!citations.length ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="回答生成后，本轮证据会陈列在这里"
              />
            ) : (
              citations.map((citation) => (
                <article
                  id={`citation-${citation.citation_key}`}
                  key={citation.citation_key}
                  className={`evidence-card ${activeCitation === citation.citation_key ? "active" : ""}`}
                  onClick={() => setActiveCitation(citation.citation_key)}
                >
                  <div className="evidence-card-head">
                    <span className="citation-key">{citation.citation_key}</span>
                    <span className="evidence-score">{citation.score.toFixed(3)}</span>
                  </div>
                  <strong>{citation.title}</strong>
                  <div className="evidence-meta">
                    <span>{citation.product}</span><span>{citation.section}</span>
                  </div>
                  <p className={activeCitation === citation.citation_key ? "expanded" : ""}>
                    {citation.snippet}
                  </p>
                  <div className="evidence-foot">
                    <span>{citation.used_in_answer ? "已用于回答" : "候选证据"}</span>
                    {citation.url && (
                      <a href={citation.url} target="_blank" rel="noreferrer noopener">
                        查看来源 ↗
                      </a>
                    )}
                  </div>
                </article>
              ))
            )}
          </div>
        </aside>
      </main>

      <ShareDialog
        open={shareOpen}
        conversationId={activeId}
        teams={teams}
        onClose={() => setShareOpen(false)}
        onSaved={() => message.success("共享设置已更新")}
      />
      <Modal
        title="重命名分析卷宗"
        open={Boolean(editing)}
        okText="保存"
        onOk={() => void rename()}
        onCancel={() => setEditing(null)}
      >
        <Input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} />
      </Modal>
      {report && (
        <div className="report-overlay">
          <div className="report-sheet">
            <header>
              <div><span className="eyebrow">INTELLIGENCE REPORT</span><h2>{report.title}</h2></div>
              <div className="report-actions">
                <a className="ant-btn ant-btn-default" href={api.reportDownloadUrl(report.id)}>
                  下载 Markdown
                </a>
                <Button type="primary" onClick={() => setReport(null)}>关闭</Button>
              </div>
            </header>
            <div className="report-html markdown-content" dangerouslySetInnerHTML={{ __html: report.html }} />
          </div>
        </div>
      )}
    </>
  );
}

function AuthenticatedApp({ initialUser }: { initialUser: UserInfo }) {
  const [user, setUser] = useState(initialUser);
  const [view, setView] = useState<AppView>("analysis");
  if (user.must_change_password) {
    return (
      <ForcedPasswordChange
        user={user}
        onComplete={() => window.location.reload()}
      />
    );
  }
  const logout = async () => {
    await api.logout();
    window.location.reload();
  };
  return (
    <div className="app-root">
      <TopNav user={user} view={view} onChange={setView} onLogout={() => void logout()} />
      <div className="app-view">
        {view === "analysis" && <Workspace user={user} />}
        {view === "teams" && <TeamsPage user={user} />}
        {view === "admin" && user.platform_role === "admin" && <AdminPage />}
      </div>
    </div>
  );
}

function AuthGate() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [checking, setChecking] = useState(true);
  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
  }, []);
  if (checking) {
    return (
      <div className="boot-screen">
        <div className="brand-seal">煌</div>
        <Spin />
        <p>正在确认登录状态...</p>
      </div>
    );
  }
  return user ? <AuthenticatedApp initialUser={user} /> : <LoginPage onAuthenticated={setUser} />;
}

export default function App() {
  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#3f6b58",
          colorInfo: "#3f6b58",
          colorText: "#2b2d27",
          colorBgBase: "#f5efe3",
          borderRadius: 9,
          fontFamily:
            '"Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif',
        },
      }}
    >
      <AntApp>
        <AuthGate />
      </AntApp>
    </ConfigProvider>
  );
}
