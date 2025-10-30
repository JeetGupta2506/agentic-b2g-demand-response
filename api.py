"""
Simple Flask API to run orchestrator from web interface.
"""
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import subprocess
import os
import json

app = Flask(__name__)
CORS(app)  # Enable CORS for local development

# Rate limiting configuration
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
    strategy="fixed-window"
)

@app.route('/api/run', methods=['POST'])
@limiter.limit("20 per minute")  # Expensive LLM orchestration
def run_orchestrator():
    """Run the orchestrator with given prompt."""
    data = request.json
    prompt = data.get('prompt', 'Schedule all flexible loads')

    try:
        # Set working directory (container-aware)
        work_dir = os.environ.get('HEMS_WORK_DIR') or os.path.dirname(os.path.abspath(__file__))

        # Virtual environment activation (only for local development)
        venv_path = os.environ.get('VENV_PATH')
        venv_activate = f'source {venv_path}/bin/activate && ' if venv_path and os.path.exists(venv_path) else ''

        # Run orchestrator
        result = subprocess.run(
            [
                'bash', '-c',
                f'{venv_activate}python orchestrator_agent_react.py "{prompt}"'
            ],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        return jsonify({
            'success': True,
            'prompt': prompt,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        })

    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'error': 'Orchestrator timed out after 5 minutes'
        }), 408

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/run/stream', methods=['POST'])
@limiter.limit("20 per minute")  # Expensive LLM orchestration
def run_orchestrator_stream():
    """Run the orchestrator with real-time streaming output."""
    data = request.json
    prompt = data.get('prompt', 'Schedule all flexible loads')
    model = data.get('model', 'llama3.1-8b')

    def generate():
        try:
            # Set working directory (container-aware)
            work_dir = os.environ.get('HEMS_WORK_DIR') or os.path.dirname(os.path.abspath(__file__))

            # Virtual environment activation (only for local development)
            venv_path = os.environ.get('VENV_PATH')
            venv_activate = f'source {venv_path}/bin/activate && ' if venv_path and os.path.exists(venv_path) else ''

            # Set model as environment variable so orchestrator can use it
            env = os.environ.copy()
            env['CEREBRAS_MODEL_OVERRIDE'] = model

            process = subprocess.Popen(
                [
                    'bash', '-c',
                    f'{venv_activate}python -u orchestrator_agent_react.py "{prompt}"'
                ],
                env=env,
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            # Stream stdout
            for line in iter(process.stdout.readline, ''):
                if line:
                    yield f"data: {json.dumps({'type': 'stdout', 'content': line})}\n\n"

            # Wait for process to complete
            process.wait(timeout=300)

            # Send completion message
            yield f"data: {json.dumps({'type': 'done', 'returncode': process.returncode})}\n\n"

        except subprocess.TimeoutExpired:
            yield f"data: {json.dumps({'type': 'error', 'content': 'Timeout after 5 minutes'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/api/models', methods=['GET'])
@limiter.limit("30 per minute")  # Allow frequent model list fetches
def get_models():
    """
    Fetch available models from LLM provider API.

    Supports:
    - OpenAI-compatible APIs (Cerebras, OpenRouter, etc.)
    - Custom provider-specific endpoints

    Returns categorized list of available models.
    """
    try:
        import requests
        import os

        # Get recently used models from query parameter (sent from frontend)
        recently_used = request.args.get('recently_used', '').split(',') if request.args.get('recently_used') else []
        recently_used = [m for m in recently_used if m]  # Remove empty strings

        # Get API configuration from environment
        api_key = os.getenv('CEREBRAS_API_KEY') or os.getenv('OPENAI_API_KEY') or os.getenv('LLM_API_KEY')
        api_base = os.getenv('LLM_API_BASE', 'https://api.cerebras.ai')
        provider = os.getenv('LLM_PROVIDER', 'cerebras')

        if not api_key:
            return jsonify({
                'success': False,
                'error': 'No API key found. Set CEREBRAS_API_KEY, OPENAI_API_KEY, or LLM_API_KEY'
            }), 500

        # Build API endpoint
        models_endpoint = f'{api_base}/v1/models'

        # Fetch models from API
        response = requests.get(
            models_endpoint,
            headers={
                'Authorization': f'Bearer {api_key}'
            },
            timeout=10
        )

        if response.status_code == 200:
            models_data = response.json()

            # Parse models (OpenAI-compatible format)
            all_models = []

            # Handle different response formats
            if 'data' in models_data:
                # OpenAI/Cerebras format: { "data": [...] }
                all_models = models_data['data']
            elif isinstance(models_data, list):
                # Direct list format
                all_models = models_data

            # Convert all models to standardized format
            model_list = []
            for model in all_models:
                if isinstance(model, dict):
                    model_id = model.get('id', '')
                    model_name = model.get('name', model_id)
                    model_desc = model.get('description', '')
                    created = model.get('created', 0)  # Timestamp for recency
                else:
                    model_id = model_name = str(model)
                    model_desc = ''
                    created = 0

                model_list.append({
                    'id': model_id,
                    'name': model_name,
                    'description': model_desc,
                    'created': created
                })

            # Filter text-only models (exclude image/audio models for HEMS use case)
            text_models = [m for m in model_list if not any(x in m['id'].lower() for x in ['image', 'audio', 'vision', 'whisper', 'tts', 'dall-e'])]

            # Categorize models into three groups
            most_used = []
            newest = []
            other = []

            # 1. Most Used - models that appear in recently_used list
            if recently_used:
                for model_id in recently_used:
                    model = next((m for m in text_models if m['id'] == model_id), None)
                    if model and model not in most_used:
                        most_used.append(model)

            # 2. Newest - top 4 newest models (excluding those in most_used)
            sorted_models = sorted(text_models, key=lambda x: x['created'], reverse=True)
            newest_count = 0
            for model in sorted_models:
                if model not in most_used and newest_count < 4:
                    newest.append(model)
                    newest_count += 1

            # 3. Other - remaining models
            for model in sorted_models:
                if model not in most_used and model not in newest:
                    other.append(model)

            return jsonify({
                'success': True,
                'provider': provider,
                'most_used': most_used,
                'newest': newest,
                'other': other
            })
        else:
            return jsonify({
                'success': False,
                'error': f'API returned status {response.status_code}',
                'provider': provider
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
@limiter.exempt  # Health check should not be rate limited
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    print("=" * 80)
    print("AGENTIC HEMS API SERVER")
    print("=" * 80)
    print("Starting Flask API on http://localhost:5001")
    print("API Endpoints:")
    print("  POST /api/run/stream - Streaming orchestrator (20 req/min)")
    print("  POST /api/run        - Orchestrator (20 req/min)")
    print("  GET  /api/models     - Available LLM models (30 req/min)")
    print("  GET  /api/health     - Health check (no limit)")
    print("")
    print("Rate Limiting: 200/day, 50/hour (default)")
    print("Orchestrator: 20 requests/minute (prevents quota exhaustion)")
    print("=" * 80)
    app.run(host='0.0.0.0', port=5001, debug=True)
