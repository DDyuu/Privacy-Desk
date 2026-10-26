"use strict";

const { app, BrowserWindow, Menu, dialog, ipcMain } = require("electron");
const { spawn, spawnSync } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const BACKEND_START_TIMEOUT_MS = 40000;
const HEALTH_INTERVAL_MS = 500;
const OUTPUT_LIMIT = 8000;
const DEFAULT_DEV_URL = "http://localhost:5173";
const DESIGN_WIDTH = 1440;
const DESIGN_HEIGHT = 960;
const TITLEBAR_HEIGHT = 36;
const WINDOW_FADE_MS = 180;
const LOCK_WIDTH = 460;
const LOCK_HEIGHT = 460;
const LOCK_MIN_WIDTH = 440;
const LOCK_MIN_HEIGHT = 440;

let mainWindow = null;
let windowMode = "lock";
let opacityTimer = null;
let modeAppliedToken = 0;
let backendChild = null;
let backendToken = "";
let backendPort = 0;
let backendOutput = "";
let backendSpawnFailed = false;
let stopping = false;

function projectRoot() {
  return path.join(__dirname, "..");
}

function backendDir() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "backend")
    : path.join(projectRoot(), "backend");
}

function devUrl() {
  return process.env.PRIVACY_DESK_DEV_URL || DEFAULT_DEV_URL;
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = address && typeof address === "object" ? address.port : 0;
      server.close(() => {
        if (port) {
          resolve(port);
        } else {
          reject(new Error("无法获取空闲端口"));
        }
      });
    });
  });
}

function resolveBackendCommand() {
  if (app.isPackaged) {
    const exe = path.join(process.resourcesPath, "backend", "privacy-backend.exe");
    return { command: exe, args: [], cwd: path.dirname(exe) };
  }
  const cwd = backendDir();
  const venvPython = path.join(cwd, ".venv", "Scripts", "python.exe");
  if (fs.existsSync(venvPython)) {
    return { command: venvPython, args: ["run.py"], cwd };
  }
  return { command: "py", args: ["-3.12", "run.py"], cwd };
}

function appendBackendOutput(chunk) {
  backendOutput = (backendOutput + String(chunk)).slice(-OUTPUT_LIMIT);
}

function startBackend(port, token) {
  const target = resolveBackendCommand();
  if (app.isPackaged && !fs.existsSync(target.command)) {
    throw new Error(`未找到后端可执行文件：${target.command}`);
  }

  const env = {
    ...process.env,
    APP_TOKEN: token,
    PRIVACY_DESK_PORT: String(port),
    PRIVACY_DESK_REQUIRE_TOKEN: "1",
    PRIVACY_DESK_REQUIRE_ENCRYPTED_RESOURCES: "1",
  };
  if (app.isPackaged) {
    env.PRIVACY_DESK_ENFORCE_INTEGRITY = "1";
  }

  const child = spawn(target.command, target.args, {
    cwd: target.cwd,
    env,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  backendChild = child;
  child.stdout?.on("data", appendBackendOutput);
  child.stderr?.on("data", appendBackendOutput);
  child.on("error", (error) => {
    backendSpawnFailed = true;
    appendBackendOutput(`\n[启动进程失败] ${error.message}\n`);
  });
  return child;
}

function checkHealth(port, token) {
  return new Promise((resolve) => {
    const request = http.get(
      {
        host: "127.0.0.1",
        port,
        path: "/api/v1/health",
        headers: { "X-App-Token": token },
        timeout: 2000,
      },
      (response) => {
        let body = "";
        response.setEncoding("utf8");
        response.on("data", (chunk) => {
          body += chunk;
        });
        response.on("end", () => {
          if (response.statusCode !== 200) {
            resolve(false);
            return;
          }
          try {
            resolve(JSON.parse(body).status === "ok");
          } catch {
            resolve(false);
          }
        });
      }
    );
    request.on("timeout", () => {
      request.destroy();
      resolve(false);
    });
    request.on("error", () => resolve(false));
  });
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function backendExited() {
  if (backendSpawnFailed) return true;
  if (!backendChild) return false;
  return backendChild.exitCode !== null || backendChild.signalCode !== null;
}

async function waitForBackend(port, token) {
  const deadline = Date.now() + BACKEND_START_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (backendExited()) return false;
    if (await checkHealth(port, token)) return true;
    await delay(HEALTH_INTERVAL_MS);
  }
  return false;
}

function stopBackend() {
  if (stopping) return;
  stopping = true;
  const child = backendChild;
  backendChild = null;
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  try {
    child.kill();
  } catch {
    /* 进程可能已退出 */
  }
  if (process.platform === "win32" && child.pid) {
    try {
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
        windowsHide: true,
        stdio: "ignore",
      });
    } catch {
      /* 兜底失败不阻塞退出 */
    }
  }
}

