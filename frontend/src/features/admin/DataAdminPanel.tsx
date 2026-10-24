import {
  App as AntApp,
  Button,
  Descriptions,
  Form,
  Input,
  Modal,
  Progress,
  Select,
  Table,
  Tag,
  Upload,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../../api/client";
import {
  canRunCrawler,
  jobStatusLabel,
  type DocumentQuery,
} from "../../lib/dataAdmin";
import type {
  DataDocument,
  DataOverview,
  DataSource,
  IngestJob,
} from "../../types";

const PRODUCT_OPTIONS = [
  "东煌纪",
  "战斗吧精灵",
  "乐趣萌宠",
  "宝可梦 朱／紫",
];

function statusColor(status: string): string {
  return (
    {
      active: "green",
      archived: "default",
      queued: "gold",
      running: "blue",
      completed: "green",
      failed: "red",
    }[status] || "default"
  );
}

function sourceName(source: DataSource): string {
  return (
    {
      donghuangji: "东煌纪 · 官网全量",
      lqmc: "乐趣萌宠 · 官网",
      pkmbattle: "战斗吧精灵 · 官网",
      pokemon_sv: "宝可梦朱紫 · 官方图鉴",
    }[source.crawler_key || ""] || source.name
  );
}

export function DataAdminPanel() {
  const { message, modal } = AntApp.useApp();
  const [overview, setOverview] = useState<DataOverview | null>(null);
  const [documents, setDocuments] = useState<DataDocument[]>([]);
  const [documentTotal, setDocumentTotal] = useState(0);
  const [jobs, setJobs] = useState<IngestJob[]>([]);
  const [sources, setSources] = useState<DataSource[]>([]);
  const [filters, setFilters] = useState<DocumentQuery>({
    status: "active",
    page: 1,
    pageSize: 20,
  });
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [detail, setDetail] = useState<
    (DataDocument & { content: string }) | null
  >(null);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    try {
      const [overviewData, documentPage, jobRows, sourceRows] =
        await Promise.all([
          api.dataOverview(),
          api.dataDocuments(filters),
          api.dataJobs(),
          api.dataSources(),
        ]);
      setOverview(overviewData);
      setDocuments(documentPage.items);
      setDocumentTotal(documentPage.total);
      setJobs(jobRows);
      setSources(sourceRows);
    } catch (reason) {
      message.error((reason as Error).message);
    }
  }, [filters, message]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!jobs.some((job) => ["queued", "running"].includes(job.status))) {
      return;
    }
    const timer = window.setInterval(() => void load(), 4000);
    return () => window.clearInterval(timer);
  }, [jobs, load]);

  const products = useMemo(
    () =>
      Array.from(
        new Set([
          ...PRODUCT_OPTIONS,
          ...(overview?.products.map((item) => item.product) || []),
        ]),
      ),
    [overview],
  );

  const upload = async () => {
    try {
      const values = await form.validateFields();
      if (!pendingFile) {
        message.warning("请先选择文件");
        return;
      }
      setUploading(true);
      const job = await api.uploadData(pendingFile, values);
      message.success(`上传任务 ${job.id.slice(0, 8)} 已进入后台队列`);
      setUploadOpen(false);
      setPendingFile(null);
      form.resetFields();
      await load();
    } catch (reason) {
      if (reason instanceof Error) message.error(reason.message);
    } finally {
      setUploading(false);
    }
  };

  const runCrawler = async (source: DataSource) => {
    try {
      await api.runCrawler(source.id, 60);
      message.success(`${sourceName(source)} 已开始增量重抓`);
      await load();
    } catch (reason) {
      message.error((reason as Error).message);
    }
  };

  const toggleDocument = (document: DataDocument) => {
    const archiving = document.status === "active";
    modal.confirm({
      title: archiving ? "归档这份资料？" : "恢复这份资料？",
      content: archiving
        ? "归档后问答和 MCP 不再检索该文档，原始记录仍保留。"
        : "恢复后会重新加入检索索引。",
      okText: archiving ? "归档" : "恢复",
      okButtonProps: { danger: archiving },
      async onOk() {
        await api.updateDataDocument(document.doc_id, {
          status: archiving ? "archived" : "active",
        });
        await load();
      },
    });
  };

  const showDetail = async (document: DataDocument) => {
    try {
      setDetail(await api.dataDocument(document.doc_id));
    } catch (reason) {
      message.error((reason as Error).message);
    }
  };

  const rebuild = async () => {
    try {
      await api.rebuildDataIndex();
      message.success("索引重建任务已提交");
      await load();
    } catch (reason) {
      message.error((reason as Error).message);
    }
  };

  return (
    <div className="data-admin">
      <div className="data-metrics">
        {[
          ["活动资料", overview?.active_documents || 0, "篇"],
          ["检索分块", overview?.chunks || 0, "块"],
          ["已归档", overview?.archived_documents || 0, "篇"],
          ["运行任务", jobs.filter((job) => ["queued", "running"].includes(job.status)).length, "个"],
        ].map(([label, value, unit]) => (
          <div className="data-metric" key={String(label)}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{unit}</small>
          </div>
        ))}
      </div>

      <section className="data-section">
        <div className="data-section-head">
          <div>
            <span className="eyebrow">INGESTION</span>
            <h3>资料入库</h3>
          </div>
          <div className="data-actions">
            <Button onClick={() => void rebuild()}>重建索引</Button>
            <Button type="primary" onClick={() => setUploadOpen(true)}>
              上传文件
            </Button>
          </div>
        </div>
        <div className="crawler-grid">
          {sources.map((source) => (
            <article className="crawler-card" key={source.id}>
              <div>
                <strong>{sourceName(source)}</strong>
                <span>{source.product}</span>
              </div>
              <p>
                {source.last_run_at
                  ? `上次重抓 ${new Date(source.last_run_at).toLocaleString("zh-CN")}`
                  : "尚未通过当前系统重抓"}
              </p>
              <Button
                size="small"
                disabled={!canRunCrawler(source.status, source.active_job_id)}
                onClick={() => void runCrawler(source)}
              >
                {source.active_job_id ? "抓取中" : "增量重抓"}
              </Button>
            </article>
          ))}
        </div>
      </section>

      <section className="data-section">
        <div className="data-section-head">
          <div>
            <span className="eyebrow">DOCUMENTS</span>
            <h3>资料库</h3>
          </div>
          <span className="data-total">共 {documentTotal} 篇</span>
        </div>
        <div className="data-filter-row">
          <Input.Search
            allowClear
            placeholder="搜索标题、文件名或文档 ID"
            onSearch={(value) =>
              setFilters((current) => ({ ...current, q: value, page: 1 }))
            }
          />
          <Select
            allowClear
            placeholder="全部产品"
            options={products.map((value) => ({ value, label: value }))}
            onChange={(value) =>
              setFilters((current) => ({
                ...current,
                product: value || "",
                page: 1,
              }))
            }
          />
          <Select
            value={filters.status || "active"}
            options={[
              { value: "active", label: "活动资料" },
              { value: "archived", label: "已归档" },
            ]}
            onChange={(value) =>
              setFilters((current) => ({ ...current, status: value, page: 1 }))
            }
          />
        </div>
        <Table
          rowKey="doc_id"
          dataSource={documents}
          pagination={{
            current: filters.page,
            pageSize: filters.pageSize,
            total: documentTotal,
            showSizeChanger: false,
            onChange: (page) =>
              setFilters((current) => ({ ...current, page })),
          }}
          columns={[
            {
              title: "资料",
              render: (_: unknown, row: DataDocument) => (
                <button
                  type="button"
                  className="document-title"
                  onClick={() => void showDetail(row)}
                >
                  <strong>{row.title}</strong>
                  <small>{row.original_name || row.doc_id}</small>
                </button>
              ),
            },
            { title: "产品", dataIndex: "product", width: 130 },
            { title: "栏目", dataIndex: "section", width: 130 },
            {
              title: "来源",
              dataIndex: "origin",
              width: 90,
              render: (value: string) => <Tag>{value}</Tag>,
            },
            { title: "分块", dataIndex: "chunk_count", width: 70 },
            {
              title: "状态",
              dataIndex: "status",
              width: 90,
              render: (value: string) => (
                <Tag color={statusColor(value)}>{value === "active" ? "活动" : "归档"}</Tag>
              ),
            },
            {
              title: "操作",
              width: 100,
              render: (_: unknown, row: DataDocument) => (
                <Button size="small" onClick={() => toggleDocument(row)}>
                  {row.status === "active" ? "归档" : "恢复"}
                </Button>
              ),
            },
          ]}
        />
      </section>

      <section className="data-section">
        <div className="data-section-head">
          <div>
            <span className="eyebrow">BACKGROUND JOBS</span>
            <h3>任务队列</h3>
          </div>
        </div>
        <Table
          rowKey="id"
          dataSource={jobs}
          pagination={{ pageSize: 8 }}
          columns={[
            {
              title: "任务",
              render: (_: unknown, job: IngestJob) => (
                <div className="job-title">
                  <strong>
                    {job.title || job.original_name || job.kind}
                  </strong>
                  <small>{job.id}</small>
                </div>
              ),
            },
            { title: "类型", dataIndex: "kind", width: 90 },
            {
              title: "状态",
              width: 100,
              render: (_: unknown, job: IngestJob) => (
                <Tag color={statusColor(job.status)}>
                  {jobStatusLabel(job.status)}
                </Tag>
              ),
            },
            {
              title: "进度",
              width: 180,
              render: (_: unknown, job: IngestJob) => (
                <Progress
                  size="small"
                  percent={job.progress}
                  status={job.status === "failed" ? "exception" : undefined}
                />
              ),
            },
            {
              title: "说明",
              dataIndex: "message",
              ellipsis: true,
              render: (value: string, job: IngestJob) =>
                job.error ? <span className="job-error">{job.error}</span> : value,
            },
            {
              title: "创建时间",
              dataIndex: "created_at",
              width: 170,
              render: (value: string) =>
                new Date(value).toLocaleString("zh-CN"),
            },
          ]}
        />
      </section>

      <Modal
        title="上传资料"
        open={uploadOpen}
        confirmLoading={uploading}
        okText="提交入库"
        onOk={() => void upload()}
        onCancel={() => setUploadOpen(false)}
      >
        <p className="modal-hint">
          支持 PDF、Word、Excel、CSV、Markdown 和 TXT，单文件不超过 10 MB。
          原始文件存入 MinIO，解析、切块和向量化由后台任务完成。
        </p>
        <Form form={form} layout="vertical">
          <Form.Item
            name="product"
            label="所属产品"
            rules={[{ required: true }]}
            initialValue="东煌纪"
          >
            <Select options={products.map((value) => ({ value, label: value }))} />
          </Form.Item>
          <Form.Item
            name="section"
            label="栏目"
            rules={[{ required: true }]}
            initialValue="产品资料"
          >
            <Input />
          </Form.Item>
          <Form.Item name="title" label="显示标题（可选）">
            <Input placeholder="默认使用文件名或 Markdown 一级标题" />
          </Form.Item>
          <Form.Item label="文件" required>
            <Upload
              maxCount={1}
              beforeUpload={(file) => {
                setPendingFile(file);
                return false;
              }}
              onRemove={() => setPendingFile(null)}
            >
              <Button>选择文件</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={detail?.title}
        open={Boolean(detail)}
        width={900}
        footer={null}
        onCancel={() => setDetail(null)}
      >
        {detail && (
          <>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="产品">{detail.product}</Descriptions.Item>
              <Descriptions.Item label="栏目">{detail.section}</Descriptions.Item>
              <Descriptions.Item label="来源">{detail.origin}</Descriptions.Item>
              <Descriptions.Item label="分块">{detail.chunk_count}</Descriptions.Item>
              <Descriptions.Item label="文档 ID" span={2}>
                {detail.doc_id}
              </Descriptions.Item>
            </Descriptions>
            <pre className="document-preview">{detail.content}</pre>
          </>
        )}
      </Modal>
    </div>
  );
}
