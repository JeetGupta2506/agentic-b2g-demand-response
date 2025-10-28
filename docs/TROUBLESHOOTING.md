# Troubleshooting Guide

Common issues and solutions for Agentic AI HEMS.

---

## Docker Issues

### Containers won't start

**Symptom**: `docker-compose up` fails or containers exit immediately

**Solutions**:

1. **Check .env file exists**
   ```bash
   ls -la .env
   # If missing: cp .env.example .env
   ```

2. **Validate .env has required keys**
   ```bash
   grep -E "ENTSOE_API_KEY|CEREBRAS_API_KEY" .env
   ```

3. **Check port conflicts**
   ```bash
   # Ports 5000 and 8000 must be free
   lsof -i :5000
   lsof -i :8000
   # If occupied, stop conflicting services or change ports in docker-compose.yml
   ```

4. **View container logs**
   ```bash
   docker-compose logs hems-api
   docker-compose logs hems-dashboard
   ```

5. **Rebuild containers**
   ```bash
   docker-compose down
   docker-compose build --no-cache
   docker-compose up -d
   ```

---

### Health check failing

**Symptom**: `docker ps` shows container as "unhealthy"

**Solutions**:

1. **Check API is responding**
   ```bash
   curl http://localhost:5000/api/health
   ```

2. **Verify curl is installed in container**
   - Health check requires `curl` command
   - If needed, add to Dockerfile:
   ```dockerfile
   RUN apt-get update && apt-get install -y curl
   ```

3. **Increase health check timeout**
   - Edit `docker-compose.yml`:
   ```yaml
   healthcheck:
     start_period: 60s  # Give more startup time
   ```

---

### Volume mount issues

**Symptom**: Changes to code not reflected in container

**Solutions**:

1. **Restart container**
   ```bash
   docker-compose restart hems-api
   ```

2. **Verify volume mounts**
   ```bash
   docker inspect agentic-hems-api | grep -A5 Mounts
   ```

3. **For Python code changes**
   - Restart is needed (Flask debug mode not enabled in production)
   - Or enable debug in `api.py` (not recommended for production)

---

## API Issues

### "No API key found" error

**Symptom**: API returns error about missing API key

**Solutions**:

1. **Check .env file format**
   - No spaces around `=`
   - No quotes around values (usually)
   ```bash
   # Correct
   CEREBRAS_API_KEY=csk-abc123

   # Incorrect
   CEREBRAS_API_KEY = csk-abc123
   CEREBRAS_API_KEY="csk-abc123"
   ```

2. **Verify environment variables loaded**
   ```bash
   # Inside container
   docker exec agentic-hems-api env | grep API_KEY

   # Local
   python -c "import os; print(os.getenv('CEREBRAS_API_KEY'))"
   ```

3. **Restart after .env changes**
   ```bash
   docker-compose down
   docker-compose up -d
   ```

---

### "Rate limit exceeded" error

**Symptom**: API returns 429 status code

**Solutions**:

1. **Wait for rate limit to reset**
   - Check `X-RateLimit-Reset` header for reset time

2. **Increase rate limits**
   - Edit `api.py`:
   ```python
   @limiter.limit("50 per minute")  # Increase from 20
   ```

3. **Use different API key**
   - Some providers allow multiple keys

---

### Orchestrator timeout

**Symptom**: "Orchestrator timed out after 5 minutes"

**Solutions**:

1. **Increase timeout**
   - Edit `api.py` in both the `run_orchestrator()` and `run_orchestrator_stream()` functions:
   ```python
   # In run_orchestrator() - subprocess.run() call
   timeout=600  # 10 minutes instead of 5

   # In run_orchestrator_stream() - process.wait() call
   process.wait(timeout=600)  # 10 minutes instead of 5
   ```

2. **Use faster model**
   - Switch to smaller model in dashboard

3. **Simplify prompt**
   - Break complex requests into smaller tasks
   - Reduce number of appliances in single request

---

## LLM Provider Issues

### Cerebras API errors

**Symptom**: API calls fail with 401, 403, or 500 errors

**Solutions**:

1. **Verify API key is valid**
   ```bash
   curl -H "Authorization: Bearer $CEREBRAS_API_KEY" https://api.cerebras.ai/v1/models
   ```

2. **Check account status**
   - Log in to https://cloud.cerebras.ai/
   - Verify account is active and has credits

3. **Try different model**
   - Some models may be temporarily unavailable
   - Check dashboard for model availability

---

### OpenAI/OpenRouter errors

**Symptom**: Authentication or quota errors

**Solutions**:

1. **Verify API key format**
   - OpenAI keys start with `sk-`
   - OpenRouter keys start with `sk-or-`

2. **Check billing**
   - OpenAI requires payment method
   - OpenRouter requires account balance

3. **Verify API base URL**
   ```bash
   # OpenAI
   LLM_API_BASE=https://api.openai.com

   # OpenRouter
   LLM_API_BASE=https://openrouter.ai/api
   ```

---

### Local LLM (Ollama) issues

**Symptom**: Cannot connect to local model

**Solutions**:

1. **Verify Ollama is running**
   ```bash
   curl http://localhost:11434/api/tags
   ```

2. **Start Ollama service**
   ```bash
   ollama serve
   ```

3. **Check model is pulled**
   ```bash
   ollama list
   # If missing: ollama pull <model_name>
   ```

