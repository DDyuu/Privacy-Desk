// 脱敏配置面板：按敏感类型逐行设置脱敏动作，聚合未忽略片段后提交脱敏。
import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Empty, InputNumber, Select, Space, Tag, Tooltip, Typography } from "antd";
import type { Action, MaskActions, MaskStats, Span, TypeDefinition, VerifyResult } from "../types";

interface MaskRowState {
  action: Action;
  keepPrefix: number;
  keepSuffix: number;
}

const ACTION_OPTIONS: Array<{ value: Action; label: string }> = [
  { value: "mask", label: "屏蔽" },
  { value: "replace", label: "替换" },
  { value: "fuzz", label: "模糊化" },
  { value: "encrypt", label: "加密" },
];

const ACTION_HINT: Record<Action, string> = {
  mask: "保留前 N 位与保留后 N 位，其余字符替换为 *",
  replace: "替换为 [类型名称_序号] 占位符，相同内容全文一致",
  fuzz: "按类型规则做模糊化，保留大致形态",
  encrypt: "加密后生成 ENC:... token，可用主密钥解开",
};

interface MaskPanelProps {
  spans: Span[];
  byCode: Record<string, TypeDefinition>;
  disabled: boolean;
  loading: boolean;
  verify: VerifyResult | null;
  stats: MaskStats | null;
  onMask: (actions: MaskActions) => void;
}

// 新建配置行时继承类型定义里的默认动作与保留位数，减少手工调整
function defaultRow(definition: TypeDefinition | undefined): MaskRowState {
  const options = definition?.actionOptions ?? {};
  return {
    action: definition?.defaultAction ?? "mask",
    keepPrefix: Number(options.keepPrefix ?? 0),
    keepSuffix: Number(options.keepSuffix ?? 0),
  };
}

export default function MaskPanel({
  spans,
  byCode,
  disabled,
  loading,
  verify,
  stats,
  onMask,
}: MaskPanelProps) {
  // 入参 spans 已由父级剔除忽略项；这里只按类型 code 去重，一个类型对应一行配置
  const codes = useMemo(
    () => Array.from(new Set(spans.map((span) => span.type_code))),
    [spans],
  );
  // 数组每轮渲染都是新引用，转成字符串作依赖，避免 effect 因引用变化反复执行
  const codesKey = codes.join("|");
  const [rows, setRows] = useState<Record<string, MaskRowState>>({});

  useEffect(() => {
    setRows((prev) => {
      const next: Record<string, MaskRowState> = {};
      let changed = false;
      for (const code of codes) {
        if (prev[code]) {
          next[code] = prev[code];
        } else {
          next[code] = defaultRow(byCode[code]);
          changed = true;
        }
      }
      if (Object.keys(prev).length !== codes.length) changed = true;
      return changed ? next : prev;
    });
    // 仅在类型集合变化时同步，避免覆盖用户已修改的配置
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codesKey]);

  const updateRow = (code: string, patch: Partial<MaskRowState>) => {
    setRows((prev) => ({
      ...prev,
      [code]: { ...(prev[code] ?? defaultRow(byCode[code])), ...patch },
    }));
  };

  const handleMask = () => {
    // 只有 mask 动作需要保留位数，其余动作传空 options，避免后端收到无意义参数
    const actions: MaskActions = {};
    for (const code of codes) {
      const row = rows[code] ?? defaultRow(byCode[code]);
      actions[code] =
        row.action === "mask"
          ? {
              action: row.action,
              options: { keepPrefix: row.keepPrefix, keepSuffix: row.keepSuffix },
            }
          : { action: row.action };
    }
    onMask(actions);
  };

  if (codes.length === 0) {
    return (
      <div className="mask-panel">
        <Alert
          type="info"
          showIcon
          message="请先完成敏感信息识别"
          description="识别结果中出现的类型会在这里生成脱敏配置。"
        />
        <Button type="primary" block disabled style={{ marginTop: 12 }}>
          执行脱敏
        </Button>
      </div>
    );
  }

  return (
    <div className="mask-panel">
      {codes.map((code) => {
        const definition = byCode[code];
        const row = rows[code] ?? defaultRow(definition);
        return (
          <div className="mask-row" key={code}>
            <div className="mask-row-head">
              <span className="mask-row-name">{definition?.name ?? code}</span>
              {/* 高敏类型用红色标签提示风险，其余保持默认色 */}
              <Tag color={definition?.level === "high" ? "red" : "default"}>{code}</Tag>
            </div>
            <Space wrap size={8}>
              <span className="mask-label">动作</span>
              <Select<Action>
                size="small"
                style={{ width: 112 }}
                value={row.action}
                options={ACTION_OPTIONS}
                onChange={(action) => updateRow(code, { action })}
              />
            </Space>
            {/* 保留前后位数只对“屏蔽”动作有意义，因此随动作切换显示 */}
            {row.action === "mask" ? (
              <Space wrap size={8} style={{ marginTop: 8 }}>
                <span className="mask-label">保留前</span>
                <InputNumber
                  size="small"
                  min={0}
                  precision={0}
                  value={row.keepPrefix}
                  onChange={(value) => updateRow(code, { keepPrefix: value ?? 0 })}
                />
                <span className="mask-label">位，保留后</span>
                <InputNumber
                  size="small"
                  min={0}
                  precision={0}
                  value={row.keepSuffix}
                  onChange={(value) => updateRow(code, { keepSuffix: value ?? 0 })}
                />
                <span className="mask-label">位</span>
              </Space>
            ) : null}
            <div className="mask-hint">{ACTION_HINT[row.action]}</div>
          </div>
        );
      })}

      <Tooltip title={disabled ? "请先执行识别" : undefined}>
        <span style={{ display: "block" }}>
          <Button
            type="primary"
            block
            loading={loading}
            disabled={disabled || loading}
            onClick={handleMask}
          >
            执行脱敏
          </Button>
        </span>
      </Tooltip>

      {/* 统计文案由后端返回；忽略数为 0 时省略，避免常态出现“忽略 0 处” */}
      {stats ? (
        <div className="mask-stats">
          识别 {stats.detected} 处 · 脱敏 {stats.applied} 处
          {stats.ignored ? ` · 忽略 ${stats.ignored} 处` : ""} · 耗时{" "}
          {stats.elapsed_ms ?? 0} ms
        </div>
      ) : null}

      {verify ? (
        <Alert
          style={{ marginTop: 12 }}
          type={verify.passed ? "success" : "error"}
          showIcon
          message={verify.passed ? "校验通过，可导出" : "存在高敏残留，禁止导出"}
          description={
            verify.issues.length > 0 ? (
              <ul className="issue-list">
                {verify.issues.map((issue, index) => (
                  <li key={`${index}-${issue}`}>{issue}</li>
                ))}
              </ul>
            ) : (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                未发现残留敏感信息
              </Typography.Text>
            )
          }
        />
      ) : null}

      {!verify ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未执行脱敏" /> : null}
    </div>
  );
}
