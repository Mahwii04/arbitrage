#!/bin/bash
# Render Build Script for Arbitrage Scanner
# This script runs during the build phase on Render

set -e  # Exit on any error

echo "🔨 Starting build process..."

# Upgrade pip to latest version
echo "📦 Upgrading pip..."
pip install --upgrade pip

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Install production WSGI server
echo "🚀 Installing Gunicorn..."
pip install gunicorn

echo "✅ Build completed successfully!"
echo "🎯 Ready for deployment to Render"