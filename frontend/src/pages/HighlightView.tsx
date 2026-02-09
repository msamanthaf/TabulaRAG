import React, { useEffect, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { getHighlight, getSlice, listTables } from "../api";
import DataTable from "../components/DataTable";
import logo from "../images/logo.png";
import returnIcon from "../images/return.png";

export default function HighlightView() {
    const { highlightId } = useParams();
    const location = useLocation();
    const [hl, setHl] = useState<any | null>(null);
    const [slice, setSlice] = useState<any | null>(null);
    const [err, setErr] = useState<string | null>(null);
    const [queryText, setQueryText] = useState<string | null>(null);
    const [tableName, setTableName] = useState<string | null>(null);

    useEffect(() => {
        if (!highlightId) return;
        (async () => {
            const h = await getHighlight(highlightId);
            setHl(h);

            const citations = h.evidence || [];
            const first = citations[0];
            const rows = first?.range?.rows || h.rows || [0];
            const cols = first?.range?.cols || h.cols || [];

            const rowFrom = Math.max(0, Math.min(...rows) - 5);
            const rowTo = Math.max(...rows) + 6;

            const s = await getSlice(h.table_id, rowFrom, rowTo, cols.length ? cols : undefined);
            setSlice({ ...s, rowFrom, highlight: { rows, cols } });

            try {
                const tables = await listTables();
                const t = tables.find((row: any) => row.table_id === h.table_id);
                setTableName(t?.name || null);
            } catch {
                setTableName(null);
            }
        })().catch(e => setErr(String(e?.message || e)));
    }, [highlightId]);

    useEffect(() => {
        const q = new URLSearchParams(location.search).get("q");
        setQueryText(q);
    }, [location.search]);

    useEffect(() => {
        if (!slice?.highlight?.rows?.length) return;
        const target = Math.min(...slice.highlight.rows);
        const el = document.querySelector(`[data-row-index="${target}"]`) as HTMLElement | null;
        if (!el) return;
        // Let layout settle before scrolling
        setTimeout(() => {
            el.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 0);
    }, [slice]);

    if (!highlightId) return null;

    return (
        <div className="page-stack">
            <div className="highlight-header">
                <img src={logo} alt="TabulaRAG" className="hero-logo" />
                <div className="highlight-title">TabulaRAG</div>
            </div>
            <div className="top-info top-info-center">
                {hl?.table_id && <div className="small">Table: {tableName || "Table"}</div>}
                {queryText && <div className="small">Query: {queryText}</div>}
            </div>

            {err && <p className="error">{err}</p>}

            {slice && (
                <>
                    <div className="top-info top-info-row">
                        <div className="small">
                            Showing rows {slice.rowFrom}..{slice.rowFrom + slice.rows.length - 1}
                        </div>
                    </div>
                    <div className="table-area">
                        <DataTable
                            columns={slice.columns}
                            rows={slice.rows}
                            highlight={slice.highlight}
                            rowOffset={slice.rowFrom}
                        />
                    </div>
                    <div className="return-row">
                        <a className="return-link" href="/">
                            <img src={returnIcon} alt="" />
                            Return to Upload Page
                        </a>
                    </div>
                </>
            )}
        </div>
    );
}
