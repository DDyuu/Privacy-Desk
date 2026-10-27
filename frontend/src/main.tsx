// 渲染进程入口：挂载 React 根节点，并统一注入 Ant Design 中文语言包与品牌主题。
import React from "react";
import ReactDOM from "react-dom/client";
import { App as AntApp, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {/* 主题色与深色侧栏对齐 Electron 窗口底色；AntApp 为 message 等静态方法提供上下文 */}
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#0f766e",
          borderRadius: 8,
          colorBgLayout: "#f5f7fa",
        },
        components: {
          Layout: {
            siderBg: "#0b1220",
            headerBg: "#ffffff",
          },
          Menu: {
            darkItemBg: "#0b1220",
            darkItemSelectedBg: "#0f766e",
          },
        },
      }}
    >
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>,
);
