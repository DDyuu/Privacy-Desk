export type Level = "high" | "medium" | "low";
export type Action = "mask" | "replace" | "fuzz" | "encrypt";

export interface Span {
  start: number;
  end: number;
  type_code: string;
  text: string;
  confidence: number;
  source: "rule" | "llm";
  level: Level;
}

export interface DocumentMeta {
  id: string;
  name: string;
  ext: string;
  size: number;
  status: "uploaded" | "detected" | "masked" | "verified";
  created_at: string;
  updated_at: string;
}

export interface DocumentDetail extends DocumentMeta {
  text: string;
  detections: Span[];
}

export interface TypeDefinition {
  code: string;
  name: string;
  category: string;
  level: Level;
  builtin: boolean;
  enabled: boolean;
  detectors: Array<{
    kind: "regex" | "checksum" | "keyword" | "dict" | "llm";
    pattern?: string;
    flags?: string[];
    algo?: string;
    words?: string[];
    hint?: string;
    confidence?: number;
    strip?: string;
  }>;
  defaultAction: Action;
  actionOptions: Record<string, number>;
}

export interface VerifyResult {
  passed: boolean;
  residuals: Span[];
  metrics: Record<string, number>;
  issues: string[];
}

export interface SessionStatus {
  initialized: boolean;
  unlocked: boolean;
  llm_mode: "online" | "ollama" | "rules";
}

export interface EnvKeyInfo {
  name: string;
  provider: string;
  masked: string;
  base_url: string;
  model: string;
  active: boolean;
}

export interface LLMConfig {
  mode: "online" | "ollama" | "rules";
  base_url: string;
  model: string;
  api_key: string;
  ollama_url: string;
  ollama_model: string;
  has_key?: boolean;
  key_source?: string;
  env_keys?: EnvKeyInfo[];
  env_key_names?: string[];
}

export interface OllamaStatus {
  url: string;
  reachable: boolean;
  models: string[];
  model_present: boolean;
  message: string;
}

export interface BatchStatus {
  id: string;
  status: "running" | "done";
  total: number;
  done: number;
  items: Array<{ id: string; doc_id: string | null; status: string; message: string }>;
}

/** 脱敏时单个类型的配置；options 仅 mask 动作使用 keepPrefix / keepSuffix */
export type MaskActions = Record<
  string,
  { action: Action; options?: Record<string, number> }
>;

/** 后端 mask 响应中的逐条替换记录，start/end 为原文偏移 */
export interface AppliedItem {
  start: number;
  end: number;
  type_code: string;
  action: Action;
  replacement: string;
}

/** 解密 ENC 令牌后返回的原文片段 */
export interface RevealedItem {
  token: string;
  type_code: string;
  start: number;
  text: string;
}

export interface MaskStats {
  detected: number;
  applied: number;
  mapping?: number;
  elapsed_ms?: number;
}

export interface MaskResponse {
  masked_text: string;
  applied: AppliedItem[];
  stats: MaskStats;
  verify: VerifyResult | null;
  summary: Record<string, unknown>;
  job_id: string;
}

export interface CompareResponse {
  original: string;
  masked: string;
  detections: Span[];
  applied: AppliedItem[];
  verify: VerifyResult;
}
