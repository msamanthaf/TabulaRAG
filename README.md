<div align="center">
  <img src="frontend/src/images/logo.png" alt="TabulaRAG logo" width="64" height="64" />
  <h1>TabulaRAG</h1>
  A fast-ingesting tabular data MCP RAG tool backed with cell citations.
</div>

## UI Preview
<table>
  <tr>
    <td><img src="frontend/src/images/preview1.png" alt="TabulaRAG preview 1" /></td>
    <td><img src="frontend/src/images/preview2.png" alt="TabulaRAG preview 2" /></td>
  </tr>
  <tr>
    <td><img src="frontend/src/images/preview3.png" alt="TabulaRAG preview 3" /></td>
    <td><img src="frontend/src/images/preview4.png" alt="TabulaRAG preview 4" /></td>
  </tr>
</table>

## Tech Stack

- Backend: Python 3.11, FastAPI, Uvicorn, SQLAlchemy, PostgreSQL, Qdrant, MCP, OpenAPI
- Frontend: TypeScript, React, Vite

## Prerequisites

- Docker Engine / Docker Desktop
- Docker Compose (v2)
- Optional for local dev: Python 3.11+, Node.js 18+

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

## High-level Architecture


```mermaid
flowchart TD
  U([User]) --> IN[/"Upload CSV or Ask Question"/]
  IN --> C{Client Type}
  C -->|Web App| FE["React + Vite Frontend"]
  C -->|Tool Caller| OW[Open WebUI / MCP Caller]

  FE --> API["FastAPI + Uvicorn Backend"]
  OW --> API

  API --> MCP[MCP Server Endpoint]
  API --> OAPI[/"OpenAPI Schema + REST Endpoints"/]
  API --> FS[/"Uploads directory: data/uploads"/]

  API --> ING["Parse + Normalize + Store Data Rows"]
  ING --> DB[(PostgreSQL)]
  ING --> EMB[FastEmbed]
  EMB --> VDB[(Qdrant Vector DB)]

  API --> RET[Retrieve Matching Rows]
  DB --> RET
  VDB --> RET

  RET --> ANS["Answer with Citations + Highlight URL"]
  ANS --> OUT[/"Response to Frontend or Open WebUI"/]
  OUT --> END([End])

  classDef term fill:#FFF7D6,stroke:#B08900,color:#5C4500;
  classDef user fill:#F3E5F5,stroke:#6A1B9A,color:#3F0A5C;
  classDef api fill:#D6ECFF,stroke:#2F6DB5,color:#123255;
  classDef data fill:#E6F5E9,stroke:#2E7D32,color:#1B4D2B;
  classDef infra fill:#FFE6CC,stroke:#C97A3D,color:#3D2B1F;

  class U,IN,C,OW,END term;
  class FE,API,MCP,OAPI,RET,ANS api;
  class DB,VDB,FS,EMB data;
  class ING infra;

```
