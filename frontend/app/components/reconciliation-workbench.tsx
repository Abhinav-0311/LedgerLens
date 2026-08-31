"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";

type Decision = { source_id: string; target_id: string | null; relationship: string; status: "matched" | "unmatched" | "ambiguous"; confidence: number; rule_id: string | null; evidence: string[]; exception_category: string | null };
type Batch = { id: string; label: string; record_count: number; source_kind: string; imported_at?: string };
type Report = { batch_id: string; batch_label: string; records_processed: number; auto_match_rate: number; verified_matching_accuracy: number | null; ground_truth_available: boolean; unresolved_exceptions: number; throughput_records_per_second: number | null; processing_time_ms: number; exception_categories: Record<string, number>; low_confidence_cases: Decision[]; incorrect_match_examples: Decision[]; decisions: Decision[] };
type Analysis = { status: "available" | "unavailable"; advisory_id?: string; classification: string | null; explanation: string | null; recommendation: string | null; confidence: number | null; limitation: string };
type AuditEvent = { id: string; event_type: string; entity_id: string; created_at: string; payload: Record<string, unknown> };
const words = (value: string) => value.replaceAll("_", " ");

export function ReconciliationWorkbench() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [batches, setBatches] = useState<Batch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analysisState, setAnalysisState] = useState<"idle" | "loading" | "error">("idle");
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [resolutionMessage, setResolutionMessage] = useState<string | null>(null);
  const exceptions = useMemo(() => report?.decisions.filter((decision) => decision.status !== "matched") ?? [], [report]);
  const selected = exceptions.find((decision) => decision.source_id === selectedId) ?? exceptions[0] ?? null;

  async function loadBatches() {
    const response = await fetch("/api/batches");
    if (!response.ok) throw new Error("Synthetic batch list is unavailable.");
    const body = await response.json();
    setBatches(body.batches);
    setSelectedBatchId((current) => current || body.batches.find((batch: Batch) => batch.id === "00000000-0000-0000-0000-000000000004")?.id || body.batches[0]?.id || "");
  }
  useEffect(() => { void loadBatches().catch((cause) => setError(cause.message)); }, []);
  useEffect(() => { const saved = window.localStorage.getItem("ledgerlens-theme"); if (saved === "dark" || saved === "light") setTheme(saved); }, []);
  useEffect(() => { document.documentElement.dataset.theme = theme; window.localStorage.setItem("ledgerlens-theme", theme); }, [theme]);
  async function loadAudit(batchId: string) { const response = await fetch(`/api/audit-events?batch_id=${encodeURIComponent(batchId)}`); if (response.ok) setAuditEvents((await response.json()).events); }
  async function runBatch() {
    if (!selectedBatchId) return;
    setState("loading"); setError(null); setImportMessage(null);
    try {
      const response = await fetch("/api/reconciliation", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ batch_id: selectedBatchId }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "The reconciliation run could not complete.");
      setReport(body); setSelectedId(null); setAnalysis(null); setResolutionMessage(null); setState("success"); void loadAudit(body.batch_id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "The reconciliation run could not complete."); setState("error"); }
  }
  async function importFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; event.target.value = "";
    if (!file) return;
    if (!/\.(json|csv)$/i.test(file.name)) { setError("Choose a synthetic .json or .csv batch file."); return; }
    if (file.size > 1_000_000) { setError("Import exceeds the 1 MB synthetic-demo limit."); return; }
    setState("loading"); setError(null); setImportMessage(null);
    try {
      const content = await file.text();
      const response = await fetch("/api/batches", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ filename: file.name, content }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Import could not be processed.");
      await loadBatches(); setSelectedBatchId(body.id); setImportMessage(`${body.record_count} synthetic records imported. Select Run reconciliation to evaluate the batch.`); setState("idle");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Import could not be processed."); setState("error"); }
  }
  async function analyze() { if (!selected || !report) return; setAnalysisState("loading"); try { const response = await fetch("/api/exception-analysis", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ batch_id: report.batch_id, source_id: selected.source_id }) }); const body = await response.json(); if (!response.ok) throw new Error(); setAnalysis(body); setAnalysisState("idle"); } catch { setAnalysisState("error"); } }
  async function resolve(action: "approved" | "rejected") { if (!selected || !analysis?.advisory_id || !report) return; const response = await fetch("/api/resolutions", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ batch_id: report.batch_id, source_id: selected.source_id, advisory_id: analysis.advisory_id, action, actor_label: "Demo finance reviewer", rationale: action === "approved" ? "Evidence reviewed; proposed follow-up accepted." : "Evidence reviewed; proposed follow-up rejected." }) }); const body = await response.json(); setResolutionMessage(response.ok ? body.message : body.detail); void loadAudit(report.batch_id); }
  function reset() { setReport(null); setSelectedId(null); setAnalysis(null); setError(null); setState("idle"); }
  const metrics = [["Records processed", report ? String(report.records_processed) : "—"], ["Auto-match rate", report ? `${Math.round(report.auto_match_rate * 100)}%` : "—"], ["Verified accuracy", report ? (report.verified_matching_accuracy === null ? "Not supplied" : `${Math.round(report.verified_matching_accuracy * 100)}%`) : "—"], ["Unresolved", report ? String(report.unresolved_exceptions) : "—"], ["Throughput", report?.throughput_records_per_second ? `${report.throughput_records_per_second}/s` : "—"]];
  return <main className="workbench">
    <header className="topbar"><div className="brand"><img className="brand-logo" src="/ledgerlens-logo.png" alt="LedgerLens reconciliation lens"/>LedgerLens</div><div className="topbar-actions"><p className="source-label">Synthetic data only · no live Razorpay integration</p><button className="theme-toggle" onClick={() => setTheme(theme === "light" ? "dark" : "light")} aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`} aria-pressed={theme === "dark"}>{theme === "light" ? "◐ Dark" : "◑ Light"}</button></div></header>
    <section className="runbar" aria-labelledby="workspace-heading"><div><p className="eyebrow">Reconciliation workspace</p><h1 id="workspace-heading">Close the batch. Keep the uncertainty visible.</h1><p className="lede">Deterministic rules reconcile the evidence. Exceptions stay open until a human reviews them.</p></div><div className="run-controls"><label className="batch-picker">Batch<select aria-label="Select reconciliation batch" value={selectedBatchId} onChange={(event) => { setSelectedBatchId(event.target.value); reset(); }}>{batches.map((batch) => <option value={batch.id} key={batch.id}>{batch.label} · {batch.record_count} records</option>)}</select></label><label className="import-action">Import synthetic file<input aria-label="Import synthetic JSON or CSV batch" type="file" accept=".json,.csv,application/json,text/csv" onChange={importFile}/><span>Import file</span></label><button className="primary-action" onClick={runBatch} disabled={state === "loading" || !selectedBatchId}>{state === "loading" ? "Working…" : "Run reconciliation"}</button>{report && <button className="quiet-action" onClick={reset}>Reset view</button>}</div></section>
    {error && <section className="error-banner" role="alert"><strong>Action unavailable.</strong> {error} <button onClick={() => setError(null)}>Dismiss</button></section>}{importMessage && <p className="import-message">{importMessage}</p>}
    <section className="metric-grid" aria-label="Batch metrics">{metrics.map(([label, value]) => <article className="metric" key={label}><span>{label}</span><strong>{value}</strong></article>)}<article className="metric metric-note"><span>Processing time</span><strong>{report ? `${report.processing_time_ms} ms` : "Awaiting run"}</strong></article></section>
    <section className="review-layout" aria-label="Exception review"><section className="exception-panel" aria-labelledby="exceptions-heading"><div className="panel-heading"><div><p className="eyebrow">Review queue</p><h2 id="exceptions-heading">Exceptions requiring attention</h2></div><span className="count-badge">{report ? exceptions.length : "—"}</span></div>{!report && <div className="empty-state"><strong>No batch has been run.</strong><p>Run the demo or import a synthetic JSON/CSV batch to see unresolved cases.</p></div>}{exceptions.map((decision) => <button className={`exception-row ${selected?.source_id === decision.source_id ? "is-selected" : ""}`} key={decision.source_id} onClick={() => { setSelectedId(decision.source_id); setAnalysis(null); setResolutionMessage(null); }} aria-pressed={selected?.source_id === decision.source_id}><span className={`status-dot ${decision.status}`} aria-hidden="true"/><span className="exception-main"><strong>{decision.source_id}</strong><small>{words(decision.exception_category ?? decision.status)}</small></span><span className="row-status">{decision.status}</span></button>)}</section>
    <aside className="evidence-panel" aria-labelledby="evidence-heading"><p className="eyebrow">Inspectable evidence</p><h2 id="evidence-heading">{selected ? selected.source_id : "Select an exception"}</h2>{selected ? <><dl className="record-facts"><div><dt>Outcome</dt><dd>{selected.status}</dd></div><div><dt>Relationship</dt><dd>{words(selected.relationship)}</dd></div><div><dt>Confidence</dt><dd>{Math.round(selected.confidence * 100)}%</dd></div><div><dt>Candidate</dt><dd>{selected.target_id ?? "No safe candidate"}</dd></div></dl><h3>Why it stopped</h3><ul className="evidence-list">{selected.evidence.map((item) => <li key={item}>{item}</li>)}</ul><button className="analysis-action" onClick={analyze} disabled={analysisState === "loading"}>{analysisState === "loading" ? "Analyzing evidence…" : "Analyze exception"}</button>{analysis?.status === "available" && <section className="analysis-result"><p className="eyebrow">AI advisory</p><strong>{analysis.classification}</strong><p>{analysis.explanation}</p><dl className="analysis-facts"><div><dt>Recommended review</dt><dd>{words(analysis.recommendation ?? "manual_investigation")}</dd></div><div><dt>AI confidence</dt><dd>{Math.round((analysis.confidence ?? 0) * 100)}%</dd></div></dl><div className="resolution-actions"><button className="approve-action" onClick={() => resolve("approved")}>Approve follow-up</button><button className="quiet-action" onClick={() => resolve("rejected")}>Reject</button></div></section>}{analysis?.status === "unavailable" && <p className="analysis-unavailable">{analysis.limitation} The exception remains unresolved.</p>}{resolutionMessage && <p className="resolution-message">{resolutionMessage}</p>}<p className="review-boundary">AI is advisory only. Approval requires a server-recorded advisory for this exact exception and cannot alter source financial records.</p></> : <p className="empty-copy">Evidence will appear after a batch is run.</p>}</aside></section>
    <section className="category-strip" aria-label="Exception categories"><p className="eyebrow">Exception mix</p>{report ? Object.entries(report.exception_categories).map(([category, count]) => <div className="category" key={category}><span>{words(category)}</span><strong>{count}</strong></div>) : <p className="empty-copy">Categories will be calculated from the completed run.</p>}</section>
    <section className="evaluation-panel" aria-labelledby="evaluation-heading"><div><p className="eyebrow">Evaluation evidence</p><h2 id="evaluation-heading">What the batch did not resolve</h2><p>{report?.ground_truth_available ? "Accuracy is measured only against server-side synthetic ground truth." : "No ground truth was supplied for this imported batch, so accuracy is deliberately not reported."}</p></div><div><strong>{report?.low_confidence_cases.length ?? "—"}</strong><span>low-confidence auto-matches</span>{report?.low_confidence_cases.slice(0, 3).map((item) => <small key={item.source_id}>{item.source_id} · {Math.round(item.confidence * 100)}%</small>)}</div><div><strong>{report?.incorrect_match_examples.length ?? "—"}</strong><span>incorrect auto-matches</span>{report?.incorrect_match_examples.length === 0 && report ? <small>No incorrect auto-matches found.</small> : report?.incorrect_match_examples.map((item) => <small key={item.source_id}>{item.source_id} → {item.target_id}</small>)}</div></section>
    <section className="audit-panel"><div><p className="eyebrow">Append-only audit trail</p><h2>Latest workflow events</h2></div>{auditEvents.length ? auditEvents.slice(0, 6).map((event) => <article key={event.id}><strong>{words(event.event_type)}</strong><span>{event.entity_id}</span><time>{new Date(event.created_at).toLocaleTimeString()}</time></article>) : <p className="empty-copy">Run a batch to create auditable workflow events.</p>}</section>
  </main>;
}
