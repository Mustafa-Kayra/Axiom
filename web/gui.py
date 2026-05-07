from __future__ import annotations

import argparse
import errno
import json
import os
import re
import sys
import subprocess
import threading
import webbrowser
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# PTY support: Unix/Linux only
if sys.platform != 'win32':
    import pty
    import select

WEB_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEB_DIR.parent
for candidate in (str(REPO_ROOT), str(WEB_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

try:
  from web.model_registry import (
        DEFAULT_MAX_TOKENS,
        DEFAULT_MODEL_ID,
        DEFAULT_SYSTEM_PROMPT,
        DEFAULT_TEMPERATURE,
        load_models,
        select_model,
    )
except ModuleNotFoundError:
  from model_registry import (  # type: ignore
        DEFAULT_MAX_TOKENS,
        DEFAULT_MODEL_ID,
        DEFAULT_SYSTEM_PROMPT,
        DEFAULT_TEMPERATURE,
        load_models,
        select_model,
    )


CHAT_PROMPT_MARKER = "(\u30c4\u00bb "
MODEL_PROMPT_MARKER = "Enter model number to select (or Enter to keep current): "
RAW_BEGIN = "--- RAW BEGIN ---"
RAW_END = "--- RAW END ---"
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Axiom Web GUI</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #07111f;
      --bg-2: #0d1b2a;
      --panel: rgba(11, 18, 32, 0.82);
      --panel-strong: rgba(18, 29, 48, 0.96);
      --text: #e9f1ff;
      --muted: #90a4c3;
      --accent: #64d2ff;
      --accent-2: #8b5cf6;
      --good: #31d0aa;
      --warn: #ffb86b;
      --danger: #ff6b8b;
      --border: rgba(148, 163, 184, 0.16);
      --shadow: 0 24px 90px rgba(0, 0, 0, 0.42);
      --radius: 22px;
      --radius-sm: 14px;
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
      --sans: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      font-family: var(--sans);
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(100, 210, 255, 0.18), transparent 30%),
        radial-gradient(circle at 85% 10%, rgba(139, 92, 246, 0.20), transparent 26%),
        linear-gradient(160deg, var(--bg), var(--bg-2) 72%);
      overflow: hidden;
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
      background-size: 42px 42px;
      mask-image: linear-gradient(to bottom, rgba(0,0,0,0.65), transparent 92%);
      opacity: 0.35;
    }

    .app {
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 18px;
      height: 100%;
      padding: 18px;
    }

    .sidebar, .workspace {
      background: var(--panel);
      backdrop-filter: blur(18px);
      border: 1px solid var(--border);
      box-shadow: var(--shadow);
      border-radius: var(--radius);
      min-height: 0;
    }

    .sidebar {
      display: grid;
      grid-template-rows: auto auto 1fr auto;
      padding: 18px;
      gap: 14px;
    }

    .brand {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .brand h1 {
      margin: 0;
      font-size: 1.35rem;
      letter-spacing: 0.02em;
    }

    .brand p {
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
      font-size: 0.92rem;
    }

    .chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(148, 163, 184, 0.10);
      color: var(--text);
      border: 1px solid rgba(148, 163, 184, 0.14);
      font-size: 0.82rem;
      white-space: nowrap;
    }

    .chip strong { color: white; font-weight: 650; }

    .form {
      display: grid;
      gap: 12px;
      min-height: 0;
    }

    .field {
      display: grid;
      gap: 6px;
    }

    label {
      font-size: 0.75rem;
      letter-spacing: 0.11em;
      text-transform: uppercase;
      color: var(--muted);
    }

    input, select, textarea, button {
      font: inherit;
    }

    input, select, textarea {
      width: 100%;
      border: 1px solid rgba(148, 163, 184, 0.16);
      background: var(--panel-strong);
      color: var(--text);
      border-radius: var(--radius-sm);
      outline: none;
      transition: border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
    }

    input:focus, select:focus, textarea:focus {
      border-color: rgba(100, 210, 255, 0.55);
      box-shadow: 0 0 0 4px rgba(100, 210, 255, 0.12);
    }

    input, select {
      height: 42px;
      padding: 0 12px;
    }

    textarea {
      min-height: 110px;
      padding: 12px;
      resize: vertical;
      line-height: 1.45;
    }

    .row-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }

    .actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }

    button {
      border: 0;
      border-radius: 14px;
      padding: 12px 14px;
      color: white;
      cursor: pointer;
      font-weight: 650;
      transition: transform 0.15s ease, filter 0.15s ease, opacity 0.15s ease;
    }

    button:hover { transform: translateY(-1px); }
    button:disabled { opacity: 0.55; cursor: not-allowed; transform: none; }

    .primary {
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
    }

    .secondary {
      background: rgba(148, 163, 184, 0.18);
      border: 1px solid rgba(148, 163, 184, 0.18);
    }

    .note {
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.45;
    }

    .workspace {
      display: grid;
      grid-template-rows: auto 1fr auto;
      min-height: 0;
      overflow: hidden;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 18px 20px 14px;
      border-bottom: 1px solid var(--border);
    }

    .topbar .status {
      color: var(--muted);
      font-size: 0.92rem;
    }

    .topbar .title {
      font-size: 1rem;
      font-weight: 650;
    }

    .chat {
      padding: 18px;
      overflow: auto;
      display: grid;
      gap: 14px;
      align-content: start;
    }

    .message {
      max-width: min(820px, 92%);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 14px 16px;
      line-height: 1.55;
      white-space: pre-wrap;
      word-break: break-word;
      animation: fadeUp 0.18s ease both;
    }

    .message.user {
      margin-left: auto;
      background: linear-gradient(135deg, rgba(100, 210, 255, 0.16), rgba(139, 92, 246, 0.12));
    }

    .message.assistant {
      background: rgba(10, 16, 28, 0.72);
    }

    .message.system {
      background: rgba(49, 208, 170, 0.08);
      border-color: rgba(49, 208, 170, 0.18);
      color: #cffdf1;
    }

    .message.error {
      background: rgba(255, 107, 139, 0.12);
      border-color: rgba(255, 107, 139, 0.22);
      color: #ffd5dd;
    }

    .bubble-meta {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.10em;
    }

    .footer {
      display: grid;
      gap: 12px;
      padding: 14px 18px 18px;
      border-top: 1px solid var(--border);
      background: rgba(0, 0, 0, 0.14);
    }

    .composer {
      display: grid;
      gap: 10px;
    }

    .composer-row {
      display: flex;
      gap: 10px;
      align-items: end;
    }

    .composer-row textarea {
      flex: 1;
      min-height: 82px;
      max-height: 240px;
    }

    .send {
      min-width: 140px;
      height: 82px;
    }

    .inline-actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    .inline-actions button {
      min-width: 120px;
      height: 40px;
    }

    .muted {
      color: var(--muted);
    }

    .tiny {
      font-size: 0.8rem;
    }

    code, pre {
      font-family: var(--mono);
    }

    pre {
      margin: 0;
      white-space: pre-wrap;
    }

    @keyframes fadeUp {
      from { transform: translateY(6px); opacity: 0; }
      to { transform: translateY(0); opacity: 1; }
    }

    @media (max-width: 1040px) {
      body { overflow: auto; }
      .app {
        grid-template-columns: 1fr;
        height: auto;
        min-height: 100%;
      }
      .workspace { min-height: 74vh; }
    }

    @media (max-width: 720px) {
      .app { padding: 10px; gap: 10px; }
      .sidebar, .workspace { border-radius: 18px; }
      .row-2, .actions { grid-template-columns: 1fr; }
      .composer-row { flex-direction: column; align-items: stretch; }
      .send { width: 100%; height: 46px; }
      .message { max-width: 100%; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        <h1>Axiom Web GUI</h1>
        <p>Browser-based chat UI backed by a hidden <code>axiomai chat</code> terminal session. Models are loaded from <code>src/axiomai/model/config.py</code>.</p>
      </div>

      <div class="chip-row" id="chips"></div>

      <div class="form">
        <div class="field">
          <label for="apiUrl">API URL</label>
          <input id="apiUrl" placeholder="http://localhost:8000/v1" />
        </div>

        <div class="field">
          <label for="apiKey">API Key</label>
          <input id="apiKey" type="password" placeholder="Bearer token" />
        </div>

        <div class="field">
          <label for="modelSelect">Model</label>
          <select id="modelSelect"></select>
        </div>

        <div class="field">
          <label for="systemPrompt">System Prompt</label>
          <textarea id="systemPrompt" placeholder="Assistant instructions"></textarea>
        </div>

        <div class="row-2">
          <div class="field">
            <label for="temperature">Temperature</label>
            <input id="temperature" type="number" min="0" max="2" step="0.1" />
          </div>
          <div class="field">
            <label for="maxTokens">Max Tokens</label>
            <input id="maxTokens" type="number" min="1" step="1" />
          </div>
        </div>

        <div class="actions">
          <button class="secondary" id="loadDefaults">Reset Defaults</button>
          <button class="secondary" id="clearChat">Clear Chat</button>
        </div>
      </div>

      <div class="note">
        <strong>Tips</strong>
        <div class="tiny muted">- Messages stay in the browser via localStorage.</div>
        <div class="tiny muted">- The backend keeps a hidden <code>axiomai chat</code> session open and reuses it for your selected model.</div>
      </div>
    </aside>

    <section class="workspace">
      <div class="topbar">
        <div>
          <div class="title">Conversation</div>
          <div class="status" id="statusText">Idle</div>
        </div>
        <div class="chip-row">
          <span class="chip"><strong id="activeModelLabel">-</strong></span>
          <span class="chip"><strong id="messageCount">0</strong> messages</span>
        </div>
      </div>

      <div class="chat" id="chat"></div>

      <div class="footer">
        <div class="composer">
          <div class="composer-row">
            <textarea id="messageInput" placeholder="Write a message. Shift+Enter for a new line, Enter to send."></textarea>
            <button class="primary send" id="sendButton">Send</button>
          </div>
          <div class="inline-actions">
            <button class="secondary" id="saveState">Save State</button>
            <button class="secondary" id="restoreState">Restore State</button>
            <button class="secondary" id="exportChat">Export JSON</button>
          </div>
          <div class="note">Everything is local except the message sent to the hidden Axiom CLI session.</div>
        </div>
      </div>
    </section>
  </div>

  <script>
    const STORAGE_KEY = "axiom-web-gui-state-v1";
    const DEFAULTS = {
      apiUrl: "",
      apiKey: "",
      modelId: "",
      systemPrompt: "",
      temperature: 0.7,
      maxTokens: 2048,
      conversation: []
    };

    const els = {
      chips: document.getElementById("chips"),
      apiUrl: document.getElementById("apiUrl"),
      apiKey: document.getElementById("apiKey"),
      modelSelect: document.getElementById("modelSelect"),
      systemPrompt: document.getElementById("systemPrompt"),
      temperature: document.getElementById("temperature"),
      maxTokens: document.getElementById("maxTokens"),
      loadDefaults: document.getElementById("loadDefaults"),
      clearChat: document.getElementById("clearChat"),
      chat: document.getElementById("chat"),
      messageInput: document.getElementById("messageInput"),
      sendButton: document.getElementById("sendButton"),
      statusText: document.getElementById("statusText"),
      activeModelLabel: document.getElementById("activeModelLabel"),
      messageCount: document.getElementById("messageCount"),
      saveState: document.getElementById("saveState"),
      restoreState: document.getElementById("restoreState"),
      exportChat: document.getElementById("exportChat"),
    };

    const state = {
      models: [],
      apiUrl: "",
      apiKey: "",
      modelId: "",
      systemPrompt: "",
      temperature: 0.7,
      maxTokens: 2048,
      conversation: []
    };

    function escapeHtml(text) {
      return String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function fmtTime() {
      return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }

    function setStatus(text, tone = "muted") {
      els.statusText.textContent = text;
      els.statusText.style.color = tone === "error" ? "var(--danger)" : tone === "good" ? "var(--good)" : "var(--muted)";
    }

    function renderChips() {
      const chips = [];
      chips.push(`<span class="chip"><strong>${escapeHtml(state.models.length)}</strong> models</span>`);
      chips.push(`<span class="chip"><strong>${escapeHtml(state.apiUrl || "unset")}</strong></span>`);
      if (state.modelId) {
        const selected = state.models.find((m) => m.id === state.modelId);
        chips.push(`<span class="chip"><strong>${escapeHtml(selected ? selected.name : state.modelId)}</strong></span>`);
      }
      els.chips.innerHTML = chips.join("");
    }

    function renderModelOptions() {
      els.modelSelect.innerHTML = state.models.map((model, index) => {
        const active = model.id === state.modelId ? "selected" : "";
        const label = `${index + 1}. ${model.name} (${model.id})`;
        return `<option value="${escapeHtml(model.id)}" ${active}>${escapeHtml(label)}</option>`;
      }).join("");

      const selected = state.models.find((model) => model.id === state.modelId);
      els.activeModelLabel.textContent = selected ? selected.name : state.modelId || "-";
    }

    function renderForm() {
      els.apiUrl.value = state.apiUrl;
      els.apiKey.value = state.apiKey;
      els.systemPrompt.value = state.systemPrompt;
      els.temperature.value = state.temperature;
      els.maxTokens.value = state.maxTokens;
      renderChips();
      renderModelOptions();
      updateMessageCount();
    }

    function updateMessageCount() {
      els.messageCount.textContent = String(state.conversation.length);
    }

    function renderConversation() {
      if (!state.conversation.length) {
        els.chat.innerHTML = `
          <div class="message system">
            <div class="bubble-meta"><span>System</span><span>${fmtTime()}</span></div>
            <div>Chat is empty. Send a message to start.</div>
          </div>`;
        return;
      }

      els.chat.innerHTML = state.conversation.map((item) => {
        const role = item.role || "assistant";
        const cls = role === "user" ? "user" : role === "system" ? "system" : role === "error" ? "error" : "assistant";
        return `
          <div class="message ${cls}">
            <div class="bubble-meta"><span>${escapeHtml(role)}</span><span>${escapeHtml(item.time || fmtTime())}</span></div>
            <div>${escapeHtml(item.content)}</div>
          </div>`;
      }).join("");

      els.chat.scrollTop = els.chat.scrollHeight;
    }

    function persistState() {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        apiUrl: state.apiUrl,
        apiKey: state.apiKey,
        modelId: state.modelId,
        systemPrompt: state.systemPrompt,
        temperature: state.temperature,
        maxTokens: state.maxTokens,
        conversation: state.conversation
      }));
      setStatus("State saved locally", "good");
    }

    function restoreState() {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        setStatus("No saved state found", "error");
        return;
      }
      try {
        const saved = JSON.parse(raw);
        state.apiUrl = saved.apiUrl || state.apiUrl;
        state.apiKey = saved.apiKey || "";
        state.modelId = saved.modelId || state.modelId;
        state.systemPrompt = saved.systemPrompt || state.systemPrompt;
        state.temperature = Number(saved.temperature ?? state.temperature);
        state.maxTokens = Number(saved.maxTokens ?? state.maxTokens);
        state.conversation = Array.isArray(saved.conversation) ? saved.conversation : [];
        syncInputs();
        renderAll();
        setStatus("State restored from browser storage", "good");
      } catch (error) {
        setStatus(`Could not restore state: ${error.message}`, "error");
      }
    }

    function resetToDefaults() {
      const defaults = window.__AXIOM_DEFAULTS__;
      state.apiUrl = defaults.apiUrl || "";
      state.apiKey = defaults.apiKey || "";
      state.modelId = defaults.modelId || "";
      state.systemPrompt = defaults.systemPrompt || "";
      state.temperature = defaults.temperature ?? 0.7;
      state.maxTokens = defaults.maxTokens ?? 2048;
      state.conversation = [];
      syncInputs();
      renderAll();
      setStatus("Loaded defaults from the backend", "good");
    }

    function syncInputs() {
      els.apiUrl.value = state.apiUrl;
      els.apiKey.value = state.apiKey;
      els.systemPrompt.value = state.systemPrompt;
      els.temperature.value = state.temperature;
      els.maxTokens.value = state.maxTokens;
      els.modelSelect.value = state.modelId;
    }

    function renderAll() {
      renderChips();
      renderModelOptions();
      renderConversation();
      updateMessageCount();
    }

    async function loadConfig() {
      const response = await fetch("/api/config");
      if (!response.ok) {
        throw new Error(`Failed to load config (${response.status})`);
      }
      const config = await response.json();
      state.models = config.models || [];
      state.apiUrl = config.apiUrl || "";
      state.apiKey = config.apiKey || "";
      state.modelId = config.modelId || "";
      state.systemPrompt = config.systemPrompt || "";
      state.temperature = config.temperature ?? 0.7;
      state.maxTokens = config.maxTokens ?? 2048;
      state.conversation = loadConversationFromStorage();
      if (!state.conversation.length) {
        state.conversation = [];
      }
      renderForm();
      renderAll();
    }

    function loadConversationFromStorage() {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return [];
      }
      try {
        const saved = JSON.parse(raw);
        if (Array.isArray(saved.conversation)) {
          return saved.conversation;
        }
      } catch (_error) {
        return [];
      }
      return [];
    }

    function appendMessage(role, content) {
      state.conversation.push({ role, content, time: fmtTime() });
      renderConversation();
      updateMessageCount();
      persistState();
    }

    async function sendMessage() {
      const message = els.messageInput.value.trim();
      if (!message) {
        return;
      }

      if (!state.apiUrl) {
        setStatus("Set an API URL first", "error");
        return;
      }

      const selectedModel = state.models.find((model) => model.id === state.modelId) || state.models[0];
      if (!selectedModel) {
        setStatus("No model available", "error");
        return;
      }

      els.sendButton.disabled = true;
      setStatus("Sending request...", "good");

      const conversation = state.conversation.filter((item) => item.role !== "system").map((item) => ({
        role: item.role,
        content: item.content,
      }));

      appendMessage("user", message);
      els.messageInput.value = "";

      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            apiUrl: els.apiUrl.value.trim(),
            apiKey: els.apiKey.value.trim(),
            modelId: els.modelSelect.value,
            systemPrompt: els.systemPrompt.value,
            temperature: Number(els.temperature.value || 0.7),
            maxTokens: Number(els.maxTokens.value || 2048),
            conversation,
            message,
          }),
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || `Request failed (${response.status})`);
        }

        appendMessage("assistant", data.assistant || "");
        setStatus(`Reply from ${selectedModel.name}`, "good");
      } catch (error) {
        appendMessage("error", error.message);
        setStatus(error.message, "error");
      } finally {
        els.sendButton.disabled = false;
      }
    }

    async function exportChat() {
      const blob = new Blob([JSON.stringify({
        exportedAt: new Date().toISOString(),
        apiUrl: els.apiUrl.value.trim(),
        modelId: els.modelSelect.value,
        systemPrompt: els.systemPrompt.value,
        conversation: state.conversation,
      }, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "axiom-chat.json";
      a.click();
      URL.revokeObjectURL(url);
      setStatus("Chat exported", "good");
    }

    els.sendButton.addEventListener("click", sendMessage);
    els.clearChat.addEventListener("click", () => {
      state.conversation = [];
      renderAll();
      persistState();
      fetch("/api/reset", { method: "POST" }).catch(() => {});
      setStatus("Conversation cleared", "good");
    });
    els.loadDefaults.addEventListener("click", resetToDefaults);
    els.saveState.addEventListener("click", persistState);
    els.restoreState.addEventListener("click", restoreState);
    els.exportChat.addEventListener("click", exportChat);
    els.modelSelect.addEventListener("change", () => {
      state.modelId = els.modelSelect.value;
      renderChips();
      persistState();
    });

    [els.apiUrl, els.apiKey, els.systemPrompt, els.temperature, els.maxTokens].forEach((input) => {
      input.addEventListener("change", () => {
        state.apiUrl = els.apiUrl.value.trim();
        state.apiKey = els.apiKey.value;
        state.systemPrompt = els.systemPrompt.value;
        state.temperature = Number(els.temperature.value || 0.7);
        state.maxTokens = Number(els.maxTokens.value || 2048);
        renderChips();
      });
    });

    els.messageInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
      }
    });

    window.addEventListener("beforeunload", persistState);

    window.__AXIOM_DEFAULTS__ = {
      apiUrl: "__DEFAULT_API_URL__",
      apiKey: "__DEFAULT_API_KEY__",
      modelId: "__DEFAULT_MODEL_ID__",
      systemPrompt: "__DEFAULT_SYSTEM_PROMPT__",
      temperature: __DEFAULT_TEMPERATURE__,
      maxTokens: __DEFAULT_MAX_TOKENS__,
    };

    loadConfig().catch((error) => {
      setStatus(error.message, "error");
      els.chat.innerHTML = `
        <div class="message error">
          <div class="bubble-meta"><span>Error</span><span>${fmtTime()}</span></div>
          <div>${escapeHtml(error.message)}</div>
        </div>`;
    });
  </script>
