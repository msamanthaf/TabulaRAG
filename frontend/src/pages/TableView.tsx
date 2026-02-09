import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getSlice, listTables } from "../api";
import DataTable from "../components/DataTable";

export default function TableView() {
    const { tableId } = useParams();
    const [data, setData] = useState<any | null>(null);
    const [err, setErr] = useState<string | null>(null);
    const [tableName, setTableName] = useState<string | null>(null);

    useEffect(() => {
        if (!tableId) return;
        getSlice(tableId, 0, 100).then(setData).catch(e => setErr(String(e?.message || e)));
    }, [tableId]);

    useEffect(() => {
        if (!tableId) return;
        listTables()
            .then(tables => {
                const t = tables.find((row: any) => row.table_id === tableId);
                setTableName(t?.name || null);
            })
            .catch(() => setTableName(null));
    }, [tableId]);

    if (!tableId) return null;

    return (
        <div className="page-stack">
            <div className="card" style={{ marginBottom: 12 }}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                    <div>
                        <div className="mono">{tableName || "Table"}</div>
                        <div className="small">Showing first 100 rows.</div>
                    </div>
                </div>
            </div>

            {err && <p className="error">{err}</p>}
            {data && (
                <div className="table-area">
                    <DataTable columns={data.columns} rows={data.rows} />
                </div>
            )}
        </div>
    );
}
