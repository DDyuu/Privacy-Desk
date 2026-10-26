import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, App as AntApp, Button, Card, Spin, Typography } from "antd";
import AppLayout, { type PageKey } from "./components/AppLayout";
import TitleBar from "./components/TitleBar";
import { useSession } from "./hooks/useSession";
import { useTypes } from "./hooks/useTypes";
import BatchPage from "./pages/BatchPage";
import LockPage from "./pages/LockPage";
import SettingsPage from "./pages/SettingsPage";
import TypesPage from "./pages/TypesPage";
import WorkbenchPage from "./pages/WorkbenchPage";

type View = "boot" | "lock" | "app";
const FADE_MS = 180;

export default function App() {
  const session = useSession();
  const { message } = AntApp.useApp();
  const [page, setPage] = useState<PageKey>("workbench");
  const [lockReason, setLockReason] = useState("");
  const [pendingDocId, setPendingDocId] = useState<string | null>(null);
  const [view, setView] = useState<View>("boot");
  const viewRef = useRef<View>("boot");

  const unlocked = Boolean(session.status?.unlocked);
  const targetView: View = !session.status ? "boot" : unlocked ? "app" : "lock";
  const { types, byCode, loading: typesLoading, refresh: refreshTypes } = useTypes(
    unlocked || view === "app",
  );

  useEffect(() => {
    if (unlocked) setLockReason("");
  }, [unlocked]);

  // 锁定/解锁：整窗淡出 → 切换尺寸 → 等窗口就绪后再挂载新界面并淡入
  useEffect(() => {
    const bridge = window.privacyDesk;
    let cancelled = false;
    let fadeTimer: number | null = null;
    let fallbackTimer: number | null = null;
    let unsubscribe: (() => void) | undefined;

    const cleanup = () => {
      cancelled = true;
      if (fadeTimer !== null) window.clearTimeout(fadeTimer);
      if (fallbackTimer !== null) window.clearTimeout(fallbackTimer);
      unsubscribe?.();
      bridge?.fadeWindow?.("in");
    };

    if (targetView === viewRef.current) return cleanup;

    const applyView = (next: View) => {
      if (cancelled) return;
      viewRef.current = next;
      setView(next);
      // 等两帧，让新界面按最终尺寸完成布局后再显示
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (!cancelled) bridge?.fadeWindow?.("in");
        });
      });
    };

    const switchMode = (next: View) => {
      if (cancelled) return;
      const mode = next === "app" ? "workbench" : "lock";
      if (!bridge?.setWindowMode || !bridge.onWindowModeApplied) {
        applyView(next);
        return;
      }
      unsubscribe = bridge.onWindowModeApplied(() => {
        unsubscribe?.();
        unsubscribe = undefined;
        if (fallbackTimer !== null) {
          window.clearTimeout(fallbackTimer);
          fallbackTimer = null;
        }
        applyView(next);
      });
      // 兜底：窗口消息丢失时仍能完成切换
      fallbackTimer = window.setTimeout(() => {
        fallbackTimer = null;
        unsubscribe?.();
        unsubscribe = undefined;
        applyView(next);
      }, 800);
      bridge.setWindowMode(mode);
    };

    // 启动页 → 锁屏：窗口尺寸不变，直接切换
    if (targetView === "lock" && viewRef.current === "boot") {
      bridge?.setWindowMode?.("lock");
      applyView(targetView);
      return cleanup;
    }

    if (targetView === "boot" || !bridge?.fadeWindow) {
      bridge?.setWindowMode?.(targetView === "app" ? "workbench" : "lock");
      applyView(targetView);
      return cleanup;
    }

    bridge.fadeWindow("out");
    fadeTimer = window.setTimeout(() => {
      fadeTimer = null;
      switchMode(targetView);
    }, FADE_MS);

    return cleanup;
  }, [targetView]);

  useEffect(() => {
    if (session.error && unlocked) {
      message.error(session.error);
    }
  }, [session.error, unlocked, message]);

  const handleLock = useCallback(() => {
    setLockReason("已手动锁定");
    void session.lock();
  }, [session.lock]);

  const handleOpenDoc = useCallback((docId: string) => {
    setPendingDocId(docId);
    setPage("workbench");
  }, []);

  const handleDocOpened = useCallback(() => setPendingDocId(null), []);

  if (view === "boot" || !session.status) {
    return (
      <div className="boot-screen">
        {session.error ? (
          <Card style={{ width: 440 }}>
            <Alert
              type="error"
              showIcon
              message="无法连接本地后端"
              description={session.error}
            />
            <Button
              type="primary"
              style={{ marginTop: 16 }}
              onClick={() => void session.refresh()}
            >
              重试连接
            </Button>
          </Card>
        ) : (
          <>
            <Spin size="large" />
            <Typography.Text type="secondary">正在连接本地服务…</Typography.Text>
          </>
        )}
      </div>
    );
  }

  if (view === "lock") {
    return (
      <LockPage
        status={session.status}
        busy={session.busy}
        error={session.error}
        reason={lockReason}
        onSetup={session.setup}
        onUnlock={session.unlock}
      />
    );
  }

  return (
    <>
      <TitleBar />
      <AppLayout
        status={session.status}
        page={page}
        onPageChange={setPage}
        onLock={handleLock}
      >
        {page === "workbench" ? (
          <WorkbenchPage
            byCode={byCode}
            llmMode={session.status.llm_mode}
            openDocId={pendingDocId}
            onOpenedDoc={handleDocOpened}
          />
        ) : null}
        {page === "batch" ? <BatchPage onOpenDoc={handleOpenDoc} /> : null}
        {page === "types" ? (
          <TypesPage types={types} loading={typesLoading} onRefresh={refreshTypes} />
        ) : null}
        {page === "settings" ? <SettingsPage onSessionRefresh={session.refresh} /> : null}
      </AppLayout>
    </>
  );
}
