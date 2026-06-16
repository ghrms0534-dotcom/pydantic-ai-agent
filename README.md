# MAOS

MAOS는 **Multi-Agent Orchestration System**의 약자이다.

이 프로젝트는 로컬 환경에서 실행 가능한 AI Agent Runtime System을 직접 설계하고 구축하는 것을 목표로 한다.

기존 단일 LLM 기반 Chatbot 구조가 아니라, 사용자의 요청을 분석하고 역할별 Agent가 작업을 수행하며 Tool 실행 결과를 검증하는 **Multi-Agent Architecture (MAS)** 구조를 기반으로 설계하였다.

최종 목표는 단순 질의응답 시스템이 아닌 **Production 수준의 AI Agent Platform 구축**이다.

---

## 시스템 개요

사용자가 자연어로 질문을 입력하면 시스템은 질문을 분석하여 어떤 작업인지 먼저 판단한다.

일반적인 Chat 요청인지, Kubernetes 상태 조회인지, Git 상태 확인인지, API 호출이 필요한 작업인지 먼저 분류한 뒤 적절한 Agent를 선택한다.

선택된 Agent는 필요한 Tool을 실행하고 결과를 검증한 후 최종 응답을 생성한다.

전체 시스템은 다음과 같은 구조로 동작한다.

```text
사용자 요청
   │
   ▼
Frontend Dashboard (React)
   │
   ▼
FastAPI Backend
   │
   ▼
Planner Agent
   │
   ▼
Role Agent Selection
(Chat / DevOps / API / Local)
   │
   ▼
Tool Selection
   │
   ▼
Tool Execution
   │
   ▼
Validation Layer
   │
   ▼
Final Response
```

---

## 시스템 구성 요소

이 프로젝트를 구성하는 모든 요소는 로컬 환경에서 직접 실행 가능하도록 설계하였다.

| 구성 요소          | 기술                | 역할                                |
| ------------------ | ------------------- | ----------------------------------- |
| Frontend Dashboard | React + TypeScript  | 사용자 채팅 UI 및 Agent 상태 시각화 |
| Backend API        | FastAPI             | API 서버 및 Agent Runtime 관리      |
| Agent Framework    | PydanticAI          | Agent 실행 구조 관리                |
| Model Runtime      | Ollama              | 로컬 LLM 실행                       |
| Planner            | Python              | 사용자 요청 분석 및 작업 분류       |
| Role Agents        | Python              | 역할별 Agent 실행                   |
| Tool Registry      | Python              | 사용 가능한 Tool 중앙 관리          |
| Validation Layer   | Python              | Tool 실행 결과 검증                 |
| Infrastructure     | Docker + Kubernetes | 컨테이너 실행 및 배포 환경          |

---

## Agent Architecture

시스템은 역할별 Agent 구조를 기반으로 동작한다.

각 Agent는 독립적인 역할을 수행하도록 분리하였다.

현재 Agent 구조는 다음과 같다.

### Planner Agent

사용자의 요청을 분석하여 어떤 유형의 작업인지 먼저 판단한다.

예시

- 일반 대화
- Kubernetes 관련 요청
- Git 관련 요청
- GitHub API 요청
- 시스템 로컬 작업 요청

---

### DevOps Agent

인프라 관련 작업을 담당한다.

지원 작업

- Kubernetes Pod 상태 조회
- Deployment 상태 확인
- Docker Container 조회
- Infrastructure 상태 확인

---

### Git Agent

Git 관련 작업을 담당한다.

지원 작업

- Git Status 확인
- Branch 조회
- Commit 상태 확인
- Remote Repository 확인

---

### API Agent

외부 API 호출이 필요한 작업을 담당한다.

지원 작업

- GitHub Repository API
- Network API
- 외부 서비스 상태 확인

---

## Tool Execution System

Agent는 직접 작업하지 않는다.

각 Agent는 Tool Registry에 등록된 Tool을 선택하여 작업을 수행한다.

현재 Tool 구조는 다음과 같다.

Infrastructure Tools

- Kubernetes Tool
- Docker Tool

Development Tools

- Git Tool
- GitHub Tool

System Tools

- Network Tool
- Local System Tool

모든 Tool 실행 이후 Validation Layer가 결과를 검증한다.

검증 항목

- 응답 데이터 존재 여부
- Error 문자열 확인
- 비정상 출력 감지
- 사용자 응답 가능 여부 판단

---

## Frontend Dashboard

Frontend는 단순 Chat UI가 아니다.

Agent Runtime 상태를 실시간으로 시각화하도록 설계하였다.

현재 Dashboard 기능

- 실시간 Chat
- Agent Activity 확인
- Tool 상태 확인
- Execution Trace
- Session History
- Settings 관리

---

## 프로젝트 구조

```text
backend/

app/agent/
 ├── planner.py
 ├── model_router.py
 ├── role_agents.py
 ├── runner.py

app/agents/
 ├── devops_agent.py
 ├── api_agent.py
 ├── orchestrator_agent.py

app/tools/
 ├── registry.py
 ├── validation.py

frontend/

k8s/
```

---

## 핵심 목표

이 프로젝트의 목적은 단순히 AI Chatbot을 만드는 것이 아니다.

직접 Multi-Agent System Architecture를 설계하고 실제 동작 가능한 Runtime Platform 형태로 구현하는 것이다.

현재 AI 시스템은 단순 LLM 호출에서 벗어나 여러 Agent가 역할을 분리하고 Tool을 활용하는 방향으로 발전하고 있다.

이 프로젝트는 그러한 구조를 로컬 환경에서 직접 구현하는 것을 목표로 한다.

---

## 현재 구현 상태

현재 구현 완료 항목

- Multi-Agent Architecture
- Planner Agent
- Role-based Agent Structure
- Tool Registry
- Tool Validation System
- FastAPI API Server
- React Dashboard
- Ollama Local Model Integration
- Docker Container Runtime
- Kubernetes Deployment

---

## 개발 목적

AI Engineering 분야에서는 단순 LLM 호출보다 실제 Agent Runtime 구조 설계가 중요해지고 있다.

이 프로젝트는 그러한 구조를 이해하고 직접 구현하기 위한 개인 AI Engineering Project이다.
