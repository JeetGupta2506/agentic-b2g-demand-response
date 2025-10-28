#!/bin/bash

# Startup script for Agentic AI HEMS Dashboard

echo "=========================================="
echo "  Starting Agentic AI HEMS Dashboard"
echo "=========================================="
echo ""

# Check if virtual environment is activated (optional but recommended)
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "⚠️  Note: No virtual environment detected."
    echo "   Consider activating your venv first:"
    echo "   source venv/bin/activate"
    echo ""
fi

# Check dependencies
if ! python3 -c "import flask" 2>/dev/null; then
    echo "❌ Flask not found. Installing dependencies..."
    pip install -r requirements-api.txt
fi

# Start Flask API in background
echo "Starting Flask API on port 5000..."
python3 api.py &
API_PID=$!

# Wait a moment for API to start
sleep 2

# Start HTTP server for dashboard
echo "Starting Dashboard on port 8000..."
python3 -m http.server 8000 &
HTTP_PID=$!

echo ""
echo "=========================================="
echo "  ✅ Dashboard ready!"
echo "=========================================="
echo ""
echo "  📊 Dashboard: http://localhost:8000/dashboard.html"
echo "  🔌 API:       http://localhost:5000"
echo ""
echo "  Press Ctrl+C to stop all servers"
echo ""

# Handle Ctrl+C gracefully
trap "echo ''; echo 'Stopping servers...'; kill $API_PID $HTTP_PID 2>/dev/null; exit" INT

# Wait for processes
wait
