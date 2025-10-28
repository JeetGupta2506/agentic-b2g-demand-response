# Architecture Overview

This document describes the simulation architecture of the Agentic AI HEMS system. For HEMS domain concepts (energy optimization, appliance scheduling), refer to the research paper.

---

## System Overview

Agentic AI HEMS is a research simulation platform demonstrating LLM-based orchestration for home energy management. The system uses a ReAct (Reasoning + Acting) pattern where an orchestrator LLM coordinates specialist agents through structured prompts.

---

## Core Components

### 1. Web Dashboard (`dashboard.html`)

**Purpose**: Interactive interface for running simulations

**Key Features**:
- Natural language prompt input
- Dynamic model selection (fetches available models from provider API)
- Real-time execution streaming via Server-Sent Events (SSE)
- Results visualization with scheduling charts
- Analytics page showing aggregated metrics across runs

**Technology**: Vanilla JavaScript, Chart.js for visualizations

---

### 2. Flask API Server (`api.py`)

**Purpose**: HTTP API layer between dashboard and orchestrator

**Endpoints**:
- `POST /api/run/stream` - Execute orchestrator with real-time streaming output
- `GET /api/models` - Fetch available LLM models from provider
- `GET /api/health` - Health check

**Key Behavior**:
- Spawns orchestrator as subprocess
- Sets `CEREBRAS_MODEL_OVERRIDE` environment variable for dynamic model selection
- Streams stdout from orchestrator to dashboard via SSE
- Rate limiting to prevent API quota exhaustion

---

### 3. ReAct Orchestrator (`orchestrator_agent_react.py`)

**Purpose**: Main LLM-based coordinator using Reasoning-Action pattern

**Architecture**:
```
User Request
    ↓
[Security Validation]
    ↓
[ReAct Loop: max 15 iterations]
    ↓
Thought → Action → Observation
    ↓
Context accumulation
    ↓
Final Summary
```

**Available Actions**:
- `GET_PRICES` - Fetch day-ahead electricity prices from ENTSO-E
- `GET_CALENDAR_CONSTRAINT` - Check calendar for EV charging deadlines
- `CALCULATE_WINDOW_SUMS` - Analyze price windows for optimization
- `CALL_AGENT` - Delegate to specialist appliance agent
- `SCHEDULE` - Execute appliance schedule
- `FINISH` - Complete orchestration

**Prompt Structure**:
- System prompt loaded from `hems_orchestrator.md`
- ReAct instructions added programmatically
- Action format: `ACTION: TYPE | param1=value1 | param2=value2`

**Context Management**:
- Prices data stored after `GET_PRICES`
- Calendar constraints stored after `GET_CALENDAR_CONSTRAINT`
- Agent results accumulated for each appliance
- Executed schedules tracked for final summary

---

### 4. Specialist Agents

**Architecture**: Agents are markdown prompt files, not separate code modules.

**Available Agents**:
- `dishwasher_agent.md`
- `washing_machine_agent.md`
- `ev_charger_agent.md`

**Agent Execution Flow**:
1. Orchestrator calls `call_appliance_agent()` in `tools.py`
2. Agent prompt loaded from `.md` file
3. LLM called with agent prompt + price data + user request
4. Agent returns structured recommendation (slot, duration, cost, reasoning)
5. Orchestrator validates recommendation against optimal schedule
6. If significant discrepancy (>20%), orchestrator may retry agent call

---

### 5. Tools Module (`tools.py`)

**Purpose**: Utility functions executed by orchestrator actions

**Key Functions**:
- `get_electricity_prices()` - ENTSO-E API client wrapper
- `call_appliance_agent()` - Load agent prompt and call LLM
- `schedule_appliance()` - Generate 96-element schedule array
- `get_calendar_ev_constraint()` - Parse Google Calendar events
- `calculate_window_sums()` - Sliding window analysis for price optimization

---

### 6. Configuration (`config.py`)

**Purpose**: Centralized configuration and appliance specifications

