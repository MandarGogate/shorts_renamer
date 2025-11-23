#!/bin/bash
# ShortsSync Web Server Startup Script

echo "========================================="
echo "ShortsSync Web Server"
echo "========================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -q -r requirements_web.txt

# Check for fpcalc
if ! command -v fpcalc &> /dev/null; then
    echo ""
    echo "⚠️  Warning: fpcalc not found"
    echo "Install with:"
    echo "  macOS: brew install chromaprint"
    echo "  Linux: sudo apt install libchromaprint-tools"
    echo ""
fi

# Start server
echo ""
echo "Starting ShortsSync Web Server..."
echo "Open your browser to: http://localhost:5000"
echo ""
python3 web_backend.py
