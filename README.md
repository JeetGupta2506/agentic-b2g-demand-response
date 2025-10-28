# Agentic AI Home Energy Management System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![GitHub stars](https://img.shields.io/github/stars/redaelmakroum/agentic-ai-hems?style=social)](https://github.com/redaelmakroum/agentic-ai-hems/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/redaelmakroum/agentic-ai-hems)](https://github.com/redaelmakroum/agentic-ai-hems/issues)
[![GitHub last commit](https://img.shields.io/github/last-commit/redaelmakroum/agentic-ai-hems)](https://github.com/redaelmakroum/agentic-ai-hems/commits/main)

An agentic AI system for intelligent home energy management. Features autonomous orchestration with specialist agents, real-time electricity price optimization, transparent ReAct reasoning chains, multi-appliance coordination, provider-agnostic LLM support, calendar integration for deadline constraints, comprehensive execution logging, and MILP baseline comparison—all through a real-time streaming dashboard.

This project aims to provide a foundation for exploring agentic AI architectures in demand response scenarios, enabling research in interpretable decision-making, flexible constraint handling, and systematic LLM evaluation for home energy management.

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- API keys:
  - [ENTSO-E](https://transparency.entsoe.eu/) (free, for day-ahead electricity prices)
  - LLM provider: [Cerebras](https://cloud.cerebras.ai/) (recommended), OpenAI, OpenRouter, or local LLM

### 2. Setup

```bash
# Clone repository
git clone https://github.com/redaelmakroum/agentic-ai-hems.git
cd agentic-ai-hems

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-api.txt

# Configure environment
cp .env.example .env
# Edit .env and add your API keys
```

### 3. Run

**Option A: Docker (Recommended)**

```bash
docker-compose up -d
```

Open dashboard: http://localhost:8000/dashboard.html

**Option B: Local**

```bash
# Terminal 1: Start API server
python api.py

# Terminal 2: Start dashboard server
python -m http.server 8000
```

Open dashboard: http://localhost:8000/dashboard.html

### 4. Try It

Enter a prompt in the dashboard:
- "Schedule my dishwasher for tomorrow"
- "Charge my EV tomorrow, optimize for cost"
- "Schedule all flexible loads for minimal cost"

Watch the orchestrator reason through the task in real-time.

---

## Features

### Core Capabilities

- **ReAct Orchestration**: LLM uses Reasoning-Action pattern for transparent decision-making
- **Day-Ahead Pricing**: Fetches electricity prices from ENTSO-E for 15-minute resolution optimization
- **Multi-Appliance Coordination**: Dishwasher, washing machine, EV charger
- **Provider-Agnostic**: Works with Cerebras, OpenAI, OpenRouter, local LLMs (Ollama)
- **Real-Time Streaming**: Watch agent reasoning as it happens via Server-Sent Events
- **Calendar Integration**: EV charging deadlines from Google Calendar

### Research Features

- **Execution Traces**: Every run logged with complete reasoning chain, token usage, and cost
- **Model Comparison**: Test multiple LLMs on same tasks
- **Analytics Dashboard**: Aggregate metrics across runs
- **MILP Baseline**: Compare LLM performance against optimal mixed-integer linear programming

---

## Documentation

- **[Setup Guide](docs/SETUP.md)** - Detailed API key setup and provider configuration
- **[Configuration Reference](docs/CONFIGURATION.md)** - Environment variables and settings
- **[API Documentation](docs/API.md)** - HTTP endpoints and streaming protocol
- **[Architecture Overview](docs/ARCHITECTURE.md)** - System design and data flow
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues and solutions

---

## Project Structure

```
agentic-hems/
├── orchestrator_agent_react.py    # ReAct orchestrator (main entry point)
├── api.py                         # Flask API server
├── dashboard.html                 # Web interface
├── tools.py                       # Utility functions (ENTSO-E, scheduling, calendar)
├── config.py                      # Configuration and appliance specs
├── entsoe_client.py              # Day-ahead price fetching
├── security.py                    # Input validation
├── data/
│   └── runs/{model}/              # Execution traces (JSON logs)
├── milp-baseline/                 # Optimal baseline for comparison
│   └── optimizer.py
├── docs/                          # Documentation
├── dishwasher_agent.md           # Agent prompts
├── washing_machine_agent.md
├── ev_charger_agent.md
├── hems_orchestrator.md
└── docker-compose.yml             # Container orchestration
```

---

## Technical Details

### Time Resolution
- **15-minute intervals** (96 slots per 24 hours)
- Matches day-ahead electricity market granularity
- Configurable in principle, but ENTSO-E data fetching would need adjustment

### LLM Configuration
- **Provider-Agnostic**: Works with any OpenAI-compatible API (Cerebras, OpenAI, OpenRouter, Ollama)
- **Temperature**: 0.0 (deterministic scheduling decisions)
- **Max Iterations**: 15 (prevents infinite loops)

### Data Sources
- **Electricity Prices**: ENTSO-E Transparency Platform (European day-ahead markets)
- **Calendar**: Google Calendar API (optional, for EV deadline constraints)
- **Weather**: Open-Meteo API (available but not actively used - free, no key required)

---

## Contributing

This is an active research project with ongoing development. Issues, questions, and contributions are welcome.

If you use this code in your research, please cite:
```
[Citation details to be added upon publication]
```

If you find this work useful for your research, please consider citing the paper.

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines on code contributions and development setup.

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

## Acknowledgments

This project is supervised by Dr. Sebastian Zwickl-Bernhard and Dr. Lukas Kranzl at TU Wien.

Core development was supported by Claude Code.

---

## Contact

Reda El Makroum, M.Sc.
Technische Universität Wien
elmakroum@eeg.tuwien.ac.at
https://www.redaelmakroum.dev/