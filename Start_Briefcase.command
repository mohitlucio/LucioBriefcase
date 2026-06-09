#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Lucio Briefcase — Double-click to launch
#  Opens the web dashboard in your browser.
#  Close this Terminal window to stop the server.
# ═══════════════════════════════════════════════════════════════
cd "$(dirname "$0")"
echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   LUCIO AI BRIEFCASE — Starting server...   ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""
echo "  Dashboard will open at http://localhost:8765"
echo "  Close this window to stop."
echo ""

# Start server in background, wait for it, then open browser
python3 backend/server.py &
SERVER_PID=$!

# Wait for server to be ready
sleep 3
open "http://localhost:8765"

# Keep this window alive — closing it kills the server
wait $SERVER_PID
