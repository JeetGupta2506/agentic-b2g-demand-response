# Configuration Reference

Complete reference for all environment variables and configuration options.

---

## Environment Variables

All configuration is managed through the `.env` file in the project root.

---

## ENTSO-E Configuration

### `ENTSOE_API_KEY` (Required)

**Type**: String
**Description**: API key for ENTSO-E Transparency Platform
**Get it from**: https://transparency.entsoe.eu/

---

### `BIDDING_ZONE` (Required)

**Type**: String
**Description**: European electricity market bidding zone code
**Default**: `AT` (Austria)
**Valid values**: `AT`, `DE`, `FR`, `NL`, `CH`, `BE`, `ES`, `IT`, etc.
**Example**: `BIDDING_ZONE=DE`

**Common Codes**:
- `AT` - Austria
- `DE` - Germany
- `FR` - France
- `NL` - Netherlands
- `CH` - Switzerland
- `BE` - Belgium
- `ES` - Spain
- `IT` - Italy

Full list: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html#_areas

---

## LLM Provider Configuration

Choose ONE of the following provider configurations:

---

### Cerebras (Recommended)

#### `CEREBRAS_API_KEY` (Required)

**Type**: String
**Description**: API key for Cerebras Cloud
**Get it from**: https://cloud.cerebras.ai/

---

#### `CEREBRAS_MODEL`

**Type**: String
**Description**: Model ID to use for orchestrator
**Valid values**: Any model ID from Cerebras API
**Example**: `CEREBRAS_MODEL=model-name`

Check the dashboard for available models - it automatically fetches and displays all models from your provider's API.

---

### OpenAI

#### `OPENAI_API_KEY` (Required)

**Type**: String
**Description**: OpenAI API key
**Format**: Starts with `sk-`
**Get it from**: https://platform.openai.com/api-keys

---

#### `LLM_PROVIDER`

**Type**: String
**Description**: Provider identifier
**Value**: `openai`
**Example**: `LLM_PROVIDER=openai`

---

#### `LLM_API_BASE`

**Type**: URL
**Description**: OpenAI API base URL
**Value**: `https://api.openai.com`
**Example**: `LLM_API_BASE=https://api.openai.com`

---

### OpenRouter

#### `OPENAI_API_KEY` (Required)

**Type**: String
**Description**: OpenRouter API key (reuses OpenAI variable name)
**Format**: Starts with `sk-or-`
**Get it from**: https://openrouter.ai/keys

---

#### `LLM_PROVIDER`

**Type**: String
**Description**: Provider identifier
**Value**: `openrouter`
**Example**: `LLM_PROVIDER=openrouter`

---

#### `LLM_API_BASE`

**Type**: URL
**Description**: OpenRouter API base URL
**Value**: `https://openrouter.ai/api`
**Example**: `LLM_API_BASE=https://openrouter.ai/api`

---

#### `CEREBRAS_MODEL`

**Type**: String
**Description**: Model ID from OpenRouter catalog
**Format**: `provider/model-name`
**Example**: `CEREBRAS_MODEL=provider/model-name`

Browse available models: https://openrouter.ai/models

---

### Local LLM (Ollama)

#### `LLM_API_KEY`

**Type**: String
**Description**: Not required for local LLMs
**Value**: `not_required_for_local`
**Example**: `LLM_API_KEY=not_required_for_local`

---

#### `LLM_PROVIDER`

**Type**: String
**Description**: Provider identifier
**Value**: `custom`
**Example**: `LLM_PROVIDER=custom`

---

#### `LLM_API_BASE`

**Type**: URL
**Description**: Local Ollama API endpoint
**Default**: `http://localhost:11434`
**Docker**: `http://host.docker.internal:11434`
**Example**: `LLM_API_BASE=http://localhost:11434`

---

#### `CEREBRAS_MODEL`

**Type**: String
**Description**: Ollama model name
**Example**: `CEREBRAS_MODEL=model-name:tag`

**Check available models**:
```bash
ollama list
```

---

## Generic Provider Configuration

For providers not explicitly listed above:

#### `LLM_API_KEY` (Required)

**Type**: String
**Description**: API key for your LLM provider

---

#### `LLM_PROVIDER`

**Type**: String
**Description**: Provider identifier for logging
**Options**: `cerebras`, `openai`, `anthropic`, `openrouter`, `custom`
**Example**: `LLM_PROVIDER=custom`

---

#### `LLM_API_BASE`

**Type**: URL
**Description**: Base URL for OpenAI-compatible API
**Example**: `LLM_API_BASE=https://api.yourprovider.com`

