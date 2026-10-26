import { useCallback, useEffect, useState } from "react";
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

export default function App() {
  const session = useSession();
  const { message } = AntApp.useApp();
  const [page, setPage] = useState<PageKey>("workbench");
  const [lockReason, setLockReason] = useState("");
  const [pendingDocId, setPendingDocId] = useState<string | null>(null);

  const unlocked = Boolean(session.status?.unlocked);
  const { types, byCode, loading: typesLoading, refresh: refreshTypes } = useTypes(unlocked);

  useEffect(() => {
    if (unlocked) setLockReason("");
  }, [unlocked]);

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

  if (!session.status) {
    return (
      <>
        <TitleBar />
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
      </>
    );
  }

  if (!unlocked) {
    return (
      <>
        <TitleBar />
        <LockPage
          status={session.status}
          busy={session.busy}
          error={session.error}
          reason={lockReason}
          onSetup={session.setup}
          onUnlock={session.unlock}
        />
      </>
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
