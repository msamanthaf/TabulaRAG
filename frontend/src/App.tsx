import React, { useEffect, useState } from "react";
import { Routes, Route } from "react-router-dom";
import Upload from "./pages/Upload";
import TableView from "./pages/TableView";
import HighlightView from "./pages/HighlightView";
import logo from "./images/logo.png";
import sunIcon from "./images/sun.png";
import moonIcon from "./images/moon.png";
import { getMcpStatus } from "./api";

export default function App() {
    const [theme, setTheme] = useState<"dark" | "light">("light");
    const [mcpStatus, setMcpStatus] = useState<"online" | "offline" | "unknown">("unknown");

    useEffect(() => {
        const stored = window.localStorage.getItem("theme");
        if (stored === "light" || stored === "dark") {
            setTheme(stored);
        }
    }, []);

    useEffect(() => {
        document.documentElement.setAttribute("data-theme", theme);
        window.localStorage.setItem("theme", theme);
    }, [theme]);

    useEffect(() => {
        let mounted = true;

        async function checkStatus() {
            try {
                const res = await getMcpStatus();
                if (mounted) setMcpStatus(res.status ?? "unknown");
            } catch {
                if (mounted) setMcpStatus("offline");
            }
        }

        checkStatus();
        const id = window.setInterval(checkStatus, 5000);
        return () => {
            mounted = false;
            window.clearInterval(id);
        };
    }, []);

    return (
        <div className="app-shell">
            <div className={`mcp-status ${mcpStatus}`}>
                <span className="status-dot" />
                <span>MCP Server: {mcpStatus === "online" ? "Online" : mcpStatus === "offline" ? "Offline" : "Unknown"}</span>
            </div>
            <div className="theme-toggle-wrap">
                <button
                    className="theme-toggle"
                    onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                    aria-label="Toggle theme"
                    aria-pressed={theme === "light"}
                    type="button"
                >
                    <span className="toggle-track">
                        <span className="toggle-thumb">
                            <img src={theme === "dark" ? moonIcon : sunIcon} alt="" />
                        </span>
                    </span>
                </button>
                <div className="toggle-label">{theme === "dark" ? "Dark mode" : "Light mode"}</div>
            </div>

            <div className="content">
                <Routes>
                    <Route path="/" element={<Upload />} />
                    <Route path="/tables/:tableId" element={<TableView />} />
                    <Route path="/highlight/:highlightId" element={<HighlightView />} />
                </Routes>
            </div>
        </div>
    );
}
