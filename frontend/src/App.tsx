// 应用主状态机：boot（探测后端）→ lock（初始化/解锁）→ app（工作台），并驱动 Electron 窗口尺寸切换。
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, App as AntApp, Button, Card, Spin, Typography } from "antd";
import AppLayout, { type PageKey } from "./components/AppLayout";
import TitleBar from "./components/TitleBar";
import { useSession } from "./hooks/useSession";
import { useTypes } from "./hooks/useTypes";
import BatchPage from "./pages/BatchPage";
import LockPage from "./pages/LockPage";
import RevealPage from "./pages/RevealPage";
import SettingsPage from "./pages/SettingsPage";
import TypesPage from "./pages/TypesPage";
import WorkbenchPage from "./pages/WorkbenchPage";

type View = "boot" | "lock" | "app";
// 与主进程 WINDOW_FADE_MS 一致：淡出结束后再改窗口尺寸，用户看不到中间态的旧布局
const FADE_MS = 180;

export default function App() {
  const session = useSession();
  const { message } = AntApp.useApp();
  const [page, setPage] = useState<PageKey>("workbench");
  const [lockReason, setLockReason] = useState("");
  const [pendingDocId, setPendingDocId] = useState<string | null>(null);
  const [view, setView] = useState<View>("boot");
  // 与 view 同步的镜像，供 effect 内读取最新值而不被加入依赖数组
  const viewRef = useRef<View>("boot");

  const unlocked = Boolean(session.status?.unlocked);
  // 后端状态是唯一真源：未拿到状态先停在启动页，已解锁才进入工作台
  const targetView: View = !session.status ? "boot" : unlocked ? "app" : "lock";
  // 仅在解锁（或已切到工作台）后加载类型库，锁屏阶段不提前请求
  const { types, byCode, loading: typesLoading, refresh: refreshTypes } = useTypes(
    unlocked || view === "app",
  );

  useEffect(() => {
    // 解锁成功后清掉上一次的锁定提示文案
    if (unlocked) setLockReason("");
  }, [unlocked]);

  // 锁定/解锁：整窗淡出 → 切换尺寸 → 等窗口就绪后再挂载新界面并淡入
  useEffect(() => {
    // 浏览器调试时没有 preload 注入的桥接对象，以下窗口调用都按可选链降级
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
      // 恢复不透明度，避免窗口因中途取消而停在半透明状态
      bridge?.fadeWindow?.("in");
    };

    if (targetView === viewRef.current) return cleanup;

    const applyView = (next: View) => {
      if (cancelled) return;
      // 先写 ref 再更新 state，避免下一轮 effect 读到旧值而重复切换
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
      // 必须先订阅再发尺寸指令，否则主进程的回执可能早于监听注册而丢失
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
      // 主进程通常 80ms 内回执，800ms 足以覆盖 IPC 与重排耗时；超时则直接切界面，避免一直白屏
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

    // 非 Electron 环境或版本缺少淡出能力时直接切换，不等待窗口回执
    if (targetView === "boot" || !bridge?.fadeWindow) {
      bridge?.setWindowMode?.(targetView === "app" ? "workbench" : "lock");
      applyView(targetView);
      return cleanup;
    }

    // 先淡出再切尺寸：窗口不可见时完成重排，避免看到布局跳变
    bridge.fadeWindow("out");
    fadeTimer = window.setTimeout(() => {
      fadeTimer = null;
      switchMode(targetView);
    }, FADE_MS);

    return cleanup;
  }, [targetView]);

  useEffect(() => {
    // 解锁后的接口错误用全局提示；锁屏阶段的错误由 LockPage 内联展示，避免重复弹窗
    if (session.error && unlocked) {
      message.error(session.error);
    }
  }, [session.error, unlocked, message]);

  const handleLock = useCallback(() => {
    // 先写入文案，再走与自动锁定相同的状态机
    setLockReason("已手动锁定");
    void session.lock();
  }, [session.lock]);

  const handleOpenDoc = useCallback((docId: string) => {
    setPendingDocId(docId);
    setPage("workbench");
  }, []);

  const handleDocOpened = useCallback(() => setPendingDocId(null), []);

  // 启动页同时是连接失败的重试入口，因此错误态优先于加载态渲染
  if (view === "boot" || !session.status) {
    return (
      <div className="boot-screen">
        {/* 后端未就绪时给出可重试的错误卡片，而不是让用户空白等待 */}
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
      {/* 标题栏常驻窗口顶部，为系统绘制的窗口按钮留出覆盖层高度 */}
      <TitleBar />
      <AppLayout
        status={session.status}
        page={page}
        onPageChange={setPage}
        onLock={handleLock}
      >
        {/* 页面按需挂载，切换菜单时卸载旧页面以释放桌面端内存 */}
        {page === "workbench" ? (
          <WorkbenchPage
            byCode={byCode}
            llmMode={session.status.llm_mode}
            maxDocs={session.status.max_docs}
            openDocId={pendingDocId}
            onOpenedDoc={handleDocOpened}
          />
        ) : null}
        {page === "batch" ? <BatchPage onOpenDoc={handleOpenDoc} /> : null}
        {page === "types" ? (
          <TypesPage types={types} loading={typesLoading} onRefresh={refreshTypes} />
        ) : null}
        {page === "reveal" ? <RevealPage byCode={byCode} /> : null}
        {page === "settings" ? <SettingsPage onSessionRefresh={session.refresh} /> : null}
      </AppLayout>
    </>
  );
}
