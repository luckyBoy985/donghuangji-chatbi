import {
  App as AntApp,
  Button,
  Form,
  Input,
  Modal,
  Select,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useEffect, useState } from "react";

import { api } from "../../api/client";
import type {
  AdminPasswordReset,
  AdminTeam,
  AdminUser,
  AuditItem,
} from "../../types";
import { DataAdminPanel } from "./DataAdminPanel";

export function AdminPage() {
  const { message } = AntApp.useApp();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [teams, setTeams] = useState<AdminTeam[]>([]);
  const [audit, setAudit] = useState<AuditItem[]>([]);
  const [teamModal, setTeamModal] = useState(false);
  const [resetResult, setResetResult] =
    useState<AdminPasswordReset | null>(null);
  const [form] = Form.useForm();

  const load = async () => {
    try {
      const [userRows, teamRows, auditRows] = await Promise.all([
        api.adminUsers(),
        api.adminTeams(),
        api.audit(),
      ]);
      setUsers(userRows);
      setTeams(teamRows);
      setAudit(auditRows);
    } catch (reason) {
      message.error((reason as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const disableUser = async (user: AdminUser) => {
    try {
      await api.updateAdminUser(user.id, {
        status: user.status === "active" ? "disabled" : "active",
      });
      await load();
    } catch (reason) {
      message.error((reason as Error).message);
    }
  };

  const resetPassword = async (user: AdminUser) => {
    try {
      setResetResult(await api.resetAdminUserPassword(user.id));
      await load();
    } catch (reason) {
      message.error((reason as Error).message);
    }
  };

  const createTeam = async () => {
    try {
      const values = await form.validateFields();
      await api.createAdminTeam(values);
      setTeamModal(false);
      form.resetFields();
      await load();
    } catch (reason) {
      if (reason instanceof Error) message.error(reason.message);
    }
  };

  const toggleTeam = async (team: AdminTeam) => {
    try {
      if (team.status === "active") await api.archiveTeam(team.id);
      else await api.restoreTeam(team.id);
      await load();
    } catch (reason) {
      message.error((reason as Error).message);
    }
  };

  return (
    <section className="management-page">
      <header className="management-head">
        <div>
          <span className="eyebrow">PLATFORM ADMIN</span>
          <Typography.Title level={2}>平台管理</Typography.Title>
          <Typography.Paragraph type="secondary">
            管理资料入库、用户、团队与安全审计；私密会话正文仍不向管理员开放。
          </Typography.Paragraph>
        </div>
      </header>
      <Tabs
        items={[
          {
            key: "data",
            label: "数据管理",
            children: <DataAdminPanel />,
          },
          {
            key: "users",
            label: `用户 ${users.length}`,
            children: (
              <Table
                rowKey="id"
                dataSource={users}
                columns={[
                  { title: "显示名", dataIndex: "display_name" },
                  { title: "用户名", dataIndex: "username" },
                  {
                    title: "平台角色",
                    dataIndex: "platform_role",
                    render: (value: string) => <Tag>{value}</Tag>,
                  },
                  {
                    title: "状态",
                    dataIndex: "status",
                    render: (value: string) => (
                      <Tag color={value === "active" ? "green" : "red"}>
                        {value}
                      </Tag>
                    ),
                  },
                  {
                    title: "操作",
                    render: (_: unknown, user: AdminUser) => (
                      <div className="admin-user-actions">
                        <Button
                          size="small"
                          onClick={() => void resetPassword(user)}
                        >
                          重置密码
                        </Button>
                        <Button
                          size="small"
                          danger={user.status === "active"}
                          onClick={() => void disableUser(user)}
                        >
                          {user.status === "active" ? "停用" : "启用"}
                        </Button>
                      </div>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: "teams",
            label: `团队 ${teams.length}`,
            children: (
              <>
                <Button type="primary" onClick={() => setTeamModal(true)}>
                  创建团队
                </Button>
                <Table
                  style={{ marginTop: 12 }}
                  rowKey="id"
                  dataSource={teams}
                  columns={[
                    { title: "团队", dataIndex: "name" },
                    { title: "成员", dataIndex: "member_count" },
                    { title: "Owner", dataIndex: "owner_count" },
                    {
                      title: "状态",
                      dataIndex: "status",
                      render: (value: string) => (
                        <Tag color={value === "active" ? "green" : "red"}>
                          {value}
                        </Tag>
                      ),
                    },
                    {
                      title: "操作",
                      render: (_: unknown, team: AdminTeam) => (
                        <Button size="small" onClick={() => void toggleTeam(team)}>
                          {team.status === "active" ? "归档" : "恢复"}
                        </Button>
                      ),
                    },
                  ]}
                />
              </>
            ),
          },
          {
            key: "audit",
            label: "安全审计",
            children: (
              <Table
                rowKey="id"
                dataSource={audit}
                pagination={{ pageSize: 15 }}
                columns={[
                  { title: "动作", dataIndex: "action" },
                  { title: "资源", dataIndex: "resource_type" },
                  { title: "结果", dataIndex: "result" },
                  { title: "时间", dataIndex: "created_at" },
                ]}
              />
            ),
          },
        ]}
      />

      <Modal
        title="创建团队"
        open={teamModal}
        onCancel={() => setTeamModal(false)}
        onOk={() => void createTeam()}
        okText="创建"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="团队名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="团队说明">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item
            name="owner_user_id"
            label="首位 owner"
            rules={[{ required: true }]}
          >
            <Select
              options={users
                .filter((user) => user.status === "active")
                .map((user) => ({
                  value: user.id,
                  label: `${user.display_name} · ${user.username}`,
                }))}
            />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title="临时密码"
        open={Boolean(resetResult)}
        footer={
          <Button type="primary" onClick={() => setResetResult(null)}>
            我已记录
          </Button>
        }
        onCancel={() => setResetResult(null)}
      >
        <p className="modal-hint">
          临时密码只显示一次。用户登录后必须先修改密码，原会话已全部退出。
        </p>
        {resetResult && (
          <Typography.Paragraph copyable>
            <Typography.Text code>
              {resetResult.temporary_password}
            </Typography.Text>
          </Typography.Paragraph>
        )}
      </Modal>
    </section>
  );
}
