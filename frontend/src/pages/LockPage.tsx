import { LockOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Form, Input, Typography } from "antd";
import type { SessionStatus } from "../types";

interface LockPageProps {
  status: SessionStatus;
  busy: boolean;
  error: string;
  reason: string;
  onSetup: (password: string) => Promise<void>;
  onUnlock: (password: string) => Promise<void>;
}

interface FormValues {
  password: string;
  confirm?: string;
}

export default function LockPage({
  status,
  busy,
  error,
  reason,
  onSetup,
  onUnlock,
}: LockPageProps) {
  const [form] = Form.useForm<FormValues>();
  const initialized = status.initialized;

  const handleFinish = async (values: FormValues) => {
    if (initialized) {
      await onUnlock(values.password);
    } else {
      await onSetup(values.password);
      form.resetFields();
    }
  };

  return (
    <div className="lock-screen">
      <Card className="lock-card">
        <div className="lock-brand">
          <div className="lock-brand-icon">
            <LockOutlined />
          </div>
          <div>
            <div className="lock-brand-title">隐盾 PrivacyDesk</div>
            <div className="lock-brand-sub">本地隐私脱敏工作台</div>
          </div>
        </div>

        <Typography.Title level={4} style={{ marginTop: 0, marginBottom: 6 }}>
          {initialized ? "解锁工作台" : "设置主密码"}
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ fontSize: 13, lineHeight: 1.8 }}>
          {initialized
            ? "请输入主密码以解密本地文档与类型配置。"
            : "主密码用于加密本地文档与配置；密码不存储，遗失将无法解密历史数据。"}
        </Typography.Paragraph>

        {reason ? (
          <Alert type="warning" showIcon message={reason} style={{ marginBottom: 16 }} />
        ) : null}

        {error ? (
          <Alert
            type="error"
            showIcon
            message={initialized ? "解锁失败" : "设置失败"}
            description={error}
            style={{ marginBottom: 16 }}
          />
        ) : null}

        <Form form={form} layout="vertical" onFinish={handleFinish} requiredMark={false}>
          <Form.Item
            name="password"
            label="主密码"
            rules={[
              { required: true, message: "请输入主密码" },
              { min: 8, message: "主密码至少 8 位" },
            ]}
          >
            <Input.Password
              autoFocus
              autoComplete={initialized ? "current-password" : "new-password"}
              placeholder={initialized ? "输入主密码" : "至少 8 位，建议混合大小写与符号"}
            />
          </Form.Item>

          {!initialized ? (
            <Form.Item
              name="confirm"
              label="确认主密码"
              dependencies={["password"]}
              rules={[
                { required: true, message: "请再次输入主密码" },
                ({ getFieldValue }) => ({
                  validator(_, value: string) {
                    if (!value || getFieldValue("password") === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error("两次输入的密码不一致"));
                  },
                }),
              ]}
            >
              <Input.Password
                autoComplete="new-password"
                placeholder="再次输入主密码"
                onPressEnter={() => form.submit()}
              />
            </Form.Item>
          ) : null}

          <Button type="primary" htmlType="submit" block size="large" loading={busy}>
            {initialized ? "解锁" : "设置并进入"}
          </Button>
        </Form>

        <div className="lock-footer">
          数据仅保存在本机目录，退出后可随时锁定
          <br />
          按 Enter 可直接提交
        </div>
      </Card>
    </div>
  );
}
