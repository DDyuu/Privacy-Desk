// 类型库共享缓存：解锁后加载一次，供工作台与解密页按 code 查表。
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
    // 类型页保存或删除后调用，用后端最新定义替换缓存
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
      // 锁定后立即清空，避免类型定义（含字典词）继续留在内存里
      setTypes([]);
    }
  }, [enabled, refresh]);

  // 预先建好 code → 定义映射，检测结果渲染时可 O(1) 取名称与级别
  const byCode = useMemo(
    () => Object.fromEntries(types.map((item) => [item.code, item])) as Record<string, TypeDefinition>,
    [types],
  );

  return { types, byCode, loading, refresh };
}
