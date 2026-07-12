from __future__ import annotations

import argparse
import importlib
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .empirical.chunked_dialogue import respond_from_chunk_seeds
from .empirical.coding_task_runner import run_coding_task
from .empirical.graph_dialogue import respond_with_graph_dialogue
from .empirical.history_chunked_dialogue import respond_with_history_chunks
from .empirical.seeded_dialogue import respond_from_seed
from .empirical.topic_continuity_dialogue import respond_with_topic_continuity
from .empirical.neural_candidate import generate_neural_candidates
from .empirical.graph_reasoning import run_graph_reasoning
from .empirical.adaptive_renderer import render_verified_response
from .runtime.language_overlay_store import OverlayNotFoundError, utc_now
from .runtime.overlay_repository import create_overlay_repository
from .runtime.japanese_dialogue import respond_japanese
from .runtime.structured_io import run_structured_io
from .runtime.dialogue_state import respond_with_dialogue_state
from .runtime.dialogue_completion import respond_with_completion
from .runtime.web_knowledge_intake import intake_url, list_intakes
from .runtime.general_knowledge_corpus import query_shadow as query_general_knowledge
from .runtime.coding_knowledge_corpus import query_shadow as query_coding_knowledge
from .runtime.wikipedia_general_education import query_shadow as query_wikipedia_general_education, public_metadata as wikipedia_public_metadata
from .runtime.hypothesis_loop import run_hypothesis_loop
from .runtime.layered_reasoning import run_layered_reasoning
from .runtime.daily_dialogue import respond_daily_dialogue
from .runtime.mode_router import select_mode
from .runtime.interpretation_slice import run_interpretation_slice


APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LCE Dialogue Lab</title>
  <style>
    :root { --bg:#f5f7f8; --panel:#fff; --ink:#1d252c; --muted:#65727d; --line:#d8e0e6; --accent:#0f766e; --code:#eef3f5; --good:#047857; --bad:#b42318; --warn:#a16207; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 "Segoe UI", system-ui, sans-serif; }
    header { height:54px; display:flex; align-items:center; justify-content:space-between; padding:0 18px; background:var(--panel); border-bottom:1px solid var(--line); }
    h1 { margin:0; font-size:18px; }
    main { display:grid; grid-template-columns:minmax(320px,420px) minmax(0,1fr); gap:14px; padding:14px; min-height:calc(100vh - 54px); }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; min-width:0; }
    .controls { padding:14px; display:flex; flex-direction:column; gap:12px; }
    label { display:grid; gap:6px; font-weight:650; }
    .hint { color:var(--muted); font-weight:400; font-size:12px; }
    textarea, select, input { width:100%; border:1px solid var(--line); border-radius:6px; padding:9px 10px; font:inherit; }
    textarea { resize:vertical; min-height:128px; }
    #historyInput { min-height:168px; font:12px/1.4 "Cascadia Mono", Consolas, monospace; }
    .row { display:flex; gap:8px; flex-wrap:wrap; }
    button { border:1px solid var(--accent); background:var(--accent); color:#fff; border-radius:6px; padding:9px 12px; font-weight:650; cursor:pointer; }
    button.secondary { background:#fff; color:var(--accent); }
    button:disabled { opacity:.55; cursor:wait; }
    .summary { display:grid; grid-template-columns:repeat(5,minmax(100px,1fr)); gap:8px; padding:14px; border-bottom:1px solid var(--line); }
    .metric { border:1px solid var(--line); border-radius:6px; padding:8px; min-height:58px; }
    .metric span { display:block; color:var(--muted); font-size:11px; text-transform:uppercase; }
    .metric strong { display:block; margin-top:3px; word-break:break-word; }
    .response { padding:14px; border-bottom:1px solid var(--line); display:grid; gap:10px; }
    .responseText { background:#f8fafb; border:1px solid var(--line); border-radius:6px; padding:12px; min-height:78px; white-space:pre-wrap; }
    .chips { display:flex; gap:6px; flex-wrap:wrap; }
    .chip { border:1px solid var(--line); border-radius:999px; padding:3px 8px; color:var(--muted); font-size:12px; }
    .chip.good { color:var(--good); border-color:#a7f3d0; }
    .chip.bad { color:var(--bad); border-color:#fecaca; }
    .chip.warn { color:var(--warn); border-color:#fde68a; }
    .detail { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); }
    .detail section { min-width:0; overflow:auto; padding:14px; }
    .detail section + section { border-left:1px solid var(--line); }
    h2 { margin:0 0 10px; font-size:14px; }
    .chunk { border:1px solid var(--line); border-radius:6px; padding:8px; margin-bottom:8px; background:#fff; }
    .chunkHead { display:flex; justify-content:space-between; gap:8px; color:var(--muted); font-size:12px; margin-bottom:5px; }
    .chunkBody { white-space:pre-wrap; }
    pre { margin:0; background:var(--code); border-radius:6px; padding:10px; overflow:auto; font:12px/1.4 "Cascadia Mono", Consolas, monospace; max-height:520px; }
    @media (max-width:920px) { main { grid-template-columns:1fr; } .summary { grid-template-columns:repeat(2,minmax(0,1fr)); } .detail { grid-template-columns:1fr; } .detail section + section { border-left:0; border-top:1px solid var(--line); } }
  </style>
</head>
<body>
  <header><h1>LCE Dialogue Lab</h1><div id="serverStatus">ready</div></header>
  <main>
    <section class="panel controls">
      <label>Mode
        <select id="mode">
          <option value="auto" selected>Auto route (bounded)</option>
          <option value="interpretation">Interpretation slice v1</option>
          <option value="graph">Graph dialogue</option>
          <option value="japanese">日本語対話</option>
          <option value="dialogue_state">日本語対話 State v1</option>
          <option value="dialogue_completion">日本語対話 Completion v1</option>
          <option value="hypothesis_loop">Hypothesis Verify Revise v1</option>
          <option value="layered_reasoning">Layered reasoning v1</option>
          <option value="daily_dialogue">Daily dialogue v1</option>
          <option value="structured">構造化入出力</option>
          <option value="reasoning">Reasoning + Cube</option>
          <option value="renderer">Adaptive renderer</option>
          <option value="neural">Neural candidates</option>
          <option value="topic">Topic continuity</option>
          <option value="coding">Coding task</option>
          <option value="history">History chunked</option>
          <option value="chunked">Chunked seed</option>
          <option value="seeded">Seeded</option>
          <option value="unknown_language">Unknown language</option>
        </select>
      </label>
      <div id="unknownLanguageControls" hidden>
        <label>Session ID
          <span class="hint">Keeps provisional vocabulary and grammar isolated from other conversations.</span>
          <input id="sessionId" value="vietnamese-demo-1" autocomplete="off">
        </label>
        <label>Observation / teaching signal
          <span class="hint">Optional meaning, correction, scene, or contrast supplied by the teacher.</span>
          <textarea id="teachingInput" placeholder="Example: xin chao means hello in this greeting context."></textarea>
        </label>
      </div>
      <div id="structuredControls" hidden>
        <label>Input data JSON
          <textarea id="structuredData">{"name":"山田","age":"30","role":"user"}</textarea>
        </label>
        <label>Output schema JSON
          <textarea id="structuredSchema">{"type":"object","properties":{"name":{"type":"string"},"age":{"type":"integer"},"role":{"type":"string","enum":["user","admin"]}},"required":["name","age"],"additionalProperties":false}</textarea>
        </label>
      </div>
      <label>Benchmark profile
        <select id="profile">
          <option value="default">Default</option>
          <option value="concise_qa">Concise QA</option>
          <option value="evidence_first">Evidence first</option>
          <option value="instruction_following">Instruction following</option>
          <option value="repair_explicit">Repair explicit</option>
          <option value="coding">Coding</option>
        </select>
      </label>
      <label>Current input
        <textarea id="textInput">Write a Python function solve(numbers) that returns the sum of a list of numbers.</textarea>
      </label>
      <label>History JSON
        <span class="hint">Used by topic, history, and coding modes. Keep coding tasks small and pure-function only.</span>
        <textarea id="historyInput">[
  {"speaker":"user","text":"Use chunk-sized seeds and compose output chunks coherently."},
  {"speaker":"assistant","text":"We will carry chunk seeds through response composition."},
  {"speaker":"user","text":"Safety gates must remain deterministic."}
]</textarea>
      </label>
      <div class="row">
        <button id="runBtn">Run</button>
        <button id="sampleCoding" class="secondary">Coding sample</button>
        <button id="sampleContinue" class="secondary">Continue sample</button>
        <button id="sampleRepair" class="secondary">Repair sample</button>
        <button id="sampleJapanese" class="secondary">Japanese eval</button>
      </div>
      <div style="border-top:1px solid var(--line);padding-top:12px;display:grid;gap:10px">
        <label>Web knowledge intake URL
          <span class="hint">Fetched content is quarantined. It is never trained or promoted automatically.</span>
          <input id="intakeUrl" placeholder="https://example.org/article" autocomplete="off">
        </label>
        <div class="row">
          <input id="intakeLanguage" value="ja" aria-label="Language" style="width:90px">
          <input id="intakeLicense" placeholder="License (optional)" aria-label="License" style="flex:1;min-width:150px">
        </div>
        <label style="display:flex;grid-template-columns:auto 1fr;align-items:center;font-weight:400">
          <input id="intakeRights" type="checkbox" style="width:auto">
          I confirmed the source permits this use
        </label>
        <div class="row"><button id="intakeBtn" class="secondary">Fetch to quarantine</button></div>
        <div class="hint" id="intakeStatus">No source fetched.</div>
      </div>
    </section>
    <section class="panel output">
      <div class="summary" id="summary"></div>
      <div class="response"><div class="chips" id="chips"></div><div class="responseText" id="responseText">Run a request.</div></div>
      <div class="detail"><section><h2>Chunks</h2><div id="chunks"></div></section><section><h2>Raw JSON</h2><pre id="rawJson">{}</pre></section></div>
    </section>
  </main>
  <script>
    const modeEl = document.getElementById("mode");
    const textEl = document.getElementById("textInput");
    const profileEl = document.getElementById("profile");
    const historyEl = document.getElementById("historyInput");
    const runBtn = document.getElementById("runBtn");
    const summaryEl = document.getElementById("summary");
    const chipsEl = document.getElementById("chips");
    const responseEl = document.getElementById("responseText");
    const chunksEl = document.getElementById("chunks");
    const rawEl = document.getElementById("rawJson");
    const statusEl = document.getElementById("serverStatus");
    const unknownControlsEl = document.getElementById("unknownLanguageControls");
    const sessionIdEl = document.getElementById("sessionId");
    const teachingEl = document.getElementById("teachingInput");
    const intakeBtn = document.getElementById("intakeBtn");
    const intakeStatusEl = document.getElementById("intakeStatus");
    const structuredControlsEl = document.getElementById("structuredControls");
    const structuredDataEl = document.getElementById("structuredData");
    const structuredSchemaEl = document.getElementById("structuredSchema");
    const samples = {
      coding: "Write a Python function solve(numbers) that returns the sum of a list of numbers.",
      continue: "Continue this chunk seed composition approach without changing safety gates.",
      repair: "Make safety gates random when the seed says so.",
      japanese: "このシステムは何ができますか？"
    };
    function parseHistory() {
      const raw = historyEl.value.trim();
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) throw new Error("History JSON must be an array.");
      return parsed;
    }
    async function run() {
      runBtn.disabled = true; statusEl.textContent = "running";
      try {
        const payload = { mode: modeEl.value, text: textEl.value, history: parseHistory(), profile: profileEl.value };
        if (modeEl.value === "unknown_language") {
          payload.session_id = sessionIdEl.value.trim();
          payload.observation = textEl.value;
          payload.teaching = teachingEl.value.trim();
        }
        if (modeEl.value === "structured") {
          payload.data = JSON.parse(structuredDataEl.value);
          payload.schema = JSON.parse(structuredSchemaEl.value);
        }
        const response = await fetch("/api/respond", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload) });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || "Request failed.");
        render(data.result); statusEl.textContent = "ready";
      } catch (error) {
        responseEl.textContent = String(error.message || error); statusEl.textContent = "error";
      } finally {
        runBtn.disabled = false;
      }
    }
    async function runIntake() {
      intakeBtn.disabled = true; intakeStatusEl.textContent = "fetching and evaluating...";
      try {
        const payload = { url:document.getElementById("intakeUrl").value.trim(), language:document.getElementById("intakeLanguage").value.trim(), license:document.getElementById("intakeLicense").value.trim(), rights_confirmed:document.getElementById("intakeRights").checked };
        const response = await fetch("/api/knowledge/intake", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
        const data = await response.json(); if (!response.ok || !data.ok) throw new Error(data.error || "Intake failed");
        intakeStatusEl.textContent = `${data.record.status} | ${data.record.quality_result} | ${data.record.intake_id}${data.duplicate ? " | duplicate" : ""}`;
      } catch (error) { intakeStatusEl.textContent = `error: ${error.message || error}`; }
      finally { intakeBtn.disabled = false; }
    }
    function render(result) {
      rawEl.textContent = JSON.stringify(result, null, 2);
      responseEl.textContent = result.broken_response || result.response || "";
      const topic = result.topic_relation ? result.topic_relation.status : (result.topic_status || "");
      const verification = result.verification ? (result.verification.ok ? "tests ok" : "tests fail") : "";
      const coherence = result.coherence ? result.coherence.ok : result.ok;
      const confidence = result.confidence && typeof result.confidence === "object" ? Object.values(result.confidence).filter(x => typeof x === "number")[0] : result.confidence;
      const metrics = [["route", result.route || ""], ["act", result.dialogue_act || result.acquisition_state || "-"], ["topic", topic || result.language_status || "-"], ["coherence", confidence != null ? Number(confidence).toFixed(2) : (coherence ? "ok" : "fail")], ["session", result.session_id || String(result.history_turn_count ?? 0)]];
      summaryEl.innerHTML = metrics.map(([k,v]) => `<div class="metric"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join("");
      const blocked = result.blocked_claims || [];
      chipsEl.innerHTML = [chip(result.ok ? "ok" : "not ok", result.ok ? "good" : "bad"), result.claim ? chip(result.claim, "warn") : "", ...blocked.slice(0,4).map(x => chip(x, ""))].join("");
      const hypotheses = (result.hypotheses || []).map((item, index) => ({
        chunk_id: item.hypothesis_id || `hyp-${index + 1}`,
        semantic_role: item.status || item.kind || "provisional",
        seed: item.confidence ?? item.score ?? "",
        text: item.text || item.form || item.meaning || JSON.stringify(item)
      }));
      const groups = [["Hypotheses", hypotheses], ["History", result.history_chunks || []], ["Current", result.current_chunks || result.input_chunks || []], ["Output", result.output_chunks || []]];
      chunksEl.innerHTML = groups.map(([name, chunks]) => chunks.length ? `<h2>${esc(name)}</h2>` + chunks.map(renderChunk).join("") : "").join("");
    }
    function renderChunk(chunk) {
      const role = chunk.role || chunk.semantic_role || chunk.policy_decision || "";
      return `<div class="chunk"><div class="chunkHead"><span>${esc(chunk.chunk_id || "")} ${esc(role)}</span><span>${esc(chunk.seed ?? "")}</span></div><div class="chunkBody">${esc(chunk.text || "")}</div></div>`;
    }
    function chip(text, cls) { return `<span class="chip ${cls}">${esc(text)}</span>`; }
    function esc(value) { return String(value).replace(/[&<>"']/g, ch => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[ch])); }
    runBtn.addEventListener("click", run);
    intakeBtn.addEventListener("click", runIntake);
    function updateModeControls() {
      unknownControlsEl.hidden = modeEl.value !== "unknown_language";
      structuredControlsEl.hidden = modeEl.value !== "structured";
    }
    modeEl.addEventListener("change", updateModeControls);
    document.getElementById("sampleCoding").addEventListener("click", () => { modeEl.value = "coding"; textEl.value = samples.coding; run(); });
    document.getElementById("sampleContinue").addEventListener("click", () => { modeEl.value = "topic"; textEl.value = samples.continue; run(); });
    document.getElementById("sampleRepair").addEventListener("click", () => { modeEl.value = "topic"; textEl.value = samples.repair; run(); });
    document.getElementById("sampleJapanese").addEventListener("click", () => { modeEl.value = "japanese"; textEl.value = samples.japanese; run(); });
    textEl.addEventListener("keydown", event => { if (event.ctrlKey && event.key === "Enter") run(); });
    updateModeControls(); run();
  </script>
</body>
</html>
"""


class LceWebHandler(BaseHTTPRequestHandler):
    server_version = "LCEDialogueLab/0.2"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_text(APP_HTML, "text/html; charset=utf-8")
            return
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "service": "lce-dialogue-lab"})
            return
        if parsed.path == "/api/knowledge/intakes":
            self._send_json({"ok": True, "items": list_intakes()})
            return
        if parsed.path == "/api/knowledge/general":
            from urllib.parse import parse_qs
            query=parse_qs(parsed.query).get("q",[""])[0]
            self._send_json({"ok":True,"items":query_general_knowledge(query)})
            return
        if parsed.path == "/api/knowledge/coding":
            from urllib.parse import parse_qs
            query=parse_qs(parsed.query).get("q",[""])[0]
            self._send_json({"ok":True,"items":query_coding_knowledge(query)})
            return
        if parsed.path == "/api/knowledge/wikipedia":
            from urllib.parse import parse_qs
            query=parse_qs(parsed.query).get("q",[""])[0]
            self._send_json({"ok":True,"items":wikipedia_public_metadata(query_wikipedia_general_education(query))})
            return
        self._send_json({"ok": False, "error": "not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/knowledge/intake":
            try:
                payload = self._read_json()
                url = str(payload.get("url", "")).strip()
                if not url:
                    raise ValueError("url is required")
                result = intake_url(
                    url,
                    language=str(payload.get("language", "")).strip() or None,
                    license=str(payload.get("license", "")).strip() or None,
                    rights_confirmed=payload.get("rights_confirmed") is True,
                    title=str(payload.get("title", "")).strip() or None,
                )
                self._send_json(result, status=201 if not result.get("duplicate") else 200)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path != "/api/respond":
            self._send_json({"ok": False, "error": "not found"}, status=404)
            return
        try:
            payload = self._read_json()
            self._send_json({"ok": True, "result": dispatch_response(payload)})
        except Exception as exc:  # pragma: no cover
            self._send_json({"ok": False, "error": str(exc)}, status=400)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("payload must be an object")
        return data

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, content_type: str, status: int = 200) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def dispatch_response(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode", "topic"))
    text = str(payload.get("text", ""))
    history = payload.get("history", [])
    if not isinstance(history, list):
        raise ValueError("history must be a list")
    routing = None
    if mode == "auto":
        routing = select_mode(payload)
        mode = routing["mode"]
    if mode == "seeded":
        result = respond_from_seed(text)
    elif mode == "japanese":
        result = respond_japanese(text, history)
    elif mode == "dialogue_state":
        result = respond_with_dialogue_state(text, history)
    elif mode == "dialogue_completion":
        result = respond_with_completion(text, history)
    elif mode == "hypothesis_loop":
        result = run_hypothesis_loop(text, history, data=payload.get("data"), schema=payload.get("schema"))
    elif mode == "layered_reasoning":
        issues=payload.get("issues")
        if issues is not None and not isinstance(issues,list): raise ValueError("issues must be an array")
        result = run_layered_reasoning(text,history,issues=issues,parallel=payload.get("parallel") is True)
    elif mode == "daily_dialogue":
        result = respond_daily_dialogue(text,history,style=str(payload.get("style", "concise")),output_contract=payload.get("output_contract"))
    elif mode == "interpretation":
        result = run_interpretation_slice(text,history)
    elif mode == "structured":
        result = run_structured_io(instruction=text, data=payload.get("data"), schema=payload.get("schema"))
    elif mode == "coding":
        result = run_coding_task(text, history)
    else:
        # Preserve legacy experimental modes, but keep auto routing bounded above.
        return _dispatch_legacy(mode, payload, text, history, routing)
    if routing is not None:
        result = {**result, "routing": routing, "selected_mode": mode}
    return result


def _dispatch_legacy(mode: str, payload: dict[str, Any], text: str, history: list[Any], routing: dict[str, Any] | None) -> dict[str, Any]:
    if mode == "seeded":
        return respond_from_seed(text)
    if mode == "japanese":
        return respond_japanese(text, history)
    if mode == "dialogue_state":
        return respond_with_dialogue_state(text, history)
    if mode == "dialogue_completion":
        return respond_with_completion(text, history)
    if mode == "hypothesis_loop":
        return run_hypothesis_loop(text, history, data=payload.get("data"), schema=payload.get("schema"))
    if mode == "layered_reasoning":
        issues=payload.get("issues")
        if issues is not None and not isinstance(issues,list):
            raise ValueError("issues must be an array")
        return run_layered_reasoning(text,history,issues=issues,parallel=payload.get("parallel") is True)
    if mode == "daily_dialogue":
        return respond_daily_dialogue(text,history,style=str(payload.get("style", "concise")),output_contract=payload.get("output_contract"))
    if mode == "structured":
        return run_structured_io(instruction=text, data=payload.get("data"), schema=payload.get("schema"))
    if mode == "chunked":
        return respond_from_chunk_seeds(text)
    if mode == "history":
        return respond_with_history_chunks(text, history)
    if mode == "graph":
        return respond_with_graph_dialogue(text, history)
    if mode == "reasoning":
        return run_graph_reasoning(text, history)
    if mode == "renderer":
        return render_verified_response(text, history, profile=str(payload.get("profile", "default")))
    if mode == "neural":
        return generate_neural_candidates(text, backend="heuristic")
    if mode == "topic":
        return respond_with_topic_continuity(text, history)
    if mode == "coding":
        return run_coding_task(text, history)
    if mode == "unknown_language":
        session_id = str(payload.get("session_id", "")).strip()
        if not session_id:
            raise ValueError("session_id is required for unknown_language mode")
        teaching = payload.get("teaching", "")
        if not isinstance(teaching, (str, dict, list)):
            raise ValueError("teaching must be text, an object, or an array")
        return run_unknown_language_session(
            session_id=session_id,
            observation=str(payload.get("observation", text)),
            teaching=teaching,
            history=history,
        )
    raise ValueError(f"unknown mode: {mode}")


_UNKNOWN_LANGUAGE_SESSIONS: dict[str, Any] = {}
_UNKNOWN_LANGUAGE_LOCK = threading.RLock()
_UNKNOWN_LANGUAGE_STORE = create_overlay_repository()


def run_unknown_language_session(*, session_id: str, observation: str, teaching: Any, history: list[Any]) -> dict[str, Any]:
    """Bridge the stable Web API to the independently owned runtime module."""
    candidates = (
        ("lce_validation.empirical.unknown_language_runtime", "process_unknown_language"),
        ("lce_validation.empirical.unknown_language", "process_unknown_language"),
        ("lce_validation.empirical.session_language_overlay", "process_unknown_language"),
    )
    for module_name, function_name in candidates:
        try:
            function = getattr(importlib.import_module(module_name), function_name)
        except (ImportError, AttributeError):
            continue
        result = function(
            session_id=session_id,
            observation=observation,
            teaching=teaching,
            history=history,
        )
        if not isinstance(result, dict):
            raise TypeError("unknown language runtime must return an object")
        return result

    try:
        module = importlib.import_module("lce_validation.empirical.unknown_language")
        session_type = getattr(module, "UnknownLanguageSession")
    except (ImportError, AttributeError) as exc:
        raise RuntimeError("unknown language runtime is not installed") from exc

    with _UNKNOWN_LANGUAGE_LOCK:
        try:
            overlay = _UNKNOWN_LANGUAGE_STORE.load(session_id)
        except OverlayNotFoundError:
            overlay = _UNKNOWN_LANGUAGE_STORE.create(session_id, session_id=session_id)
        if overlay["state"] == "retracted":
            raise ValueError("language session has been retracted")
        stored_snapshot = overlay.get("metadata", {}).get("runtime_snapshot")
        session = session_type.from_snapshot(stored_snapshot) if stored_snapshot else session_type(session_id)
        encounter = session.encounter(observation)
        lesson = _normalize_teaching(teaching, observation)
        lexical = None
        if lesson:
            lexical = session.teach(
                lesson["form"],
                lesson["meaning"],
                example=str(lesson.get("example", observation)),
                confirmed=bool(lesson.get("confirmed", False)),
            )
        requested = lesson.get("requested_meanings", []) if lesson else []
        if isinstance(requested, str):
            requested = [requested]
        broken = session.broken_language(requested) if requested else None
        snapshot = session.snapshot()
        def persist(candidate: dict[str, Any]) -> None:
            candidate.setdefault("metadata", {})["runtime_snapshot"] = snapshot
            candidate["source_language"] = encounter["language_hypotheses"][0]["language"]
            candidate["evidence"].append({
                "evidence_id": encounter["encounter_id"],
                "kind": "grounded_teaching" if lesson else "observation",
                "observed_at": utc_now(),
                "source": {"surface": "web_ui", "session_id": session_id},
                "content": {"observation": observation, "teaching": lesson},
            })
        overlay = _UNKNOWN_LANGUAGE_STORE.update(session_id, persist, expected_version=overlay["version"])

    hypotheses = list(encounter["language_hypotheses"])
    for form, rows in snapshot["lexicon"].items():
        hypotheses.extend({"kind": "lexical", "form": form, **row} for row in rows)
    if broken and broken["text"]:
        response = broken["text"]
    elif lexical is not None and not lexical.confirmed:
        response = session.confirmation_prompt(lexical.form, lexical.meaning)
    else:
        response = "Observation stored. More grounded teaching evidence is required."
    confidence = {
        "language": max((item["score"] for item in encounter["language_hypotheses"]), default=0.0),
        "meaning": lexical.confidence if lexical is not None else 0.0,
        "grammar": 0.0,
    }
    return {
        "ok": True,
        "route": "unknown_language_session",
        "session_id": session_id,
        "acquisition_state": "PROVISIONAL_USE" if lexical is not None else "SEGMENTATION_OPEN",
        "language_status": encounter["language_hypotheses"][0]["language"],
        "encounter": encounter,
        "hypotheses": hypotheses,
        "confidence": confidence,
        "broken_response": response,
        "broken_language": broken,
        "scope": snapshot["scope"],
        "formal_knowledge": snapshot["formal_knowledge"],
        "overlay_version": overlay["version"],
        "history_turn_count": len(history),
    }


def _normalize_teaching(teaching: Any, observation: str) -> dict[str, Any] | None:
    if isinstance(teaching, dict):
        if not teaching:
            return None
        if not str(teaching.get("form", "")).strip() or not str(teaching.get("meaning", "")).strip():
            raise ValueError("teaching object requires form and meaning")
        return dict(teaching)
    if isinstance(teaching, list):
        if not teaching:
            return None
        if len(teaching) != 1 or not isinstance(teaching[0], dict):
            raise ValueError("teaching array currently accepts one teaching object")
        return _normalize_teaching(teaching[0], observation)
    raw = teaching.strip()
    if not raw:
        return None
    if raw.startswith("{"):
        parsed = json.loads(raw)
        return _normalize_teaching(parsed, observation)
    match = re.match(r'^\s*(.+?)\s*(?:=|\bmeans\b)\s*(.+?)\s*\.?\s*$', raw, re.IGNORECASE)
    if not match:
        raise ValueError('plain teaching must use "form = meaning" or a JSON object')
    return {"form": match.group(1), "meaning": match.group(2), "example": observation, "confirmed": False}


def run_server(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), LceWebHandler)
    print(f"LCE Dialogue Lab running at http://{host}:{port}/", flush=True)
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8789)
    args = parser.parse_args(argv)
    run_server(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
