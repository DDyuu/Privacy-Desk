"use strict";

const { contextBridge, ipcRenderer } = require("electron");

function readArgument(prefix) {
  const match = process.argv.find((argument) => argument.startsWith(prefix));
  return match ? match.slice(prefix.length) : "";
}

const apiBase = readArgument("--privacy-api-base=") || "http://127.0.0.1:8765";
const token = readArgument("--privacy-token=") || "";

contextBridge.exposeInMainWorld("privacyDesk", {
  apiBase,
  token,
  setWindowMode: (mode) => {
    ipcRenderer.send("window:mode", mode === "workbench" ? "workbench" : "lock");
  },
  fadeWindow: (direction) => {
    ipcRenderer.send("window:fade", direction === "out" ? "out" : "in");
  },
  onWindowModeApplied: (callback) => {
    const listener = (_event, mode) => callback(mode === "workbench" ? "workbench" : "lock");
    ipcRenderer.on("window:mode-applied", listener);
    return () => ipcRenderer.removeListener("window:mode-applied", listener);
  },
});
