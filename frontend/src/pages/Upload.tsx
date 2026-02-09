import React, { useEffect, useRef, useState } from "react";
import { uploadTable, listTables, getJob, getSlice, deleteTable, renameTable } from "../api";
import DataTable from "../components/DataTable";
import logo from "../images/logo.png";
import uploadLogo from "../images/upload.png";

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("Uploaded Table");
  const [tables, setTables] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [preview, setPreview] = useState<any | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [activeTableId, setActiveTableId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [showScrollHint, setShowScrollHint] = useState(false);
  const tablesScrollRef = useRef<HTMLDivElement | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  async function refresh() {
    const t = await listTables();
    setTables(t);
  }

  useEffect(() => { refresh().catch(console.error); }, []);

  useEffect(() => {
    const el = tablesScrollRef.current;
    if (!el) return;

    const updateHint = () => {
      const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 4;
      const canScroll = el.scrollHeight > el.clientHeight + 2;
      setShowScrollHint(canScroll && !atBottom);
    };

    updateHint();
    el.addEventListener("scroll", updateHint);
    window.addEventListener("resize", updateHint);
    return () => {
      el.removeEventListener("scroll", updateHint);
      window.removeEventListener("resize", updateHint);
    };
  }, [tables.length]);

  async function onUpload() {
    if (!file) return;
    setBusy(true);
    setErr(null);
    setStatus("Uploading...");
    try {
      const res = await uploadTable(file, name);
      const jobId = res.job_id;
      if (!jobId) throw new Error("Upload started, but no job id was returned.");

      // Poll job status until done/error
      // Small delay to avoid hammering the API
      while (true) {
        const job = await getJob(jobId);
        if (job.status === "done" || job.status === "indexing") {
          setStatus(null);
          await refresh();
          if (job.table_id) {
            await loadPreview(job.table_id);
          }
          setToast("File uploaded successfully");
          setTimeout(() => setToast(null), 2400);
          setFile(null);
          setName("Uploaded Table");
          break;
        }
        if (job.status === "error") {
          throw new Error(job.message || "Upload failed.");
        }
        const msg = job.message ? `${job.message} ` : "";
        setStatus(`${msg}${job.status} (${job.progress ?? 0}%)`);
        await new Promise(r => setTimeout(r, 500));
      }
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function loadPreview(tableId: string) {
    setActiveTableId(tableId);
    setPreviewBusy(true);
    setPreviewErr(null);
    try {
      const slice = await getSlice(tableId, 0, 50);
      setPreview(slice);
    } catch (e: any) {
      setPreviewErr(String(e?.message || e));
      setPreview(null);
    } finally {
      setPreviewBusy(false);
    }
  }

  async function onDelete(tableId: string) {
    try {
      await deleteTable(tableId);
      if (activeTableId === tableId) {
        setActiveTableId(null);
        setPreview(null);
      }
      await refresh();
    } catch (e: any) {
      setErr(String(e?.message || e));
    }
  }

  async function onRename(tableId: string) {
    const next = editingName.trim();
    if (!next) {
      setErr("Name cannot be empty.");
      return;
    }
    try {
      await renameTable(tableId, next);
      setEditingId(null);
      setEditingName("");
      await refresh();
    } catch (e: any) {
      setErr(String(e?.message || e));
    }
  }

  function onSelectFile(nextFile: File | null) {
    setFile(nextFile);
    if (nextFile) {
      setName(nextFile.name);
    }
  }

  return (
    <div className="page page-stack">
      {toast && <div className="toast success">{toast}</div>}
      <div className="hero">
        <div className="hero-title-row">
          <img src={logo} alt="TabulaRAG" className="hero-logo" />
          <div className="hero-title">TabulaRAG</div>
        </div>
        <div className="hero-subtitle">Upload, Preview, and Query Table with Citation.</div>
      </div>

      <div className="panel upload-panel">
        {!file ? (
          <label className="upload-drop">
            <input
              type="file"
              accept=".csv,.tsv"
              onChange={(e) => onSelectFile(e.target.files?.[0] || null)}
            />
            <div className="upload-icon" aria-hidden="true">
              <img src={uploadLogo} alt="" />
            </div>
            <div className="upload-title">Upload CSV/TSV file</div>
            <div className="upload-subtitle">Click to select a file</div>
          </label>
        ) : (
          <>
            <h2>Upload CSV/TSV</h2>
            <div className="row">
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.tsv"
                onChange={(e) => onSelectFile(e.target.files?.[0] || null)}
                className="file-input-hidden"
              />
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                style={{ minWidth: 240 }}
              />
              <button onClick={() => fileInputRef.current?.click()} type="button" className="glass">
                Change file
              </button>
              <button onClick={onUpload} disabled={!file || busy} className="primary">
                {busy ? "Uploading..." : "Upload"}
              </button>
            </div>
            <div className="small">Selected: {file.name}</div>
          </>
        )}
        {err && <p className="error">{err}</p>}
        {status && !err && (
          <p
            className={[
              "small",
              status.toLowerCase().includes("done") || status.toLowerCase().includes("indexing")
                ? "status-success"
                : "status-info",
            ].join(" ")}
          >
            {status}
          </p>
        )}
      </div>

      <div className="panel">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h3 style={{ marginBottom: 0 }}>Uploaded tables</h3>
          <span className="small">Tap a table to preview</span>
        </div>
        <div className="tables-scroll" ref={tablesScrollRef}>
          <ul>
            {tables.map(t => (
              <li key={t.table_id}>
                <div className="list-row">
                  <div className="list-item">
                    {editingId === t.table_id ? (
                      <input
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") onRename(t.table_id);
                        }}
                        className="rename-input"
                      />
                    ) : (
                      <button
                        type="button"
                        className="list-button"
                        onClick={() => loadPreview(t.table_id)}
                      >
                        <span className="mono">{t.name}</span>{" "}
                        <span className="small">({t.row_count} rows, {t.col_count} cols)</span>
                      </button>
                    )}
                  </div>
                  <button
                    type="button"
                    className={`icon-button ${editingId === t.table_id ? "success" : "edit"}`}
                    onClick={() => {
                      if (editingId === t.table_id) {
                        onRename(t.table_id);
                      } else {
                        setEditingId(t.table_id);
                        setEditingName(t.name);
                      }
                    }}
                    aria-label={editingId === t.table_id ? "Save name" : `Rename ${t.name}`}
                    title={editingId === t.table_id ? "Save" : "Rename"}
                  >
                    {editingId === t.table_id ? (
                      <svg viewBox="0 0 24 24" role="presentation">
                        <path d="M9.2 16.6 4.8 12.2a1 1 0 1 1 1.4-1.4l3 3 8-8a1 1 0 0 1 1.4 1.4l-8.8 8.8a1 1 0 0 1-1.4 0z" />
                      </svg>
                    ) : (
                      <svg viewBox="0 0 24 24" role="presentation">
                        <path d="M15.2 4.2a2 2 0 0 1 2.8 0l1.8 1.8a2 2 0 0 1 0 2.8l-9.8 9.8a1 1 0 0 1-.5.27l-4.5 1a1 1 0 0 1-1.2-1.2l1-4.5a1 1 0 0 1 .27-.5l9.8-9.8zM6.7 15.3l-.6 2.5 2.5-.6 8.6-8.6-1.9-1.9-8.6 8.6z" />
                      </svg>
                    )}
                  </button>
                  <button
                    type="button"
                    className="icon-button danger"
                    onClick={() => onDelete(t.table_id)}
                    aria-label={`Delete ${t.name}`}
                    title="Delete table"
                  >
                    <svg viewBox="0 0 24 24" role="presentation">
                      <path d="M9 3a1 1 0 0 0-1 1v1H5a1 1 0 0 0 0 2h1v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7h1a1 1 0 1 0 0-2h-3V4a1 1 0 0 0-1-1H9zm1 2h4v0H10zm-1 4a1 1 0 0 1 2 0v8a1 1 0 1 1-2 0V9zm6-1a1 1 0 0 1 1 1v8a1 1 0 1 1-2 0V9a1 1 0 0 1 1-1z" />
                    </svg>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
        {showScrollHint && <div className="scroll-indicator" aria-hidden="true">▼</div>}
        <p className="small">
          Tip: Once Open WebUI calls <span className="mono">/query</span>, it returns a <span className="mono">highlight_url</span> you can open here.
        </p>
      </div>

      <div className="panel upload-preview">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h3 style={{ marginBottom: 0 }}>Table preview</h3>
          {activeTableId && (
            <span className="small mono">
              {tables.find(t => t.table_id === activeTableId)?.name || "Table"}
            </span>
          )}
        </div>
        {previewBusy && <p className="small">Loading preview…</p>}
        {previewErr && <p className="error">{previewErr}</p>}
        {preview && (
          <div className="table-area">
            <DataTable columns={preview.columns} rows={preview.rows} />
          </div>
        )}
        {!previewBusy && !preview && !previewErr && (
          <p className="small">Select a table above to preview the first 50 rows.</p>
        )}
      </div>
    </div>
  );
}
