import { Alert, Button, Form, Input, Typography } from "antd";
import { useState } from "react";

import { api } from "../../api/client";
import { passwordChangeError } from "../../lib/authFlow";
import type { UserInfo } from "../../types";

export function ForcedPasswordChange({
  user,
  onComplete,
}: {
  user: UserInfo;
  onComplete: () => void;
}) {
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (values: {
    current_password: string;
    new_password: string;
  }) => {
    setError("");
    setLoading(true);
    try {
      await api.changePassword(
        values.current_password,
        values.new_password,
      );
      onComplete();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="forced-password-page">
      <section className="forced-password-card">
        <div className="brand-seal">煌</div>
        <span className="eyebrow">PASSWORD ROTATION</span>
        <Typography.Title level={2}>请设置新密码</Typography.Title>
        <Typography.Paragraph type="secondary">
          {user.display_name}，你正在使用管理员发放的临时密码。
          修改成功后所有会话会退出，需要重新登录。
        </Typography.Paragraph>
        {error && <Alert type="error" showIcon message={error} />}
        <Form
          layout="vertical"
          requiredMark={false}
          onFinish={submit}
        >
          <Form.Item
            name="current_password"
            label="临时密码"
            rules={[{ required: true }]}
          >
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="新密码"
            dependencies={["current_password"]}
            rules={[
              { required: true },
              ({ getFieldValue }) => ({
                validator(_, value: string) {
                  const message = passwordChangeError(
                    getFieldValue("current_password") || "",
                    value || "",
                  );
                  return message
                    ? Promise.reject(new Error(message))
                    : Promise.resolve();
                },
              }),
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label="确认新密码"
            dependencies={["new_password"]}
            rules={[
              { required: true },
              ({ getFieldValue }) => ({
                validator(_, value: string) {
                  return value === getFieldValue("new_password")
                    ? Promise.resolve()
                    : Promise.reject(new Error("两次输入的新密码不一致"));
                },
              }),
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            更新密码并退出
          </Button>
        </Form>
      </section>
    </main>
  );
}
