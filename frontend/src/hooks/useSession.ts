// 会话状态 hook：挂载时探测一次后端状态，之后由初始化/解锁/锁定动作返回的状态更新。
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { SessionStatus } from "../types";

export function useSession() {
  const [status, setStatus] = useState<SessionStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.session.status());
      setError("");
    } catch (exc) {
      // 保留错误文案，启动页据此展示“无法连接本地后端”的重试入口
      setError(exc instanceof Error ? exc.message : "无法连接后端");
    }
  }, []);

  useEffect(() => {
    // 只在挂载时探测一次；设置页保存配置后会主动调用 refresh
    void refresh();
  }, [refresh]);

  const run = useCallback(async (action: () => Promise<SessionStatus>) => {
    // busy/error 收拢到一处，避免 setup/unlock/lock 各自维护一套状态
    setBusy(true);
    setError("");
    try {
      setStatus(await action());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }, []);

  const setup = useCallback(
    (password: string) => run(() => api.session.setup(password)),
    [run],
  );
  const unlock = useCallback(
    (password: string) => run(() => api.session.unlock(password)),
    [run],
  );
  const lock = useCallback(() => run(() => api.session.lock()), [run]);

  return { status, busy, error, refresh, setup, unlock, lock };
}
