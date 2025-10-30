# Getting Started: API Keys Setup

This guide walks you through obtaining the necessary API keys to run Agentic AI HEMS.

## Required API Keys

You need two types of API keys:

1. **LLM Provider API Key** - For running the AI orchestrator (required)
2. **ENTSO-E API Key** - For day-ahead electricity prices (required)

---

## 1. LLM Provider API Key

### Model Selection

The dashboard automatically fetches all available models from your configured provider's API and displays them in an intelligent dropdown:

- **Recently Used**: Your most recently used models appear at the top for quick access (stored in browser localStorage)
- **Newest Models**: Latest models sorted by creation date
- **Other Models**: All remaining available models (collapsible section)

Models are dynamically updated each time you load the dashboard, ensuring you always have access to your provider's current model catalog. If the API is unavailable, the system falls back to a curated list of known models.

---

Choose ONE of the following providers based on your needs.

### Option A: Cerebras (Recommended)

**Why Cerebras?**
- High-performance inference infrastructure
- Suitable for research and experimentation

**Steps:**

1. **Sign Up**
   - Go to: https://cloud.cerebras.ai/
   - Click "Sign Up" and create an account
   - Verify your email

2. **Get API Key**
   - Log in to Cerebras Cloud
   - Navigate to "API Keys" section
   - Click "Create New API Key"
   - Copy your API key

3. **Add to .env**
   ```bash
   CEREBRAS_API_KEY=your_cerebras_key_here
   CEREBRAS_MODEL=your_model_id
   ```

Check the dashboard for available models after setup.

---

### Option B: OpenAI

**Why OpenAI?**
- State-of-the-art models
- Reliable and well-documented

**Steps:**

1. **Sign Up**
   - Go to: https://platform.openai.com/signup
   - Create account and add payment method

2. **Get API Key**
   - Go to: https://platform.openai.com/api-keys
   - Click "Create new secret key"
   - Copy your API key (starts with `sk-`)

3. **Add to .env**
   ```bash
   OPENAI_API_KEY=your_openai_key_here
   LLM_PROVIDER=openai
   LLM_API_BASE=https://api.openai.com
   CEREBRAS_MODEL=your_model_id
   ```

Check the dashboard for available models after setup.

---

### Option C: OpenRouter (Multi-Provider Aggregator)

**Why OpenRouter?**
- Access 100+ models from one API
- Includes Claude, Gemini, Llama, Mistral
- Pay-as-you-go, no subscriptions

**Steps:**

1. **Sign Up**
   - Go to: https://openrouter.ai/
   - Sign up with GitHub or email

2. **Get API Key**
   - Navigate to "Keys" section
   - Create new API key
   - Add credits to your account

3. **Add to .env**
   ```bash
   OPENAI_API_KEY=your_openrouter_key_here
   LLM_PROVIDER=openrouter
   LLM_API_BASE=https://openrouter.ai/api
   CEREBRAS_MODEL=your_model_id
   ```

Check https://openrouter.ai/models for available models.

---

### Option D: Local LLM (Ollama)

**Why Local?**
- Free (after hardware cost)
- Full privacy
- No API rate limits

**Steps:**

1. **Install Ollama**
   - Download from: https://ollama.ai/
   - Install for your OS (Mac, Linux, Windows)

2. **Pull a Model**
   ```bash
   ollama pull <model_name>
   ```

3. **Add to .env**
   ```bash
   LLM_API_KEY=not_required_for_local
   LLM_PROVIDER=custom
   LLM_API_BASE=http://localhost:11434
   CEREBRAS_MODEL=<model_name>
   ```

Check available models with `ollama list` or at https://ollama.ai/library

---

## 2. ENTSO-E API Key

ENTSO-E (European Network of Transmission System Operators for Electricity) provides free access to European electricity market data.

**Research Context**: This system uses wholesale day-ahead market prices as a reliable data source for research purposes. In real-world deployments, households typically face retail tariffs from their utility providers, which may differ from wholesale prices. For production implementation, replace ENTSO-E data with actual household tariff structures from the relevant utility contracts.

### Steps:

1. **Register an Account**
   - Go to: https://transparency.entsoe.eu/
   - Click "Login" → "Register"
   - Fill in your details (name, email, organization)
   - Verify your email address

2. **Request API Access**
   - Send an email to: transparency@entsoe.eu
   - Subject line: "Restful API access"
   - Body: Include the email address you used for registration
   - Wait for approval (typically 1-2 business days)

3. **Generate API Token**
   - After approval, log in to your account
   - Go to "Account Settings" or "My Account"
   - Find "Web API Security Token" section
   - Click "Generate New Token"
   - Copy your API key (long alphanumeric string)

4. **Add to .env**
   ```bash
   ENTSOE_API_KEY=your_actual_key_here
   BIDDING_ZONE=AT  # Use your country code: AT, DE, FR, etc.
   ```

### Supported Bidding Zones:

- **AT**: Austria
- **DE**: Germany
- **FR**: France
- **NL**: Netherlands
- **CH**: Switzerland
- See full list: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html

**Note**: ENTSO-E API is free but rate-limited. Respect the limits to avoid temporary blocks.

---

## Verify Setup

After adding your API keys to `.env`:

1. **Test ENTSO-E Connection**
   ```bash
   curl "https://web-api.tp.entsoe.eu/api?securityToken=YOUR_KEY&documentType=A44&in_Domain=10YAT-APG------L&out_Domain=10YAT-APG------L&periodStart=202501010000&periodEnd=202501020000"
   ```

2. **Test LLM Provider**
   ```bash
   # Start the API
   python agentic-hems/api.py

   # In another terminal
   curl http://localhost:5001/api/models
   ```

3. **Run Test Prompt**
   - Open dashboard: `http://localhost:8000/dashboard.html`
   - Try example prompt: "Schedule my dishwasher for tomorrow"
   - Check that you see agent reasoning and output

---

## Security Best Practices

1. **Never commit `.env` file to git**
   - Already in `.gitignore`
   - Use `.env.example` for templates

2. **Use environment-specific keys**
   - Separate keys for dev and production
   - Rotate keys regularly

3. **Monitor usage**
   - Set up billing alerts with providers
   - Check API usage dashboards weekly

4. **Restrict API key permissions**
   - Use read-only keys where possible
   - Set spending limits on provider dashboards

---

## Need Help?

- ENTSO-E issues: Check their API guide at https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html
- LLM provider issues: See [Troubleshooting Guide](TROUBLESHOOTING.md)
- General setup: Open an issue at https://github.com/redaelmakroum/agentic-ai-hems/issues