4. **Update API base URL**
   ```bash
   LLM_API_BASE=http://host.docker.internal:11434  # For Docker
   LLM_API_BASE=http://localhost:11434  # For local
   ```

---

## ENTSO-E Issues

### "Invalid API key" error

**Symptom**: ENTSO-E requests return 401 Unauthorized

**Solutions**:

1. **Verify key format**
   - Should be long alphanumeric string (40+ characters)
   - No spaces or line breaks

2. **Check key is activated**
   - Log in to https://transparency.entsoe.eu/
   - Verify key shows as "Active" in account settings

3. **Test key directly**
   ```bash
   curl "https://web-api.tp.entsoe.eu/api?securityToken=YOUR_KEY&documentType=A44&in_Domain=10YAT-APG------L&out_Domain=10YAT-APG------L&periodStart=202501010000&periodEnd=202501020000"
   ```

---

### "No data available" for bidding zone

**Symptom**: ENTSO-E returns empty data or error

**Solutions**:

1. **Verify bidding zone code**
   - Check correct code at: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html
   - Example: `AT`, not `Austria`

2. **Check data availability**
   - Some zones don't publish day-ahead prices
   - Try different zone for testing

3. **Verify date range**
   - ENTSO-E only has recent data (typically last 2 years)
   - Future data only available 1-2 days ahead

---

### ENTSO-E rate limiting

**Symptom**: Requests blocked after multiple calls

**Solutions**:

1. **Reduce request frequency**
   - ENTSO-E has strict rate limits
   - Cache price data locally

2. **Wait before retrying**
   - Usually 5-10 minute cooldown

3. **Implement backoff strategy**
   - Add retry logic with exponential backoff

---

## Dashboard Issues

### Dashboard not loading

**Symptom**: Blank page or connection refused

**Solutions**:

1. **Verify HTTP server is running**
   ```bash
   # Docker
   docker-compose ps hems-dashboard

   # Local
   cd agentic-hems && python -m http.server 8000
   ```

2. **Check correct URL**
   - Should be: `http://localhost:8000/dashboard.html`
   - Not: `http://localhost:5000/dashboard.html`

3. **Clear browser cache**
   - Hard refresh: `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (Mac)

---

### Models not loading in dropdown

**Symptom**: Model dropdown is empty or shows "Failed to fetch models"

**Solutions**:

1. **Check API is running**
   ```bash
   curl http://localhost:5000/api/health
   ```

2. **Test models endpoint**
   ```bash
   curl http://localhost:5000/api/models
   ```

3. **Verify CORS is enabled**
   - Should be enabled by default in `api.py`
   - Check browser console for CORS errors

4. **Check LLM provider API key**
   - Models fetched from provider's API
   - Requires valid API key

---

### Streaming output not working

**Symptom**: No real-time output, or output appears all at once

**Solutions**:

1. **Check browser support**
   - EventSource API required (all modern browsers)
   - Try different browser

2. **Disable browser extensions**
   - Ad blockers may interfere with SSE

3. **Check proxy settings**
   - Some proxies buffer SSE streams
   - Try direct connection

---

## Performance Issues

### Slow orchestrator execution

**Symptom**: Takes >2 minutes for simple requests

**Solutions**:

1. **Use faster model**
   - Select a smaller/faster model in dashboard

2. **Check network latency**
   - Test API provider response time
   - Consider local LLM for privacy/speed

3. **Optimize prompt**
   - Shorter, more specific prompts
   - Reduce constraint complexity

---

### High memory usage

**Symptom**: Container or process consuming excessive RAM

**Solutions**:

1. **Limit container memory**
   - Add to `docker-compose.yml`:
   ```yaml
   mem_limit: 2g
   ```

2. **Use smaller model**
   - Smaller models use less memory

3. **Monitor data/runs folder**
   ```bash
   du -sh data/runs/
   # Clean old runs if needed
   ```

---

## Development Issues

### Python import errors

**Symptom**: `ModuleNotFoundError` when running scripts

**Solutions**:

1. **Verify virtual environment**
   ```bash
   which python
   # Should show venv path

   # Activate if needed
   source venv/bin/activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r agentic-hems/requirements.txt
   pip install -r agentic-hems/requirements-api.txt
   ```

3. **Check Python version**
   ```bash
   python --version
   # Should be 3.11+
   ```

---

### Changes not taking effect

**Symptom**: Code changes don't appear to work

**Solutions**:

1. **Restart Flask server**
   ```bash
   # Ctrl+C to stop, then restart
   python agentic-hems/api.py
   ```

2. **Clear Python cache**
   ```bash
   find . -type d -name "__pycache__" -exec rm -r {} +
   find . -type f -name "*.pyc" -delete
   ```

3. **Rebuild Docker image**
   ```bash
   docker-compose build --no-cache
   docker-compose up -d
   ```

---

## Still Having Issues?

1. **Check logs**
   ```bash
   # Docker
   docker-compose logs -f

   # Local
   # Check terminal output from api.py
   ```

2. **Enable debug mode**
   - Edit `api.py`:
   ```python
   app.run(host='0.0.0.0', port=5000, debug=True)
   ```

3. **Search existing issues**
   - GitHub: https://github.com/redaelmakroum/agentic-ai-hems/issues

4. **Open new issue**
   - Include:
     - Error message (full stack trace)
     - Environment (Docker/local, OS, Python version)
     - Steps to reproduce
     - What you've already tried