function describeBackendFailure() {
  const tail = backendOutput.split(backendToken).join("***").slice(-4000);
  return tail.trim() || "（后端没有输出任何日志）";
}

function isAllowedNavigation(target) {
  try {
    if (app.isPackaged) {
      const indexPath = pathToFileURL(
        path.join(process.resourcesPath, "ui", "index.html")
      ).toString();
      return target === indexPath;
    }
    const targetUrl = new URL(target);
    const allowed = new URL(devUrl());
    if (targetUrl.origin === allowed.origin) return true;
    const fallbackIndex = pathToFileURL(
      path.join(projectRoot(), "frontend", "dist", "index.html")
    ).toString();
    return target === fallbackIndex;
  } catch {
    return false;
  }
}

/** 按设计基准等比缩放页面，保证任意窗口尺寸下内容完整可见 */
function applyContentZoom(win) {
  if (win.isDestroyed()) return;
  // 小窗登录时不缩放，否则锁屏卡片会被缩得很小
  if (windowMode !== "workbench") {
    win.webContents.setZoomFactor(1);
    return;
  }
  const [width, height] = win.getContentSize();
  const scale = Math.min(width / DESIGN_WIDTH, height / DESIGN_HEIGHT);
  win.webContents.setZoomFactor(Math.min(Math.max(scale, 0.5), 2));
}

/** 整窗透明度渐变：让窗口尺寸切换发生在不可见的时候 */
function animateWindowOpacity(win, target) {
  if (opacityTimer !== null) {
    clearInterval(opacityTimer);
    opacityTimer = null;
  }
  const from = win.getOpacity();
  if (from === target) return;
  const started = Date.now();
  opacityTimer = setInterval(() => {
    if (win.isDestroyed()) {
      clearInterval(opacityTimer);
      opacityTimer = null;
      return;
    }
    const progress = Math.min((Date.now() - started) / WINDOW_FADE_MS, 1);
    win.setOpacity(from + (target - from) * progress);
    if (progress >= 1) {
      clearInterval(opacityTimer);
      opacityTimer = null;
    }
  }, 16);
}

function enterWorkbenchMode(win) {
  windowMode = "workbench";
  win.setResizable(true);
  win.setMaximizable(true);
  win.setMinimumSize(960, 640);
  win.setAspectRatio(DESIGN_WIDTH / DESIGN_HEIGHT);
  win.setContentSize(DESIGN_WIDTH, DESIGN_HEIGHT);
  win.center();
  applyContentZoom(win);
}

function enterLockMode(win) {
  windowMode = "lock";
  if (win.isMaximized()) win.unmaximize();
  win.setAspectRatio(0);
  win.setMinimumSize(LOCK_MIN_WIDTH, LOCK_MIN_HEIGHT);
  win.setContentSize(LOCK_WIDTH, LOCK_HEIGHT);
  win.center();
  // 锁屏是固定尺寸的小卡片，只保留最小化与关闭
  win.setMaximizable(false);
  win.setResizable(false);
  win.webContents.setZoomFactor(1);
}

/** 尺寸与缩放应用后通知渲染进程，避免新界面先按旧尺寸布局再被拉伸 */
function notifyWindowModeApplied(win, mode) {
  const token = ++modeAppliedToken;
  setTimeout(() => {
    if (token !== modeAppliedToken || win.isDestroyed()) return;
    win.webContents.send("window:mode-applied", mode);
  }, 80);
}

