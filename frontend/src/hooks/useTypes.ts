import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { TypeDefinition } from "../types";

/**
 * 解锁后加载脱敏类型，并提供 code -> 定义的映射。
 * 未解锁（enabled=false）时清空缓存，避免锁定后仍保留数据。
 */
export function useTypes(enabled = true) {
  const [types, setTypes] = useState<TypeDefinition[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setTypes(await api.types.list());
    } catch {
      /* 加载失败时保持现有数据，页面可自行提示 */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (enabled) {
      void refresh();
    } else {
      setTypes([]);
    }
  }, [enabled, refresh]);

  const byCode = useMemo(
    () => Object.fromEntries(types.map((item) => [item.code, item])) as Record<string, TypeDefinition>,
    [types],
  );

  return { types, byCode, loading, refresh };
}
