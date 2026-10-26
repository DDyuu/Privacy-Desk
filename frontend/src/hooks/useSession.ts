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
      setError(exc instanceof Error ? exc.message : "无法连接后端");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const run = useCallback(async (action: () => Promise<SessionStatus>) => {
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
