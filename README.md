# MAOS

MAOS is the **Multi-Agent Autonomous Runtime**.

Autonomous multi-agent runtime platform built with Python, FastAPI, React, and local LLM infrastructure. MAOS routes user requests through planner, role agents, tool execution, validation, memory, and observability layers while keeping execution local-first and inspectable.

The project is designed as a practical engineering portfolio for building production-style agent runtimes rather than a simple chatbot wrapper.

---

## 시스템 개요

MAOS analyzes a user request, classifies the required task, selects the appropriate agent, executes registered tools, validates the result, and returns a final response.

The runtime currently supports general chat, code analysis and modification, Git/GitHub workflows, Kubernetes and Docker operations, file inspection, system status checks, persistent memory, tracing, and guarded validation commands.

```text
User Request
   |
   v
Frontend Dashboard (React)
   |
   v
FastAPI Backend
   |
   v
Planner Agent
   |
   v
Role Agent Selection
(Chat / Coding / Git / GitHub / Kubernetes / Docker / File / System)
   |
   v
Tool Selection
   |
   v
Tool Execution
   |
   v
Validation Layer
   |
   v
Final Response
```

---

## 시스템 구성 요소

MAOS is composed of a local backend runtime, a React dashboard, registered tool adapters, and local model infrastructure.

### Tech Stack

| Area | Stack | Role |
| --- | --- | --- |
| Backend | Python, FastAPI, PydanticAI, SQLite | API server, agent runtime, memory, trace storage |
| Frontend | React, TypeScript, Vite | Chat dashboard, agent activity, tool visibility |
| Infrastructure | Docker, Kubernetes, Ollama Local LLM | Local runtime, container orchestration, model execution |
| Tooling | Git, GitHub API, kubectl, Docker CLI | External task execution through guarded tools |

---

## Agent Architecture

MAOS uses role-specific agents so each request can be handled by the smallest capable execution path.

Each agent has a focused responsibility and relies on the shared Tool Registry, validation layer, memory store, and trace pipeline.

### Planner Agent

Classifies user intent, selects the target agent, and suggests the required tool when a tool is needed.

Examples:

- General chat
- Coding request
- Git or GitHub workflow
- Kubernetes or Docker operation
- File or system inspection

---

### DevOps Agent

Provides the infrastructure-oriented agent grouping used by Git, Kubernetes, Docker, and related operational tools.

Current scope:

- Local Git inspection
- Container runtime status
- Kubernetes resource operations
- Infrastructure command routing through guarded tools

---

### Coding Agent

Handles code analysis, code transformation, automated modification, validation, self-correction, and guarded code workflows.

Current capabilities:

- Explain, review, and transform code
- Read project files safely
- Search project code
- Modify files only on explicit request
- Run allowlisted validation commands
- Retry one self-correction when validation fails
- Return diff and validation summaries

---

### Validator Agent

Validates tool output before it is used in the final answer.

Current checks:

- Empty result
- Error text
- Command failure
- Timeout
- Unusable output format

---

### Git Agent

Handles local Git repository inspection and guarded Git operations.

Current capabilities:

- Git status
- Git branch
- Git diff for modified files
- Guarded write/destructive command handling

---

### GitHub Agent

Handles GitHub repository interactions through the existing API structure and authentication flow.

Current capabilities:

- Repository lookup
- Create pull request
- Create issue
- Create release
- Create branch
- Commit/push through GitHub API when explicitly allowed

---

### API Agent

Handles external API-oriented tasks through registered API tools.

Current scope:

- GitHub repository API calls
- Network utility API calls
- API tool routing through the shared registry

---

### Kubernetes Agent

Handles Kubernetes inspection and guarded operational commands.

Current capabilities:

- Pod status
- Logs
- Exec
- Apply
- Delete
- Scale
- Rollout restart

---

### Docker Agent

Handles Docker runtime inspection and guarded container operations.

Current capabilities:

- Docker container status
- Build
- Run
- Logs
- Stop
- Remove
- Compose up/down

---

### File Agent

Handles project file and directory lookup.

Current capabilities:

- Project file listing
- Directory inspection
- Safe project-root-bounded file access

---

### System Agent

Handles local runtime and system-level status requests.

Current capabilities:

- System status
- Public IP lookup
- SQLite memory status

---

## Tool Execution System

Agents do not execute arbitrary work directly. They use the Tool Registry to select a registered tool, execute it, validate its output, and return a controlled result.

Current tool groups:

| Group | Examples |
| --- | --- |
| Coding Tools | `list_directory`, `read_file`, `search_code`, `write_file`, `replace_in_file`, `run_validation` |
| Git Tools | `get_git_status`, `get_git_branch`, `get_git_diff` |
| GitHub Tools | repository lookup, pull request, issue, release, branch |
| Kubernetes Tools | pods, logs, exec, apply, delete, scale, rollout restart |
| Docker Tools | ps, build, run, logs, stop, rm, compose up/down |
| System Tools | memory status, system status, public IP |

Safety rules:

- No file modification without explicit edit intent
- No project-root escape
- Sensitive file names are blocked
- Validation commands are allowlisted
- Git commit/push is not run automatically
- Coding self-correction retries at most once

---

## Frontend Dashboard

The frontend is a runtime dashboard, not only a chat UI.

Current dashboard features:

- Real-time chat
- Agent activity
- Tool status
- Execution trace
- Session history
- Settings
- Memory controls

---

## 프로젝트 구조

```text
backend/
  app/
    agent/
      planner.py
      model_router.py
      role_agents.py
      runner.py
    agents/
      devops_agent.py
      api_agent.py
      orchestrator_agent.py
    tools/
      registry.py
      validation.py
      local_tools.py

frontend/
  src/
    components/
    data/
    utils/

k8s/
```

---

## Environment Setup

### Required

- Python 3.14+
- Node.js 24+
- Docker Desktop
- Kubernetes with kind
- Ollama

### Python Environment

```bash
python -m venv .venv
```

Activate on Windows:

```powershell
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Run Guide

### Backend

```bash
uv run uvicorn backend.app.api.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger:

```text
http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

### Build

```bash
cd frontend
npm run build
```

---

## API

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/health` | Backend health check |
| GET | `/tools` | Tool metadata for dashboard discovery |
| POST | `/chat` | Chat endpoint |
| POST | `/api/chat` | API chat endpoint used by the dashboard |

---

## 핵심 목표

MAOS is not intended to be a basic LLM chat demo. The goal is to implement a local, inspectable, multi-agent runtime that can route work, execute tools, validate results, preserve memory, and expose operational traces.

The project focuses on practical agent engineering patterns:

- Planner-driven routing
- Role-specific agents
- Tool registry and permission checks
- Memory-backed request context
- Validation and self-correction
- Runtime observability

---

## 현재 구현 상태

Implemented capabilities:

- Multi-agent architecture
- Planner Agent
- Coding Agent
- Validator Agent
- Git Agent
- GitHub Agent
- Kubernetes Agent
- Docker Agent
- File Agent
- System Agent
- Tool Registry
- Persistent SQLite memory
- Request trace and runtime metrics
- File read/write safety guards
- Allowlisted validation runner
- React dashboard
- FastAPI backend
- Ollama local model integration

---

## 개발 목적

This project demonstrates how an agent platform can move beyond direct LLM calls into a structured runtime with planning, tool execution, validation, memory, and traceability.

MAOS is built as a personal AI engineering project focused on practical architecture, local execution, and safe automation.