function createWindow(port, token) {
  const win = new BrowserWindow({
    width: LOCK_WIDTH,
    height: LOCK_HEIGHT,
    useContentSize: true,
    minWidth: LOCK_MIN_WIDTH,
    minHeight: LOCK_MIN_HEIGHT,
    show: false,
    backgroundColor: "#f5f7fa",
    // 隐藏系统标题栏，窗口控制按钮以覆盖层形式保留在右上角
    titleBarStyle: "hidden",
    titleBarOverlay: {
      color: "#ffffff",
      symbolColor: "#334155",
      height: TITLEBAR_HEIGHT,
    },
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      additionalArguments: [
        `--privacy-api-base=http://127.0.0.1:${port}`,
        `--privacy-token=${token}`,
      ],
    },
  });

  mainWindow = win;
  windowMode = "lock";
  applyContentZoom(win);
  win.on("resize", () => applyContentZoom(win));
  win.webContents.on("did-finish-load", () => applyContentZoom(win));
  // 禁用快捷键缩放，避免手动放大后内容溢出
  win.webContents.on("before-input-event", (event, input) => {
    if (input.control && ["+", "=", "-", "0"].includes(input.key)) {
      event.preventDefault();
    }
  });
  win.once("ready-to-show", () => win.show());
  win.on("closed", () => {
    if (mainWindow === win) mainWindow = null;
  });
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.webContents.on("will-navigate", (event, url) => {
    if (!isAllowedNavigation(url)) event.preventDefault();
  });
  return win;
}

async function loadUi(win) {
  if (app.isPackaged) {
    await win.loadFile(path.join(process.resourcesPath, "ui", "index.html"));
    return;
  }

  const fallback = path.join(projectRoot(), "frontend", "dist", "index.html");
  try {
    await win.loadURL(devUrl());
  } catch (error) {
    if (fs.existsSync(fallback)) {
      await win.loadFile(fallback);
      return;
    }
    throw error;
  }
}

async function start() {
  try {
    backendPort = await findFreePort();
    backendToken = crypto.randomBytes(32).toString("hex");
    startBackend(backendPort, backendToken);

    const healthy = await waitForBackend(backendPort, backendToken);
    if (!healthy) {
      const detail = describeBackendFailure();
      stopBackend();
      dialog.showErrorBox(
        "后端启动失败",
        `隐私脱敏后端未能在 40 秒内就绪。\n\n${detail}`
      );
      app.quit();
      return;
    }

    const win = createWindow(backendPort, backendToken);
    try {
      await loadUi(win);
    } catch (error) {
      dialog.showErrorBox(
        "界面加载失败",
        `无法加载前端页面：${error instanceof Error ? error.message : String(error)}`
      );
      win.destroy();
      stopBackend();
      app.quit();
    }
  } catch (error) {
    stopBackend();
    dialog.showErrorBox(
      "启动失败",
      error instanceof Error ? error.message : String(error)
    );
    app.quit();
  }
}

const gotLock = app.requestSingleInstanceLock();

if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  });

  app.on("window-all-closed", () => {
    stopBackend();
    app.quit();
  });

  app.on("before-quit", () => {
    stopBackend();
  });

  app.whenReady().then(() => {
    // 去掉 Windows 默认菜单栏（文件 / 编辑 / 视图 / 窗口 / 帮助）
    Menu.setApplicationMenu(null);
    // 渲染进程切到工作台/锁屏时，同步切换窗口尺寸
    ipcMain.on("window:mode", (event, mode) => {
      const win = mainWindow;
      if (!win || win.isDestroyed() || event.sender !== win.webContents) return;
      if (mode === "workbench") {
        enterWorkbenchMode(win);
        notifyWindowModeApplied(win, "workbench");
      } else if (mode === "lock") {
        enterLockMode(win);
        notifyWindowModeApplied(win, "lock");
      }
    });
    ipcMain.on("window:fade", (event, direction) => {
      const win = mainWindow;
      if (!win || win.isDestroyed() || event.sender !== win.webContents) return;
      animateWindowOpacity(win, direction === "out" ? 0 : 1);
    });
    start();
  });
}
