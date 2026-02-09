import React from "react";

type Props = {
    columns: string[];
    rows: Record<string, any>[];
    highlight?: { rows: number[]; cols: string[] };
    rowOffset?: number; // if rows are a slice starting at row_from
};

export default function DataTable({ columns, rows, highlight, rowOffset = 0 }: Props) {
    const hlRows = new Set((highlight?.rows || []).map(r => r - rowOffset));
    const hlCols = new Set(highlight?.cols || []);

    return (
        <div className="card table-card">
            <div className="table-scroll">
                <table>
                    <thead>
                        <tr>
                            <th className="mono">#</th>
                            {columns.map(c => <th key={c}>{c}</th>)}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((r, i) => {
                            const isRowHL = hlRows.has(i);
                            const rowIndex = i + rowOffset;
                            return (
                                <tr key={i} data-row-index={rowIndex}>
                                    <td className={"mono " + (isRowHL ? "hl" : "")}>{i + rowOffset}</td>
                                    {columns.map(c => {
                                        const isCellHL = isRowHL && hlCols.has(c);
                                        return (
                                            <td key={c} className={isCellHL ? "hl" : ""}>
                                                {r[c] ?? ""}
                                            </td>
                                        );
                                    })}
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
