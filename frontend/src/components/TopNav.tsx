import { Avatar, Dropdown } from "antd";

import type { UserInfo } from "../types";

export type AppView = "analysis" | "teams" | "admin";

interface Props {
  user: UserInfo;
  view: AppView;
  onChange: (view: AppView) => void;
  onLogout: () => void;
}

export function TopNav({ user, view, onChange, onLogout }: Props) {
  return (
    <header className="top-nav">
      <button
        type="button"
        className="top-brand"
        onClick={() => onChange("analysis")}
      >
        <span className="top-seal">煌</span>
        东煌纪 · 竞品情报
      </button>
      <nav>
        <button
          type="button"
          className={view === "analysis" ? "active" : ""}
          onClick={() => onChange("analysis")}
        >
          分析
        </button>
        <button
          type="button"
          className={view === "teams" ? "active" : ""}
          onClick={() => onChange("teams")}
        >
          团队
        </button>
        {user.platform_role === "admin" && (
          <button
            type="button"
            className={view === "admin" ? "active" : ""}
            onClick={() => onChange("admin")}
          >
            管理
          </button>
        )}
      </nav>
      <Dropdown
        menu={{
          items: [
            { key: "name", label: `${user.display_name} · ${user.username}` },
            { type: "divider" },
            { key: "logout", label: "退出登录", onClick: onLogout },
          ],
        }}
        trigger={["click"]}
      >
        <button type="button" className="user-avatar">
          <Avatar size={28}>{user.display_name.slice(0, 1)}</Avatar>
        </button>
      </Dropdown>
    </header>
  );
}
