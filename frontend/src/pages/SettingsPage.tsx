import { useEffect, useRef, useState } from "react";
import {
  Alert,
  App,
  Button,
  Card,
  Collapse,
  Form,
  Input,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import { api, errorText } from "../api/client";
import type { EnvKeyInfo, LLMConfig, OllamaStatus } from "../types";

const MODE_OPTIONS: Array<{ value: LLMConfig["mode"]; label: string }> = [
  { value: "online", label: "在线 API" },
  { value: "ollama", label: "本地 Ollama" },
  { value: "rules", label: "纯规则" },
];

const MODE_LABELS: Record<string, string> = {
  online: "在线 API",
  ollama: "本地 Ollama",
  rules: "纯规则",
};

interface SettingsFormValues {
  mode: LLMConfig["mode"];
  base_url?: string;
  model?: string;
  api_key?: string;
  ollama_url?: string;
  ollama_model?: string;
  env_key_names?: string[];
}

interface TestResult {
  ok: boolean;
  mode: string;
  latency_ms?: number;
  items?: number;
  message?: string;
}

interface SettingsPageProps {
  onSessionRefresh: () => Promise<void>;
}

export default function SettingsPage({ onSessionRefresh }: SettingsPageProps) {
  const { message } = App.useApp();
  const [form] = Form.useForm<SettingsFormValues>();
  const watchedMode: LLMConfig["mode"] | undefined = Form.useWatch("mode", form);
  const watchedBaseUrl: string | undefined = Form.useWatch("base_url", form);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [hasKey, setHasKey] = useState(false);
  const [envKeys, setEnvKeys] = useState<EnvKeyInfo[]>([]);
  const [keySource, setKeySource] = useState("none");
  const [detecting, setDetecting] = useState(false);
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatus | null>(null);
  const [checkingOllama, setCheckingOllama] = useState(false);
  const ollamaCheckedRef = useRef<string | null>(null);

  const loadConfig = async () => {
    setLoading(true);
    setLoadError("");
    try {
      const config = await api.settings.getLlm();
      setHasKey(Boolean(config.has_key));
      setEnvKeys(config.env_keys ?? []);
      setKeySource(config.key_source ?? "none");
      form.setFieldsValue({
        mode: config.mode,
        base_url: config.base_url,
        model: config.model,
        api_key: "",
        ollama_url: config.ollama_url,
        ollama_model: config.ollama_model,
        env_key_names: config.env_key_names ?? [],
      });
    } catch (exc) {
      setLoadError(errorText(exc));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadConfig();
    // 仅在页面挂载时加载一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const checkOllama = async () => {
    setCheckingOllama(true);
    try {
      const url = (form.getFieldValue("ollama_url") as string | undefined) ?? "";
      const model = (form.getFieldValue("ollama_model") as string | undefined) ?? "";
      setOllamaStatus(await api.settings.ollamaStatus(url, model));
    } catch (exc) {
      setOllamaStatus(null);
      message.error(errorText(exc));
    } finally {
      setCheckingOllama(false);
    }
  };

  useEffect(() => {
    if (watchedMode !== "ollama") {
      ollamaCheckedRef.current = null;
      return;
    }
    if (ollamaCheckedRef.current === "ollama") return;
    ollamaCheckedRef.current = "ollama";
    void checkOllama();
    // 仅在切换到 Ollama 模式时检测一次，地址变化后由“重新检测”按钮触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watchedMode]);

  const handleDetectEnv = async () => {
    setDetecting(true);
    try {
      const names = (form.getFieldValue("env_key_names") as string[] | undefined) ?? [];
      const result = await api.settings.detectEnvKeys(names);
      setHasKey(Boolean(result.has_key));
      setEnvKeys(result.env_keys ?? []);
      setKeySource(result.key_source ?? "none");
      if ((result.env_keys ?? []).length === 0) {
        message.warning("未检测到环境变量中的 API Key");
      } else {
        message.success(`检测到 ${result.env_keys?.length ?? 0} 个环境变量 Key`);
      }
    } catch (exc) {
      message.error(errorText(exc));
    } finally {
      setDetecting(false);
    }
  };

  const handleSave = async () => {
    let values: SettingsFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setSaving(true);
    setSaveError("");
    try {
      const saved = await api.settings.saveLlm({
        mode: values.mode,
        base_url: values.base_url ?? "",
        model: values.model ?? "",
        api_key: values.api_key ?? "",
        ollama_url: values.ollama_url ?? "",
        ollama_model: values.ollama_model ?? "",
        env_key_names: values.env_key_names ?? [],
      });
      setHasKey(Boolean(saved.has_key));
      setEnvKeys(saved.env_keys ?? []);
      setKeySource(saved.key_source ?? "none");
      form.setFieldValue("api_key", "");
      message.success("配置已保存");
      if (values.mode === "ollama") {
        ollamaCheckedRef.current = null;
        void checkOllama();
      }
      await onSessionRefresh();
    } catch (exc) {
      setSaveError(errorText(exc));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api.settings.testLlm();
      setTestResult(result);
      if (!result.ok) {
        message.warning(result.message ?? "未配置在线或本地模型");
      } else {
        message.success(`连接成功，延迟 ${result.latency_ms ?? 0} ms`);
      }
    } catch (exc) {
      message.error(errorText(exc));
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <Card size="small">
        <Spin />
      </Card>
    );
  }

  if (loadError) {
    return (
      <Card size="small">
        <Alert type="error" showIcon message="读取设置失败" description={loadError} />
        <Button style={{ marginTop: 12 }} onClick={() => void loadConfig()}>
          重试
        </Button>
      </Card>
    );
  }

  return (
    <div style={{ maxWidth: 780 }}>
      <Card size="small" title="大模型配置">
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            mode: "online",
            base_url: "",
            model: "",
            api_key: "",
            ollama_url: "http://127.0.0.1:11434",
            ollama_model: "",
            env_key_names: [],
          }}
        >
          <Form.Item name="mode" label="模式" rules={[{ required: true }]}>
            <Select options={MODE_OPTIONS} style={{ width: 220 }} />
          </Form.Item>

          <div style={{ display: watchedMode === "online" ? undefined : "none" }}>
            <Form.Item
              name="base_url"
              label="Base URL"
              rules={
                watchedMode === "online"
                  ? [{ required: true, message: "在线模式需填写 Base URL" }]
                  : []
              }
            >
              <Input placeholder="https://api.deepseek.com/v1" />
            </Form.Item>
            <Form.Item
              name="model"
              label="模型名称"
              rules={
                watchedMode === "online" ? [{ required: true, message: "在线模式需填写模型名称" }] : []
              }
            >
              <Input placeholder="deepseek-flash" />
            </Form.Item>
            <Form.Item
              name="api_key"
              className="settings-api-key-item"
              label={
                <div className="settings-key-label">
                  <span>API Key</span>
                  <Space size={4} align="center">
                    <Typography.Text>Key 储存在环境变量中？</Typography.Text>
                    <Button
                      size="small"
                      type="link"
                      loading={detecting}
                      onClick={() => void handleDetectEnv()}
                    >
                      检测环境变量
                    </Button>
                  </Space>
                </div>
              }
              extra={
                hasKey ? (
                  <Space size={4} wrap>
                    <Tag color="green">已配置 Key</Tag>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {keySource === "stored"
                        ? "来自本地加密存储"
                        : keySource.startsWith("env:")
                          ? `来自环境变量 ${keySource.slice(4)}`
                          : ""}
                    </Typography.Text>
                  </Space>
                ) : (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    尚未配置 Key
                  </Typography.Text>
                )
              }
            >
              <Input.Password placeholder="已保存，留空则不修改" autoComplete="new-password" />
            </Form.Item>

            <Collapse
              ghost
              size="small"
              style={{ marginBottom: 16 }}
              items={[
                {
                  key: "env",
                  label: "环境变量名（可选）",
                  children: (
                    <Form.Item
                      name="env_key_names"
                      extra="留空时只检测内置变量 PRIVACY_DESK_LLM_KEY、DEEPSEEK_API_KEY、OPENAI_API_KEY；已保存的 Key 优先，环境变量仅作回退且不会写入数据库。"
                      style={{ marginBottom: 0 }}
                    >
                      <Select
                        mode="tags"
                        placeholder="输入自定义变量名后回车，如 MY_LLM_KEY"
                        tokenSeparators={[",", " "]}
                        open={false}
                      />
                    </Form.Item>
                  ),
                },
              ]}
            />

            {envKeys.length > 0 ? (
              <Alert
                style={{ marginBottom: 16 }}
                type={keySource === "stored" ? "info" : "success"}
                showIcon
                message={
                  keySource === "stored"
                    ? "已保存的 Key 生效中（优先级高于环境变量）"
                    : keySource.startsWith("env:")
                      ? "已从环境变量读取 API Key"
                      : "检测到环境变量中的 API Key"
                }
                description={
                  <Space direction="vertical" size={4}>
                    {envKeys.map((item) => (
                      <Space key={item.name} size={8} wrap>
                        <Tag color={item.active ? "green" : "default"}>{item.provider}</Tag>
                        <Typography.Text code>{item.name}</Typography.Text>
                        <Typography.Text type="secondary">{item.masked}</Typography.Text>
                        {item.active ? <Tag color="blue">当前生效</Tag> : null}
                        {item.active &&
                        item.base_url &&
                        watchedBaseUrl &&
                        item.base_url !== watchedBaseUrl ? (
                          <Typography.Text type="warning" style={{ fontSize: 12 }}>
                            该变量对应 {item.base_url}
                          </Typography.Text>
                        ) : null}
                      </Space>
                    ))}
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {watchedMode === "rules"
                        ? "当前为纯规则模式，切换到在线 API 后自动生效。"
                        : "环境变量中的 Key 不会写入数据库，删除变量后即失效。"}
                    </Typography.Text>
                  </Space>
                }
              />
            ) : null}
          </div>

          <div style={{ display: watchedMode === "ollama" ? undefined : "none" }}>
            <Form.Item
              name="ollama_url"
              label="Ollama 地址"
              rules={
                watchedMode === "ollama" ? [{ required: true, message: "请填写 Ollama 地址" }] : []
              }
            >
              <Input placeholder="http://127.0.0.1:11434" />
            </Form.Item>
            <Form.Item
              name="ollama_model"
              label="Ollama 模型"
              rules={
                watchedMode === "ollama" ? [{ required: true, message: "请填写 Ollama 模型" }] : []
              }
            >
              <Input placeholder="qwen2.5:7b" />
            </Form.Item>
            <Space style={{ marginBottom: 8 }}>
              <Button size="small" loading={checkingOllama} onClick={() => void checkOllama()}>
                重新检测
              </Button>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                检测当前填写的地址与模型
              </Typography.Text>
            </Space>
            {ollamaStatus ? (
              <Alert
                style={{ marginBottom: 8 }}
                type={
                  ollamaStatus.reachable && ollamaStatus.model_present ? "success" : "warning"
                }
                showIcon
                message={
                  !ollamaStatus.reachable
                    ? "未检测到本机 Ollama 服务"
                    : ollamaStatus.model_present
                      ? "Ollama 服务可用"
                      : "Ollama 服务已连接，但缺少模型"
                }
                description={
                  !ollamaStatus.reachable
                    ? `${ollamaStatus.message}。不安装 Ollama 不影响纯规则模式；需要本地模型时请安装并启动 Ollama。`
                    : ollamaStatus.model_present
                      ? `已检测到模型：${ollamaStatus.models.join("、")}`
                      : ollamaStatus.message ||
                        `服务已连接，当前可用模型：${
                          ollamaStatus.models.join("、") || "（暂无）"
                        }。请检查模型名称。`
                }
              />
            ) : null}
          </div>

          {watchedMode === "rules" ? (
            <Alert
              type="info"
              showIcon
              message="纯规则模式不联网"
              description="仅使用本地正则规则与字典识别敏感信息，无法发现规则之外的隐含信息。"
            />
          ) : null}

          {saveError ? (
            <Alert
              type="error"
              showIcon
              message="保存失败"
              description={saveError}
              style={{ marginTop: 12 }}
            />
          ) : null}

          <Space style={{ marginTop: 16 }}>
            <Button type="primary" loading={saving} onClick={() => void handleSave()}>
              保存配置
            </Button>
            <Button loading={testing} onClick={() => void handleTest()}>
              测试连接
            </Button>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              测试使用已保存的配置
            </Typography.Text>
          </Space>

          {testResult ? (
            <Alert
              style={{ marginTop: 12 }}
              type={testResult.ok ? "success" : "warning"}
              showIcon
              message={testResult.ok ? "连接成功" : "连接未就绪"}
              description={
                testResult.ok
                  ? `模式：${MODE_LABELS[testResult.mode] ?? testResult.mode}，延迟 ${
                      testResult.latency_ms ?? 0
                    } ms，返回条目 ${testResult.items ?? 0}`
                  : testResult.message ?? "未配置在线或本地模型"
              }
            />
          ) : null}
        </Form>
      </Card>

      <Card size="small" title="说明" style={{ marginTop: 16 }}>
        <ul className="issue-list" style={{ paddingLeft: 18, margin: 0 }}>
          <li>在线模式会先在本地遮蔽身份证、手机号等高敏信息，再将文本发送到云端模型。</li>
          <li>纯规则模式不联网，仅使用本地规则与字典完成识别。</li>
          <li>API Key 加密存储，保存后不会回显；留空表示保留已保存的 Key。</li>
        </ul>
      </Card>
    </div>
  );
}
