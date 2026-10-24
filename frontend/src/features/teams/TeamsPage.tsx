import {
  Alert,
  App as AntApp,
  Button,
  Modal,
  Select,
  Table,
  Tag,
  Typography,
} from "antd";
import { useEffect, useState } from "react";

import { api } from "../../api/client";
import type { InvitationCreated, TeamInfo, TeamMember, UserInfo } from "../../types";

interface Props {
  user: UserInfo;
}

export function TeamsPage({ user }: Props) {
  const { message } = AntApp.useApp();
  const [teams, setTeams] = useState<TeamInfo[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteRole, setInviteRole] = useState("member");
  const [invitation, setInvitation] = useState<InvitationCreated | null>(null);

  const selected = teams.find((team) => team.id === selectedId);
  const canManage = Boolean(selected && ["owner", "admin"].includes(selected.role));

  const loadTeams = async () => {
    const rows = await api.teams();
    setTeams(rows);
    if (!selectedId && rows.length) setSelectedId(rows[0].id);
  };

  const loadMembers = async (teamId: string) => {
    setMembers(await api.teamMembers(teamId));
  };

  useEffect(() => {
    loadTeams().catch((reason: Error) => message.error(reason.message));
  }, [message]);

  useEffect(() => {
    if (selectedId) {
      loadMembers(selectedId).catch((reason: Error) =>
        message.error(reason.message),
      );
    }
  }, [message, selectedId]);

  const updateRole = async (member: TeamMember, role: string) => {
    if (!selectedId) return;
    try {
      await api.updateMemberRole(selectedId, member.user_id, role);
      await loadMembers(selectedId);
    } catch (reason) {
      message.error((reason as Error).message);
    }
  };

  const createInvite = async () => {
    if (!selectedId) return;
    try {
      const result = await api.createInvitation(selectedId, inviteRole);
      setInvitation(result);
    } catch (reason) {
      message.error((reason as Error).message);
    }
  };

  return (
    <section className="management-page">
      <header className="management-head">
        <div>
          <span className="eyebrow">TEAM CENTER</span>
          <Typography.Title level={2}>团队中心</Typography.Title>
          <Typography.Paragraph type="secondary">
            {user.display_name} 当前加入 {teams.length} 个团队
          </Typography.Paragraph>
        </div>
        <Select
          value={selectedId || undefined}
          placeholder="选择团队"
          options={teams.map((team) => ({
            label: `${team.name} · ${team.role}`,
            value: team.id,
          }))}
          onChange={setSelectedId}
          style={{ minWidth: 220 }}
        />
      </header>

      {selected && (
        <>
          <div className="management-toolbar">
            <div>
              <Typography.Title level={4}>{selected.name}</Typography.Title>
              <Typography.Text type="secondary">
                {selected.description || "暂无团队说明"} · {selected.member_count} 名成员
              </Typography.Text>
            </div>
            {canManage && (
              <Button
                type="primary"
                onClick={() => {
                  setInvitation(null);
                  setInviteOpen(true);
                }}
              >
                生成邀请
              </Button>
            )}
          </div>
          <Table
            rowKey="user_id"
            pagination={false}
            dataSource={members}
            columns={[
              { title: "成员", dataIndex: "display_name" },
              { title: "用户名", dataIndex: "username" },
              {
                title: "团队角色",
                dataIndex: "role",
                render: (role: string, member: TeamMember) =>
                  canManage && member.role !== "owner" ? (
                    <Select
                      size="small"
                      value={role}
                      options={
                        selected.role === "owner"
                          ? ["owner", "admin", "member"].map((value) => ({
                              value,
                              label: value,
                            }))
                          : ["admin", "member"].map((value) => ({
                              value,
                              label: value,
                            }))
                      }
                      onChange={(value) => updateRole(member, value)}
                    />
                  ) : (
                    <Tag color={role === "owner" ? "gold" : "green"}>{role}</Tag>
                  ),
              },
            ]}
          />
        </>
      )}

      <Modal
        open={inviteOpen}
        title={`邀请加入 ${selected?.name || ""}`}
        okText={invitation ? "完成" : "生成邀请码"}
        cancelText="关闭"
        onOk={() => {
          if (invitation) {
            setInviteOpen(false);
            return;
          }
          void createInvite();
        }}
        onCancel={() => setInviteOpen(false)}
      >
        {!invitation ? (
          <Select
            value={inviteRole}
            options={["member", "admin", "owner"]
              .filter((role) => selected?.role === "owner" || role !== "owner")
              .map((value) => ({ value, label: value }))}
            onChange={setInviteRole}
            style={{ width: "100%" }}
          />
        ) : (
          <Alert
            type="success"
            showIcon
            message="邀请码只显示一次"
            description={
              <div>
                <code className="invite-code">{invitation.code}</code>
                <Button
                  size="small"
                  onClick={() => {
                    navigator.clipboard.writeText(invitation.code);
                    message.success("邀请码已复制");
                  }}
                >
                  复制
                </Button>
              </div>
            }
          />
        )}
      </Modal>
    </section>
  );
}
