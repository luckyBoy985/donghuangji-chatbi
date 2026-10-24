import { Alert, Button, Checkbox, Modal, Space } from "antd";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { ConversationShare, TeamInfo } from "../types";

interface Props {
  open: boolean;
  conversationId: string | null;
  teams: TeamInfo[];
  onClose: () => void;
  onSaved: () => void;
}

export function ShareDialog({
  open,
  conversationId,
  teams,
  onClose,
  onSaved,
}: Props) {
  const [shares, setShares] = useState<ConversationShare[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !conversationId) return;
    api
      .shares(conversationId)
      .then((items) => {
        setShares(items);
        setSelected(items.map((item) => item.team_id));
        setError("");
      })
      .catch((reason: Error) => setError(reason.message));
  }, [conversationId, open]);

  const save = async () => {
    if (!conversationId) return;
    setSaving(true);
    try {
      await api.setShares(conversationId, selected);
      onSaved();
      onClose();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="共享分析卷宗"
      open={open}
      onCancel={onClose}
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" loading={saving} onClick={save}>
            保存共享
          </Button>
        </Space>
      }
    >
      <p className="modal-hint">
        团队成员获得只读访问权限，可查看结论与证据，并可复制为个人会话。
      </p>
      {error && <Alert type="error" showIcon message={error} />}
      <div className="share-team-list">
        {teams.map((team) => (
          <Checkbox
            key={team.id}
            checked={selected.includes(team.id)}
            onChange={(event) =>
              setSelected((current) =>
                event.target.checked
                  ? [...current, team.id]
                  : current.filter((id) => id !== team.id),
              )
            }
          >
            {team.name}
          </Checkbox>
        ))}
        {shares.length > 0 && (
          <small>当前已共享给 {shares.length} 个团队</small>
        )}
      </div>
    </Modal>
  );
}
