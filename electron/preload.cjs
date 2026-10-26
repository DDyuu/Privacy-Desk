"use strict";

const { contextBridge } = require("electron");

function readArgument(prefix) {
  const match = process.argv.find((argument) => argument.startsWith(prefix));
  return match ? match.slice(prefix.length) : "";
}

const apiBase = readArgument("--privacy-api-base=") || "http://127.0.0.1:8765";
const token = readArgument("--privacy-token=") || "";

contextBridge.exposeInMainWorld("privacyDesk", { apiBase, token });