</body>
</html>
"""


@dataclass
class AppConfig:
    models: list[dict[str, Any]]
    default_api_url: str
    default_api_key: str
    default_model_id: str
    default_system_prompt: str
    default_temperature: float
    default_max_tokens: int
    project_root: Path
    bridge: AxiomCliBridge


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler: BaseHTTPRequestHandler, status: int, body: str, *, content_type: str = "text/html; charset=utf-8") -> None:
    data = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(content_length) if content_length else b"{}"
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON request body") from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON body must be an object")
    return parsed


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text).replace("\r", "")


def _model_index_for_id(models: list[dict[str, Any]], model_id: str) -> int:
    for index, model in enumerate(models, 1):
        if model.get("id") == model_id:
            return index
    raise ValueError(f"Unknown model id: {model_id}")


def _ensure_tutorial_guard() -> None:
    tutorial_flag = Path.home() / ".aye" / ".tutorial_ran"
    tutorial_flag.parent.mkdir(parents=True, exist_ok=True)
    tutorial_flag.touch(exist_ok=True)


class _PtySession:
    def __init__(self, command: list[str], *, cwd: Path, env: dict[str, str], timeout: float = 180.0) -> None:
        self._timeout = timeout
        self._buffer = ""
        self._master_fd, slave_fd = pty.openpty()
        self._proc = subprocess.Popen(
            command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=str(cwd),
            env=env,
            close_fds=True,
        )
        os.close(slave_fd)

    @property
    def alive(self) -> bool:
        return self._proc.poll() is None

    def write(self, text: str) -> None:
        os.write(self._master_fd, text.encode("utf-8"))

    def read_until(self, marker: str, *, timeout: float | None = None) -> str:
        deadline = time.monotonic() + (timeout if timeout is not None else self._timeout)

        while True:
            marker_index = self._buffer.find(marker)
            if marker_index != -1:
                chunk = self._buffer[:marker_index]
                self._buffer = self._buffer[marker_index + len(marker):]
                return _strip_ansi(chunk)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for {marker!r}")

            if self._proc.poll() is not None:
                raise RuntimeError(_strip_ansi(self._buffer) or "Axiom CLI exited unexpectedly.")

            readable, _, _ = select.select([self._master_fd], [], [], min(0.1, remaining))
            if not readable:
                continue

            try:
                data = os.read(self._master_fd, 4096)
            except OSError as exc:
                if exc.errno in {errno.EIO, errno.EBADF}:
                    raise RuntimeError(_strip_ansi(self._buffer) or "Axiom CLI closed the terminal unexpectedly.") from exc
                raise

            if not data:
                continue

            self._buffer += data.decode("utf-8", errors="replace")

    def terminate(self) -> None:
        try:
            if self.alive:
                self.write("exit\n")
                self._proc.wait(timeout=2.0)
        except Exception:
            try:
                self._proc.terminate()
            except Exception:
                pass
        finally:
            try:
                os.close(self._master_fd)
            except Exception:
                pass


class AxiomCliBridge:
    def __init__(self, *, project_root: Path, models: list[dict[str, Any]]) -> None:
        self.project_root = project_root
        self.models = models
        self._lock = threading.Lock()
        self._session: _PtySession | None = None
        self._active_model_id: str | None = None

    def reset(self) -> None:
        with self._lock:
            if self._session is not None:
                self._session.terminate()
            self._session = None
            self._active_model_id = None

    def chat(self, message: str, model_id: str) -> str:
        with self._lock:
            if self._session is None or self._active_model_id != model_id or not self._session.alive:
                self._start_session(model_id)

            assert self._session is not None
            self._session.write(f"{message}\n")
            assistant_output = self._session.read_until(CHAT_PROMPT_MARKER, timeout=240.0)

            self._session.write("raw\n")
            raw_output = self._session.read_until(CHAT_PROMPT_MARKER, timeout=120.0)
            raw_text = self._extract_raw_text(raw_output)
            if raw_text:
                return raw_text

            fallback_text = self._extract_last_block(assistant_output)
            if fallback_text:
                return fallback_text

            raise RuntimeError("Axiom CLI returned an empty response.")

    def _start_session(self, model_id: str) -> None:
        self.reset()
        _ensure_tutorial_guard()

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["AYE_TELEMETRY_OPT_IN"] = "off"
        env.setdefault("AYE_FEEDBACK_OPT_IN", "off")

        command = [sys.executable, "-m", "axiomai", "chat", "--root", str(self.project_root)]
        session = _PtySession(command, cwd=REPO_ROOT, env=env)

        try:
            session.read_until(CHAT_PROMPT_MARKER, timeout=240.0)
            model_index = _model_index_for_id(self.models, model_id)
            session.write("model\n")
            session.read_until(MODEL_PROMPT_MARKER, timeout=60.0)
            session.write(f"{model_index}\n")
            session.read_until(CHAT_PROMPT_MARKER, timeout=240.0)
        except Exception:
            session.terminate()
            raise

        self._session = session
        self._active_model_id = model_id

    def _extract_raw_text(self, text: str) -> str:
        cleaned = _strip_ansi(text)
        begin = cleaned.find(RAW_BEGIN)
        end = cleaned.find(RAW_END)
        if begin == -1 or end == -1 or end <= begin:
            return cleaned.strip()

        return cleaned[begin + len(RAW_BEGIN):end].strip()

    def _extract_last_block(self, text: str) -> str:
        cleaned = _strip_ansi(text).strip()
        if not cleaned:
            return ""
        blocks = [block.strip() for block in cleaned.split("\n\n") if block.strip()]
        return blocks[-1] if blocks else cleaned


class WebGUIHandler(BaseHTTPRequestHandler):
    app_config: AppConfig

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/index.html"}:
            html = (
                HTML_PAGE
                .replace("__DEFAULT_API_URL__", self.app_config.default_api_url.replace("\\", "\\\\").replace("\"", "\\\""))
                .replace("__DEFAULT_API_KEY__", self.app_config.default_api_key.replace("\\", "\\\\").replace("\"", "\\\""))
                .replace("__DEFAULT_MODEL_ID__", self.app_config.default_model_id.replace("\\", "\\\\").replace("\"", "\\\""))
                .replace("__DEFAULT_SYSTEM_PROMPT__", self.app_config.default_system_prompt.replace("\\", "\\\\").replace("\"", "\\\""))
                .replace("__DEFAULT_TEMPERATURE__", json.dumps(self.app_config.default_temperature))
                .replace("__DEFAULT_MAX_TOKENS__", json.dumps(self.app_config.default_max_tokens))
            )
            _text_response(self, HTTPStatus.OK, html)
            return

        if self.path == "/api/config":
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "models": self.app_config.models,
              "apiUrl": "axiomai chat (backend)",
              "apiKey": "managed by Axiom CLI backend",
                    "modelId": self.app_config.default_model_id,
                    "systemPrompt": self.app_config.default_system_prompt,
                    "temperature": self.app_config.default_temperature,
                    "maxTokens": self.app_config.default_max_tokens,
                },
            )
            return

        if self.path == "/api/models":
            _json_response(self, HTTPStatus.OK, {"models": self.app_config.models})
            return

        if self.path == "/api/reset":
          self.app_config.bridge.reset()
          _json_response(self, HTTPStatus.OK, {"ok": True})
          return

        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/chat":
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return

        try:
            body = _read_json_body(self)
            message = str(body.get("message", "")).strip()
            model_id = str(body.get("modelId", "")).strip() or self.app_config.default_model_id

            if not message:
                raise ValueError("Message cannot be empty")

            selected = next((model for model in self.app_config.models if model.get("id") == model_id), None)
            if selected is None:
                selected = select_model(self.app_config.models, model_id)

            assistant_text = self.app_config.bridge.chat(message, selected["id"])
            _json_response(self, HTTPStatus.OK, {"assistant": assistant_text})
        except (ValueError, RuntimeError, TimeoutError) as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


def build_argument_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="Axiom browser-based web GUI")
  parser.add_argument("--host", default=os.environ.get("AXIOM_WEB_HOST", "127.0.0.1"), help="Host to bind")
  parser.add_argument("--port", default=int(os.environ.get("AXIOM_WEB_PORT", "8765")), type=int, help="Port to bind")
  parser.add_argument("--model", default=None, help="Default model id or number")
  parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT, help="Default system prompt")
  parser.add_argument("--temperature", default=DEFAULT_TEMPERATURE, type=float, help="Default temperature")
  parser.add_argument("--max-tokens", default=DEFAULT_MAX_TOKENS, type=int, help="Default max tokens")
  parser.add_argument(
    "--project-root",
    default=os.environ.get("AXIOM_WEB_PROJECT_ROOT") or str(REPO_ROOT),
    help="Project root passed to axiomai chat",
  )
  parser.add_argument("--open", action="store_true", help="Open the browser automatically")
  return parser


def create_app_config(args: argparse.Namespace) -> AppConfig:
  models = load_models()
  default_model = select_model(models, args.model)
  project_root = Path(args.project_root).resolve()
  bridge = AxiomCliBridge(project_root=project_root, models=models)
  return AppConfig(
    models=models,
    default_api_url="axiomai chat (backend)",
    default_api_key="managed by Axiom CLI backend",
    default_model_id=default_model["id"],
    default_system_prompt=args.system_prompt,
    default_temperature=args.temperature,
    default_max_tokens=args.max_tokens,
    project_root=project_root,
    bridge=bridge,
  )


def serve(host: str, port: int, app_config: AppConfig, *, open_browser: bool = False) -> None:
  handler_class = type("AxiomWebGUIHandler", (WebGUIHandler,), {"app_config": app_config})
  server = ThreadingHTTPServer((host, port), handler_class)
  url = f"http://{host}:{port}/"
  print(f"Axiom Web GUI running at {url}")
  print("Press Ctrl+C to stop.")

  if open_browser:
    threading.Timer(0.75, lambda: webbrowser.open(url)).start()

  try:
    server.serve_forever()
  except KeyboardInterrupt:
    pass
  finally:
    app_config.bridge.reset()
    server.server_close()


def main(argv: list[str] | None = None) -> int:
  args = build_argument_parser().parse_args(argv)
  app_config = create_app_config(args)
  serve(args.host, args.port, app_config, open_browser=args.open)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
