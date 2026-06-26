# MAOS

MAOS 는 Local LLM 기반으로 동작하는 **Autonomous Multi-Agent Runtime Platform** 입니다.

기존 LLM 서비스는 단일 Prompt 입력 후 단일 Response를 생성하는 구조에 머무르지만, 실제 AI Agent 시스템은 작업 계획 수립, 역할 분리, Tool 실행, 결과 검증, Memory 유지, Runtime 추적 구조가 필요합니다.

MAOS는 이러한 한계를 해결하기 위해 **Planning → Agent Routing → Tool Execution → Validation → Memory → Observability** 구조를 갖춘 실제 운영형 Multi-Agent Runtime Architecture를 목표로 설계하고 구현한 프로젝트입니다.

---

<img width="1888" height="863" alt="maos" src="https://github.com/user-attachments/assets/aa2ebe13-f4a3-4ead-bb90-b01fe6318216" />

## 프로젝트 목표

기존 LLM 기반 Assistant의 한계

* 단일 Prompt 기반 단순 응답 구조
* Tool 실행과 Agent 역할 분리 불가
* 결과 검증 구조 부재
* 장기 Memory 유지 어려움
* Runtime 상태 추적 어려움

이를 해결하기 위해 구조화된 Multi-Agent Runtime Platform을 설계하였습니다.

---

## 핵심 기능

### 1. Planner Based Task Routing

사용자 요청을 분석하여 작업 유형을 분류합니다.

지원 Task

* Chat Request
* Code Analysis
* Git Workflow
* GitHub Workflow
* Kubernetes Operations
* Docker Operations
* File Operations
* System Monitoring

Planner Agent가 가장 적절한 Agent를 선택하도록 설계하였습니다.

---

### 2. Role Based Agent Architecture

역할 기반 Agent 구조 구현

지원 Agent

* Coding Agent
* Git Agent
* GitHub Agent
* Kubernetes Agent
* Docker Agent
* File Agent
* System Agent
* Validator Agent

각 Agent는 독립적인 책임을 가지며 Tool Registry를 공유합니다.

---

### 3. Tool Execution Framework

Agent는 직접 작업하지 않고 Tool Registry 기반으로 작업을 수행합니다.

지원 Tool

* File Read / Write
* Code Search
* Git Status / Branch / Diff
* GitHub API Integration
* Kubernetes Resource Control
* Docker Runtime Control
* System Runtime Monitoring

Tool 기반 실행 구조를 설계하였습니다.

---

### 4. Validation Layer

Tool 실행 결과를 검증하는 Validation 구조 구현

검증 항목

* Empty Result
* Error Output
* Timeout Detection
* Invalid Output Structure

잘못된 결과가 최종 응답에 반영되지 않도록 설계하였습니다.

---

### 5. Self Correction Architecture

Validation 실패 시 Agent가 스스로 문제를 수정하도록 설계하였습니다.

동작 흐름

```text
Tool Execution
      ↓
Validation Check
      ↓
Failure Detection
      ↓
Self Correction Retry
      ↓
Final Validation
```

최대 1회 재시도하도록 제한하였습니다.

---

### 6. Persistent Memory Architecture

SQLite 기반 Memory 구조 구현

지원 구조

Short Term Memory

* Current Session Context
* Tool Execution History

Long Term Memory

* Persistent User Context
* Previous Execution State

---

### 7. Runtime Observability

Agent Runtime 상태를 추적할 수 있도록 설계하였습니다.

지원 기능

* Agent Activity Monitoring
* Execution Trace
* Session History
* Runtime Metrics
* Memory Status

---

### 8. Safe Automation Control

위험 작업에 대한 안전 제어 구조 구현

안전 정책

* Project Root Outside Access Block
* Sensitive File Access Block
* Git Push Auto Execution Block
* Validation Command Allowlist
* File Modification Permission Check

---

## 시스템 구조

```text
User Request
      ↓
Planner Agent
      ↓
Role Agent Selection
      ↓
Tool Registry
      ↓
Tool Execution
      ↓
Validation Layer
      ↓
Memory Update
      ↓
Runtime Trace
      ↓
Final Response
```

---

## 기술 스택

Backend

* Python
* FastAPI
* SQLite
* PydanticAI

Frontend

* React
* TypeScript
* Vite

Infrastructure

* Docker
* Kubernetes
* Ollama Local LLM

AI Engineering

* Multi-Agent Architecture
* Tool Calling
* Memory Architecture
* Validation Framework
* Self Correction Loop
* Runtime Observability

---

## 개발하면서 집중한 부분

* Autonomous Multi-Agent Architecture 설계
* Planner 기반 Task Routing 구현
* Tool Registry 구조 설계
* Validation Layer 구현
* Self Correction 구조 구현
* Persistent Memory Architecture 구현
* Runtime Trace Pipeline 구현
* Safe Automation 구조 구현

---

## 기대 효과

* 복잡한 작업을 여러 Agent가 협업하여 수행 가능
* Tool 기반 실제 작업 자동화 가능
* Agent Runtime 상태 추적 가능
* Local First AI Agent Platform 구현 가능