---

## Docker-Specific Configuration

### `HEMS_WORK_DIR`

**Type**: Path
**Description**: Working directory for orchestrator execution
**Default**: `/app/agentic-hems` (in Docker)
**Auto-detected**: Uses script directory if not set
**Example**: `HEMS_WORK_DIR=/app/agentic-hems`

**Note**: Set automatically in Dockerfile, usually don't need to change

---

### `VENV_PATH`

**Type**: Path
**Description**: Path to Python virtual environment (local development only)
**Default**: Not set (no venv activation)
**Docker**: Not used (dependencies installed globally in container)
**Example**: `VENV_PATH=/path/to/your/venv`

**Note**: Optional. Only set this if you're running locally and want to activate a specific virtual environment

---

## Reproducible Testing

For research reproducibility, the system supports two methods to ensure consistent price data across experiments.

### Method 1: Lock to Specific Date (API Call)

Fetch prices for a specific historical date from ENTSO-E:

```python
from tools import get_electricity_prices

# Lock to specific date (still makes API call)
prices_data = get_electricity_prices(date="2025-10-15")
```

**Use case:** Running systematic evaluations on the same price profile while ensuring data freshness from ENTSO-E API.

### Method 2: Use Cached Prices (Offline)

Use pre-saved price data without API calls:

```python
from tools import get_electricity_prices

# Use cached file (no API call)
prices_data = get_electricity_prices(use_cached_prices=True)
```

**Use case:** Offline testing, exact reproducibility, or when ENTSO-E API is unavailable.

### Reference Price File

**File**: `test_prices_reference.json` (included in repository)

Contains day-ahead electricity prices from **2025-10-15**, allowing researchers to:
- Reproduce exact experimental conditions
- Compare results across different models on identical price data
- Benchmark against known optimal solutions
- Work offline without ENTSO-E API access

### MILP Baseline

The MILP baseline optimizer (`milp-baseline/optimizer.py`) automatically uses `test_prices_reference.json` for consistent comparison against the same price profile.

### Creating New Reference Prices

To create a new reference price file from a specific date:

```python
from tools import get_electricity_prices
import json

# Fetch prices for specific date
prices_data = get_electricity_prices(date="2025-10-15")

# Save as reference
with open('test_prices_reference.json', 'w') as f:
    json.dump(prices_data, f, indent=2)
```

**Recommendation:** Document the date in your research notes and update the date in this documentation when creating new reference files.

---

## API Server Configuration

These are set in code, not in `.env`. Modify `api.py` to change:

### Flask Server

```python
# In api.py
app.run(
    host='0.0.0.0',  # Bind to all interfaces
    port=5000,       # API port
    debug=True       # Debug mode (disable in production)
)
```

---

### Rate Limiting

```python
# In api.py
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],  # Global limits
    storage_uri="memory://",
    strategy="fixed-window"
)

@app.route('/api/run/stream', methods=['POST'])
@limiter.limit("20 per minute")  # Endpoint-specific limit
```

**Modify to adjust limits**:
- `default_limits`: Global rate limits
- `@limiter.limit()`: Per-endpoint limits

---

### CORS

```python
# In api.py
CORS(app)  # Allow all origins (development)

# Production
CORS(app, origins=['https://yourdomain.com'])
```

---

### Timeouts

```python
# In api.py

# Orchestrator execution timeout (subprocess.run and process.wait calls)
timeout=300  # 5 minutes

# Model API fetch timeout (requests.get in get_models function)
timeout=10  # 10 seconds
```

---

## Dashboard Configuration

Dashboard settings are in `dashboard.html`. No environment variables needed.

### Model Selection

Models are fetched dynamically from provider API. To set default:

```javascript
// In dashboard.html
const DEFAULT_MODEL = 'your-model-id';
```

---

### Example Prompts

```javascript
// In dashboard.html
const examplePrompts = [
    {
        category: "Single Appliance",
        prompts: [
            "Schedule my dishwasher for tomorrow",
            // Add your own examples here
        ]
    }
];
```

---

## Orchestrator Configuration

Settings in `orchestrator_agent_react.py`:

### Max Iterations

```python
max_iterations = 15  # Maximum ReAct loop iterations
```

Prevents infinite loops. Currently hardcoded in the `run()` method of `orchestrator_agent_react.py`. Increase for complex multi-step tasks by modifying the value in the orchestrator's main loop.

---

### Model Override

Set via environment variable (passed from API):

```python
model = os.getenv('CEREBRAS_MODEL_OVERRIDE') or os.getenv('CEREBRAS_MODEL')
```

