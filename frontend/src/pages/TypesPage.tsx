import { useState } from "react";
import { PlusOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { api, errorText } from "../api/client";
import type { Action, Level, Span, TypeDefinition } from "../types";

const LEVEL_META: Record<Level, { label: string; color: string }> = {
  high: { label: "高", color: "red" },
  medium: { label: "中", color: "orange" },
  low: { label: "低", color: "blue" },
};

const ACTION_LABELS: Record<Action, string> = {
  mask: "屏蔽",
  replace: "替换",
  fuzz: "模糊化",
  encrypt: "加密",
};

const LEVEL_OPTIONS = (Object.keys(LEVEL_META) as Level[]).map((value) => ({
  value,
  label: LEVEL_META[value].label,
}));

const ACTION_OPTIONS = (Object.keys(ACTION_LABELS) as Action[]).map((value) => ({
  value,
  label: ACTION_LABELS[value],
}));

interface TypeFormValues {
  code: string;
  name: string;
  category: string;
  level: Level;
  defaultAction: Action;
  keepPrefix?: number;
  keepSuffix?: number;
  pattern?: string;
  ignoreCase?: boolean;
  words?: string;
  hint?: string;
}

type TestResults = Array<{ sample: string; spans: Span[] }>;

interface TestRow {
  key: string;
  sample: string;
  text: string;
  position: string;
  typeCode: string;
}

interface TypesPageProps {
  types: TypeDefinition[];
  loading: boolean;
  onRefresh: () => Promise<void>;
}

export default function TypesPage({ types, loading, onRefresh }: TypesPageProps) {
  const { message } = App.useApp();
  const [form] = Form.useForm<TypeFormValues>();
  const watchedAction: Action | undefined = Form.useWatch("defaultAction", form);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<TypeDefinition | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const [testTarget, setTestTarget] = useState<TypeDefinition | null>(null);
  const [samplesText, setSamplesText] = useState("");
  const [testResults, setTestResults] = useState<TestResults>([]);
  const [testing, setTesting] = useState(false);
  const [testError, setTestError] = useState("");

  const [genOpen, setGenOpen] = useState(false);
  const [genSamples, setGenSamples] = useState("");
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");
  const [genResult, setGenResult] = useState<{
    pattern: string;
    matched: number;
    total: number;
    message?: string;
  } | null>(null);

  const openCreate = () => {
    setEditing(null);
    setSaveError("");
    form.resetFields();
    setFormOpen(true);
  };

  const openEdit = (record: TypeDefinition) => {
    const regex = record.detectors.find((detector) => detector.kind === "regex");
    const keyword = record.detectors.find((detector) => detector.kind === "keyword");
    const llm = record.detectors.find((detector) => detector.kind === "llm");
    setEditing(record);
    setSaveError("");
    form.resetFields();
    form.setFieldsValue({
      code: record.code,
      name: record.name,
      category: record.category,
      level: record.level,
      defaultAction: record.defaultAction,
      keepPrefix: Number(record.actionOptions?.keepPrefix ?? 0),
      keepSuffix: Number(record.actionOptions?.keepSuffix ?? 0),
      pattern: regex?.pattern ?? "",
      ignoreCase: Boolean(regex?.flags?.includes("i")),
      words: keyword?.words?.join("，") ?? "",
      hint: llm?.hint ?? "",
    });
    setFormOpen(true);
  };

  const closeForm = () => {
    setFormOpen(false);
    setEditing(null);
    setSaveError("");
  };

  const handleSave = async () => {
    let values: TypeFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }

    const detectors: TypeDefinition["detectors"] = [];
    const pattern = values.pattern?.trim();
    if (pattern) {
      detectors.push({
        kind: "regex",
        pattern,
        flags: values.ignoreCase ? ["i"] : [],
      });
    }
    const words = (values.words ?? "")
      .split(/[,，]/)
      .map((word) => word.trim())
      .filter(Boolean);
    if (words.length > 0) {
      detectors.push({ kind: "keyword", words });
    }
    const hint = values.hint?.trim();
    if (hint) {
      detectors.push({ kind: "llm", hint });
    }

    if (detectors.length === 0) {
      setSaveError("请至少填写正则表达式、关键词或 LLM 提示之一");
      return;
    }

    const payload: TypeDefinition = {
      code: editing ? editing.code : values.code.trim(),
      name: values.name.trim(),
      category: values.category.trim(),
      level: values.level,
      builtin: false,
      enabled: editing?.enabled ?? true,
      detectors,
      defaultAction: values.defaultAction,
      actionOptions:
        values.defaultAction === "mask"
          ? {
              keepPrefix: Number(values.keepPrefix ?? 0),
              keepSuffix: Number(values.keepSuffix ?? 0),
            }
          : {},
    };

    setSaving(true);
    setSaveError("");
    try {
      await api.types.save(payload);
      await onRefresh();
      message.success(editing ? "类型已更新" : "类型已创建");
      closeForm();
    } catch (exc) {
      setSaveError(errorText(exc));
    } finally {
      setSaving(false);
    }
  };

  const openTest = (record: TypeDefinition) => {
    setTestTarget(record);
    setSamplesText("");
    setTestResults([]);
    setTestError("");
  };

  const handleTest = async () => {
    if (!testTarget) return;
    const samples = samplesText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    if (samples.length === 0) {
      message.warning("请至少输入一条样例");
      return;
    }
    setTesting(true);
    setTestError("");
    try {
      const result = await api.types.test(testTarget, samples);
      setTestResults(result.results);
    } catch (exc) {
      setTestError(errorText(exc));
      setTestResults([]);
    } finally {
      setTesting(false);
    }
  };

  const openGenerate = () => {
    setGenSamples("");
    setGenError("");
    setGenResult(null);
    setGenOpen(true);
  };

  const handleGenerate = async () => {
    const samples = genSamples
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    if (samples.length === 0) {
      message.warning("请至少输入一条样例");
      return;
    }
    setGenerating(true);
    setGenError("");
    try {
      setGenResult(await api.types.generatePattern(samples));
    } catch (exc) {
      setGenError(errorText(exc));
      setGenResult(null);
    } finally {
      setGenerating(false);
    }
  };

  const applyGenerated = () => {
    if (!genResult?.pattern) return;
    form.setFieldValue("pattern", genResult.pattern);
    setGenOpen(false);
  };

  const handleDelete = async (record: TypeDefinition) => {
    try {
      await api.types.remove(record.code);
      await onRefresh();
      message.success(`已删除类型 ${record.code}`);
    } catch (exc) {
      message.error(errorText(exc));
    }
  };

  const testRows: TestRow[] = testResults.flatMap((result, sampleIndex) =>
    result.spans.map((span, spanIndex) => ({
      key: `${sampleIndex}-${spanIndex}`,
      sample: result.sample,
      text: span.text,
      position: `${span.start}-${span.end}`,
      typeCode: span.type_code,
    })),
  );

  const testColumns: ColumnsType<TestRow> = [
    {
      title: "样例",
      dataIndex: "sample",
      ellipsis: true,
      render: (value: string) => (
        <Tooltip title={value}>
          <span>{value}</span>
        </Tooltip>
      ),
    },
    {
      title: "命中片段",
      dataIndex: "text",
      render: (value: string) => (
        <span className="mono" style={{ fontSize: 12 }}>
          {value}
        </span>
      ),
    },
    {
      title: "位置",
      dataIndex: "position",
      width: 100,
      render: (value: string) => <span className="mono">{value}</span>,
    },
    {
      title: "类型",
      dataIndex: "typeCode",
      width: 140,
      render: (value: string) => <Tag>{value}</Tag>,
    },
  ];

  const columns: ColumnsType<TypeDefinition> = [
    {
      title: "代码",
      dataIndex: "code",
      width: 168,
      render: (value: string) => <span className="mono">{value}</span>,
    },
    { title: "名称", dataIndex: "name", width: 180 },
    { title: "类别", dataIndex: "category", width: 120 },
    {
      title: "等级",
      dataIndex: "level",
      width: 90,
      render: (value: Level) => {
        const meta = LEVEL_META[value] ?? LEVEL_META.medium;
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: "默认动作",
      dataIndex: "defaultAction",
      width: 110,
      render: (value: Action) => ACTION_LABELS[value] ?? value,
    },
    {
      title: "来源",
      dataIndex: "builtin",
      width: 96,
      render: (value: boolean) =>
        value ? <Tag color="geekblue">内置</Tag> : <Tag color="green">自定义</Tag>,
    },
    {
      title: "操作",
      key: "actions",
      width: 210,
      render: (_value, record) => (
        <Space size={4} wrap>
          <Tooltip title={record.builtin ? "内置类型不可覆盖" : undefined}>
            <span>
              <Button
                type="link"
                size="small"
                disabled={record.builtin}
                onClick={() => openEdit(record)}
              >
                编辑
              </Button>
            </span>
          </Tooltip>
          <Button type="link" size="small" onClick={() => openTest(record)}>
            样例测试
          </Button>
          <Tooltip title={record.builtin ? "内置类型不可删除" : undefined}>
            <span>
              <Popconfirm
                title="删除该自定义类型？"
                description="删除后无法恢复，已识别文档不受影响。"
                okText="删除"
                cancelText="取消"
                disabled={record.builtin}
                onConfirm={() => void handleDelete(record)}
              >
                <Button type="link" size="small" danger disabled={record.builtin}>
                  删除
                </Button>
              </Popconfirm>
            </span>
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div className="workbench">
      <Card
        size="small"
        title="敏感类型"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建类型
          </Button>
        }
      >
        <Table<TypeDefinition>
          size="small"
          rowKey="code"
          columns={columns}
          dataSource={types}
          loading={loading}
          pagination={false}
          scroll={{ x: 1080 }}
        />
      </Card>

      <Modal
        open={formOpen}
        title={editing ? `编辑类型 · ${editing.code}` : "新建类型"}
        width={680}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        forceRender
        onOk={() => void handleSave()}
        onCancel={closeForm}
      >
        {saveError ? (
          <Alert
            type="error"
            showIcon
            message="保存失败"
            description={saveError}
            style={{ marginBottom: 12 }}
          />
        ) : null}
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            category: "custom",
            level: "medium",
            defaultAction: "mask",
            keepPrefix: 0,
            keepSuffix: 0,
          }}
        >
          <Row gutter={12}>
            <Col span={9}>
              <Form.Item
                name="code"
                label="代码"
                rules={[
                  { required: true, message: "请填写类型代码" },
                  {
                    pattern: /^[A-Z][A-Z0-9_]*$/,
                    message: "仅允许大写字母开头，由大写字母、数字或下划线组成",
                  },
                ]}
              >
                <Input
                  className="mono"
                  placeholder="例如 EMP_NO"
                  disabled={Boolean(editing)}
                  maxLength={64}
                />
              </Form.Item>
            </Col>
            <Col span={15}>
              <Form.Item
                name="name"
                label="名称"
                rules={[{ required: true, message: "请填写类型名称" }]}
              >
                <Input placeholder="例如 员工工号" maxLength={64} />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={12}>
            <Col span={10}>
              <Form.Item
                name="category"
                label="类别"
                rules={[{ required: true, message: "请填写类别" }]}
              >
                <Input placeholder="custom" maxLength={64} />
              </Form.Item>
            </Col>
            <Col span={7}>
              <Form.Item name="level" label="等级">
                <Select options={LEVEL_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={7}>
              <Form.Item name="defaultAction" label="默认动作">
                <Select options={ACTION_OPTIONS} />
              </Form.Item>
            </Col>
          </Row>

          {watchedAction === "mask" ? (
            <Space size={12} align="center">
              <Form.Item name="keepPrefix" label="保留前 N 位">
                <InputNumber min={0} precision={0} style={{ width: 120 }} />
              </Form.Item>
              <Form.Item name="keepSuffix" label="保留后 N 位">
                <InputNumber min={0} precision={0} style={{ width: 120 }} />
              </Form.Item>
            </Space>
          ) : null}

          <Divider orientation="left" plain>
            识别器
          </Divider>

          <Form.Item
            name="pattern"
            label="正则表达式"
            extra={
              <Space size={8}>
                <span>留空则不启用正则识别</span>
                <Button size="small" type="link" onClick={openGenerate}>
                  从样例生成
                </Button>
              </Space>
            }
          >
            <Input className="mono" placeholder="例如 EMP-\d{4}" />
          </Form.Item>
          <Form.Item name="ignoreCase" valuePropName="checked">
            <Checkbox>忽略大小写</Checkbox>
          </Form.Item>
          <Form.Item
            name="words"
            label="关键词"
            extra="多个关键词用逗号分隔，例如：工号，员工编号"
          >
            <Input placeholder="关键词1，关键词2" />
          </Form.Item>
          <Form.Item
            name="hint"
            label="LLM 提示"
            extra="交给大模型识别时使用的提示，纯规则模式下不生效"
          >
            <Input.TextArea rows={2} placeholder="例如：以 EMP- 开头的四位员工工号" />
          </Form.Item>

          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            正则表达式、关键词、LLM 提示至少填写一项。
          </Typography.Text>
        </Form>
      </Modal>

      <Modal
        open={testTarget !== null}
        title={testTarget ? `样例测试 · ${testTarget.name}` : "样例测试"}
        width={760}
        onCancel={() => setTestTarget(null)}
        footer={
          <Space>
            <Button onClick={() => setTestTarget(null)}>关闭</Button>
            <Button
              type="primary"
              loading={testing}
              disabled={samplesText.trim().length === 0}
              onClick={() => void handleTest()}
            >
              运行测试
            </Button>
          </Space>
        }
      >
        {testError ? (
          <Alert
            type="error"
            showIcon
            message="测试失败"
            description={testError}
            style={{ marginBottom: 12 }}
          />
        ) : null}
        <Input.TextArea
          className="mono"
          rows={6}
          value={samplesText}
          onChange={(event) => setSamplesText(event.target.value)}
          placeholder="每行一条样例，例如：&#10;EMP-1234&#10;工号 EMP-5678"
          style={{ marginBottom: 12 }}
        />
        <Table<TestRow>
          size="small"
          rowKey="key"
          columns={testColumns}
          dataSource={testRows}
          pagination={false}
          locale={{ emptyText: "未命中任何片段" }}
        />
      </Modal>

      <Modal
        open={genOpen}
        title="从样例生成正则"
        width={640}
        okText="应用到正则"
        cancelText="取消"
        confirmLoading={generating}
        okButtonProps={{ disabled: !genResult?.pattern }}
        onOk={applyGenerated}
        onCancel={() => setGenOpen(false)}
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
          每行一条正例，最多 20 条。所有样例中完全相同的部分会保留为字面量，只有变化的片段才泛化；建议至少填 2 条。归纳完全在本地完成，不会调用大模型。
        </Typography.Paragraph>
        <Input.TextArea
          className="mono"
          rows={6}
          value={genSamples}
          onChange={(event) => setGenSamples(event.target.value)}
          placeholder={"EMP-23003\nEMP-23004"}
          style={{ marginBottom: 12 }}
        />
        <Button onClick={() => void handleGenerate()} loading={generating}>
          生成
        </Button>
        {genError ? (
          <Alert
            type="error"
            showIcon
            message="生成失败"
            description={genError}
            style={{ marginTop: 12 }}
          />
        ) : null}
        {genResult ? (
          <div style={{ marginTop: 12 }}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              命中 {genResult.matched}/{genResult.total} 条样例
              {genResult.message ? `；${genResult.message}` : ""}
            </Typography.Text>
            <Input.TextArea
              className="mono"
              rows={3}
              value={genResult.pattern}
              readOnly
              style={{ marginTop: 8 }}
            />
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
