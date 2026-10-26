import React from "react";
import ReactDOM from "react-dom/client";
import { App as AntApp, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
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
