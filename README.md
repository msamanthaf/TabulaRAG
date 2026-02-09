# TabulaRAG

![TabulaRAG logo](frontend/src/images/logo.png)

TabulaRAG is a tabular data RAG tool that handles large CSV and TSVs quickly, indexes them for retrieval, and returns answers with cell-level citations. It includes a web UI for upload and table/row highlighting, plus a backend service for ingestion and retrieval.

## Getting started

1. Build and start all services:

```bash
docker compose up --build
```

2. Open the app in your browser:
Frontend: `http://localhost:5173`
Backend API: `http://localhost:8000`

3. Stop everything:

```bash
docker compose down
```

## Integrations

### MCP (Model Context Protocol)

1. Start the stack (see Getting started).

2. Confirm the MCP server is online:
`http://localhost:8000/mcp-status` should return `{"status":"online"}`.

3. In your MCP client, add a server using Streamable HTTP transport:
URL: `http://localhost:8000/mcp`

4. Verify the tools are available:
`ping`, `list_tables`, `get_table_slice`.

### OpenAPI tool (Open WebUI integration)

1. Start the stack (see Getting started).

2. Open the interactive docs or download the schema:
Docs: `http://localhost:8000/docs`
Schema: `http://localhost:8000/openapi.json`

3. Import the OpenAPI schema into your tool system and set the base URL:
`http://localhost:8000`

4. Recommended endpoints:
`POST /upload`, `GET /tables`, `POST /query`, `GET /highlights/{highlight_id}`.

## Architecture

```mermaid
graph TD
  A[Large CSV Data Upload] --> B[Parse Rows]
  B --> C[Normalize Cells]
  C --> D[Row Text Build]
  D --> E[Bulk Store in DB]
  E --> F[Background Embedding + Vector Index]

  Q[User Question] --> W[Open WebUI]
  W --> M[MCP Tool Call]
  M --> R{Hybrid Retrieval}
  E -.-> R
  F -.-> R
  R --> G[Context-Grounded Answer Generation]
  G --> H{Judge Agent Verification}
  H -- Low Confidence --> R
  H -- High Confidence --> I[Final Answer with Citations]
  I --> J[DeepEval Quality Guardrails]
  I --> K[Highlight Creation + URL]
  K --> L[Frontend Highlight View]

  classDef ingest fill:#FFE6CC,stroke:#C97A3D,color:#3D2B1F;
  classDef retrieval fill:#D6ECFF,stroke:#2F6DB5,color:#123255;
  classDef answer fill:#E6F5E9,stroke:#2E7D32,color:#1B4D2B;
  classDef verify fill:#FDE2E2,stroke:#C0392B,color:#5A1C16;
  classDef ui fill:#F3E5F5,stroke:#6A1B9A,color:#3F0A5C;

  class A,B,C,D,E,F ingest;
  class Q,W,M,R retrieval;
  class G,I,J,K answer;
  class H verify;
  class L ui;

```