Dashboard sets `CEREBRAS_MODEL_OVERRIDE` dynamically based on user selection.

---

### System Prompt

```python
SYSTEM_PROMPT = """
You are an expert HEMS orchestrator...
"""
```

Defines agent behavior and reasoning style.

---

## Time Resolution

Fixed at 15-minute intervals (96 slots per 24 hours):

```python
SLOTS_PER_HOUR = 4
SLOTS_PER_DAY = 96
```

**Changing resolution requires**:
- Update ENTSO-E data fetching
- Update scheduling algorithms
- Update visualization (dashboard)

Not recommended unless necessary for research.

---

## Logging and Debugging

### Run Logs

All executions saved to `data/runs/` directory (organized by model):

```
data/runs/
└── model-name/
    ├── run_20251017_153045.json
    ├── run_20251017_154132.json
    └── ...
```

**Clean old runs**:
```bash
find data/runs/ -type f -mtime +30 -delete  # Delete files >30 days old
```

---

### Exporting Results to CSV

For analysis in spreadsheet tools (Excel, Google Sheets), export all run data to CSV:

```bash
python export_results_to_csv.py
```

**Generates two files:**

1. **`scheduling_evaluation.csv`** - Appliance scheduling runs with optimality metrics
2. **`analytical_query_evaluation.csv`** - Analytical query runs (price analysis, time queries)

**Key columns in scheduling_evaluation.csv:**
- `model` - LLM model used
- `appliance_id` - Which appliance was scheduled
- `recommended_slot` - Agent's recommended start slot
- `cost` - Total energy cost (EUR)
- `total_tokens` - Tokens used (orchestrator + specialist agent)
- `success` - Whether run completed successfully
- `iterations` - Number of ReAct iterations

**Use case:** Compare model performance, track success rates, analyze token efficiency across experiments.

---

### Debug Mode

Enable verbose logging:

```python
# In api.py
app.run(debug=True)  # Flask debug mode

# In orchestrator
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## Example `.env` Files

### Minimal (Cerebras)

```bash
ENTSOE_API_KEY=your_entsoe_key
BIDDING_ZONE=AT
CEREBRAS_API_KEY=your_cerebras_key
CEREBRAS_MODEL=model-name
```

---

### OpenAI

```bash
ENTSOE_API_KEY=your_entsoe_key
BIDDING_ZONE=DE
OPENAI_API_KEY=your_openai_key
LLM_PROVIDER=openai
LLM_API_BASE=https://api.openai.com
CEREBRAS_MODEL=model-name
```

---

### Local (Ollama)

```bash
ENTSOE_API_KEY=your_entsoe_key
BIDDING_ZONE=AT
LLM_API_KEY=not_required_for_local
LLM_PROVIDER=custom
LLM_API_BASE=http://localhost:11434
CEREBRAS_MODEL=model-name:tag
```

---

## Validation

Check configuration validity:

```bash
# Test ENTSO-E connection
curl "https://web-api.tp.entsoe.eu/api?securityToken=$ENTSOE_API_KEY&documentType=A44&in_Domain=10YAT-APG------L&out_Domain=10YAT-APG------L&periodStart=202501010000&periodEnd=202501020000"

# Test LLM provider
curl http://localhost:5000/api/models

# Test full flow
curl -X POST http://localhost:5000/api/run/stream \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Schedule dishwasher for tomorrow", "model": "your-model-id"}'
```

---

## Troubleshooting Configuration

### Common Issues

1. **"No API key found"**
   - Check `.env` file exists
   - Verify no spaces around `=`
   - Restart services after changes

2. **"Model not found"**
   - Check model ID is correct
   - Try fetching `/api/models` to see available models

3. **"ENTSO-E connection failed"**
   - Verify API key is activated
   - Check bidding zone code is valid

See [Troubleshooting Guide](TROUBLESHOOTING.md) for detailed solutions.

---

## Configuration Best Practices

1. **Separate Dev/Prod Configs**
   ```bash
   .env.development
   .env.production
   ```

2. **Use Comments**
   ```bash
   # Day-ahead price API
   ENTSOE_API_KEY=your_key_here  # Active until 2026-01
   ```

3. **Version Control**
   - Commit `.env.example` (with placeholders)
   - Never commit `.env` (actual keys)

4. **Validate on Startup**
   - Check required variables exist
   - Test API connections
   - Log configuration summary

---

## Need Help?

- Full setup guide: [SETUP.md](SETUP.md)
- Troubleshooting: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- GitHub Issues: https://github.com/redaelmakroum/agentic-ai-hems/issues
