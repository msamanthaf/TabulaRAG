const API_BASE = (import.meta as any).env.VITE_API_BASE || "http://localhost:8000";

export async function uploadTable(file: File, name: string) {
    const form = new FormData();
    form.append("file", file);

    const url = new URL(API_BASE + "/upload");
    url.searchParams.set("name", name);

    const res = await fetch(url.toString(), { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function listTables() {
    const res = await fetch(API_BASE + "/tables");
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function getSlice(tableId: string, rowFrom: number, rowTo: number, cols?: string[]) {
    const offset = Math.max(0, rowFrom);
    const limit = Math.max(1, rowTo - rowFrom);
    const url = new URL(`${API_BASE}/tables/${tableId}/slice`);
    url.searchParams.set("offset", String(offset));
    url.searchParams.set("limit", String(limit));
    if (cols && cols.length) url.searchParams.set("cols", cols.join(","));
    const res = await fetch(url.toString());
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    return {
        ...data,
        rows: (data.rows || []).map((r: any) => r.data ?? r),
        offset,
        limit,
    };
}

export async function getHighlight(highlightId: string) {
    const res = await fetch(`${API_BASE}/highlights/${highlightId}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function uploadCsv(file: File, tableName?: string) {
    const form = new FormData();
    form.append("file", file);

    const url = tableName
        ? `${API_BASE}/upload?name=${encodeURIComponent(tableName)}`
        : `${API_BASE}/upload`;

    const res = await fetch(url, { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{ job_id: string; message: string }>;
}

export async function getJob(jobId: string) {
    const res = await fetch(`${API_BASE}/jobs/${jobId}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{ status: string; progress: number; message?: string; table_id?: string }>;
}

export async function deleteTable(tableId: string) {
    const res = await fetch(`${API_BASE}/tables/${tableId}`, { method: "DELETE" });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function renameTable(tableId: string, name: string) {
    const res = await fetch(`${API_BASE}/tables/${tableId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function getMcpStatus() {
    const res = await fetch(`${API_BASE}/mcp-status`);
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{ status: "online" | "offline" | "unknown" }>;
}
