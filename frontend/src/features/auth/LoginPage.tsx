import { Alert, Button, Form, Input, Segmented, Typography } from "antd";
import { useEffect, useState } from "react";

import { api } from "../../api/client";
import type { UserInfo } from "../../types";

interface Props {
  onAuthenticated: (user: UserInfo) => void;
}

type AuthMode = "login" | "register" | "setup";

export function LoginPage({ onAuthenticated }: Props) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [setupRequired, setSetupRequired] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [inviteFromUrl] = useState(
    () => new URLSearchParams(window.location.search).get("invite") || "",
  );

  useEffect(() => {
    api
      .setupStatus()
      .then((result) => {
        setSetupRequired(result.setup_required);
        if (result.setup_required) setMode("setup");
        else if (inviteFromUrl) setMode("register");
      })
      .catch((reason: Error) => setError(reason.message));
  }, [inviteFromUrl]);

  const submit = async (values: Record<string, string>) => {
    setLoading(true);
    setError("");
    try {
      let user: UserInfo;
      if (mode === "setup") {
        user = await api.setup(values);
      } else if (mode === "register") {
        user = await api.registerWithInvite(values);
      } else {
        user = await api.login(values.username, values.password);
      }
      onAuthenticated(user);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-page">
      <section className="login-story">
        <div className="brand-seal">煌</div>
        <div>
          <span className="eyebrow">DONGHUANG INTELLIGENCE</span>
          <h1>
            让每次竞品判断
            <br />
            都有据可循
          </h1>
          <p>多产品资料库、同屏证据与可追溯引用。登录后进入你的分析卷宗。</p>
        </div>
        <small>INTERNAL · EVIDENCE-FIRST · CHATBI</small>
      </section>
      <section className="login-form-side">
        <div className="login-form-card">
          <Typography.Title level={2}>
            {mode === "setup"
              ? "初始化系统"
              : mode === "register"
                ? "通过邀请加入"
                : "登录分析工作台"}
          </Typography.Title>
          <Typography.Paragraph type="secondary">
            {mode === "setup"
              ? "创建首位平台管理员，之后仅可通过邀请加入。"
              : mode === "register"
                ? "邀请码绑定团队与角色。"
                : "使用团队成员账号继续。"}
          </Typography.Paragraph>

          {!setupRequired && (
            <Segmented
              block
              value={mode}
              options={[
                { label: "登录", value: "login" },
                { label: "邀请注册", value: "register" },
              ]}
              onChange={(value) => {
                setError("");
                setMode(value as AuthMode);
              }}
            />
          )}
          {error && <Alert type="error" showIcon message={error} />}
          <Form layout="vertical" onFinish={submit} requiredMark={false}>
            {mode === "setup" && (
              <Form.Item
                name="bootstrap_token"
                label="初始化令牌"
                rules={[{ required: true }]}
              >
                <Input.Password autoComplete="off" />
              </Form.Item>
            )}
            {(mode === "login" || mode === "setup") && (
              <Form.Item
                name="username"
                label="用户名"
                rules={[{ required: true }]}
              >
                <Input autoComplete="username" />
              </Form.Item>
            )}
            {mode === "register" && (
              <>
                <Form.Item
                  name="code"
                  label="邀请码"
                  initialValue={inviteFromUrl}
                  rules={[{ required: true }]}
                >
                  <Input />
                </Form.Item>
                <Form.Item
                  name="username"
                  label="用户名"
                  rules={[{ required: true, min: 3 }]}
                >
                  <Input autoComplete="username" />
                </Form.Item>
              </>
            )}
            {mode !== "login" && (
              <Form.Item
                name="display_name"
                label="显示名称"
                rules={[{ required: true }]}
              >
                <Input />
              </Form.Item>
            )}
            <Form.Item
              name="password"
              label="密码"
              rules={[{ required: true, min: mode === "login" ? 1 : 12 }]}
            >
              <Input.Password
                autoComplete={
                  mode === "login" ? "current-password" : "new-password"
                }
              />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={loading}>
              {mode === "setup"
                ? "创建管理员"
                : mode === "register"
                  ? "注册并加入"
                  : "进入竞品情报"}
            </Button>
          </Form>
        </div>
      </section>
    </main>
  );
}