**Contents**:
- LLM provider configuration (API keys, model selection)
- `AVAILABLE_APPLIANCES` - Dictionary with appliance specs (power rating, duration, agent file)
- ENTSO-E settings (API key, bidding zone)

**Appliance Specification Structure**:
```python
{
    "dishwasher": {
        "agent_file": "dishwasher_agent.md",
        "default_duration_minutes": 120,
        "power_rating_kw": 1.8,
        "default_deadline": None,
        "default_request": "Schedule for a 2-hour cycle. Optimize for lowest cost.",
        "control_type": "binary"
    }
}
```

---

### 7. Security Layer (`security.py`)

**Purpose**: Input validation and sanitization

**Key Features**:
- Pattern detection for malicious inputs (SQL injection, command injection)
- XML wrapping for privilege separation
- Risk level assessment (low/medium/high)
- Rejection of out-of-scope requests

---

## Data Flow

### Typical Simulation Run

```
1. User enters prompt in dashboard
   ↓
2. Dashboard sends POST to /api/run/stream with prompt + model
   ↓
3. API spawns orchestrator subprocess
   - Sets CEREBRAS_MODEL_OVERRIDE env var
   - Captures stdout in real-time
   ↓
4. Orchestrator validates input (security.py)
   ↓
5. ReAct Loop:
   Iteration 1: Thought → ACTION: GET_PRICES → Observation
   Iteration 2: Thought → ACTION: CALL_AGENT | ... → Observation
   Iteration 3: Thought → ACTION: SCHEDULE | ... → Observation
   ...
   Iteration N: Thought → ACTION: FINISH | summary=... → Done
   ↓
6. Orchestrator saves run data to data/runs/{model}/run_{timestamp}.json
   ↓
7. API streams each iteration output to dashboard via SSE
   ↓
8. Dashboard displays results and charts
```

---

## Execution Traces

All runs saved to `data/runs/` organized by model:

```
data/runs/
├── model-a/
│   ├── run_20251017_153045.json
│   └── run_20251017_154132.json
└── model-b/
    └── run_20251017_160230.json
```

**Trace Contents** (`run_*.json`):
```json
{
  "timestamp": "2025-10-17T15:30:45",
  "model": "model-name",
  "user_request": "Schedule all flexible loads",
  "success": true,
  "iterations": 7,
  "duration_seconds": 12.3,
  "total_tokens": 3245,
  "total_cost": 0.042,
  "prices_data": {...},
  "calendar_constraint": {...},
  "agent_results": {...},
  "executed_schedules": [...],
  "actions_taken": [...],
  "final_summary": "..."
}
```

**Usage**:
- Dashboard analytics page aggregates metrics across runs
- Researchers can analyze LLM performance, token usage, cost
- Traces enable reproducibility and debugging

---

## Time Resolution

**Fixed Resolution**: 15-minute intervals (96 slots per 24 hours)

**Why 15 minutes?**
- Matches day-ahead electricity market resolution
- Sufficient granularity for household appliances
- Keeps computation tractable

**Slot Indexing**:
- Slot 0 = 00:00-00:15
- Slot 1 = 00:15-00:30
- Slot 95 = 23:45-00:00

---

## Provider-Agnostic Design

The system works with any OpenAI-compatible API:

**Supported Providers**:
- Cerebras
- OpenAI
- OpenRouter (multi-provider aggregator)
- Local LLMs (Ollama, LM Studio)

**Dynamic Model Selection**:
1. Dashboard fetches available models from provider's `/v1/models` endpoint
2. User selects model from dropdown
3. API passes model ID via `CEREBRAS_MODEL_OVERRIDE` environment variable
4. Orchestrator uses selected model for all LLM calls

---

## Error Handling

### Orchestrator Level
- Max iterations limit (15) prevents infinite loops
- Action parsing handles multiple LLM output formats (robustness across models)
- Context preserved across iterations for debugging

### API Level
- Timeout protection (5 minutes max)
- Rate limiting prevents quota exhaustion
- Structured error responses with action history

### Agent Level
- Input validation before LLM calls
- Cost calculations validated against price data
- Error messages stored in execution traces

