#!/bin/bash

# AxiomAI API <> Claude Code Integration Script
# This script sets up Claude Code to use your local AxiomAI API wrapper.

API_URL="http://localhost:8000/v1"

echo "🚀 Configuring Claude Code to use local AxiomAI API..."

# Check if claude-code is installed
if ! command -v claude &> /dev/null
then
    echo "❌ Claude Code (claude) not found. Please install it first."
    exit 1
fi

echo "📝 Setting up model mappings..."
echo "------------------------------------------------"
echo "Opus   -> anthropic/claude-opus-4.7"
echo "Sonnet -> anthropic/claude-sonnet-4.6"
echo "Haiku  -> openai/gpt-5.5"
echo "------------------------------------------------"

# Configure Claude Code via environment variables or setting commands
# Note: Claude Code typically reads from CLAUDE_BASE_URL or via config set
# We'll use the 'claude config' command pattern if applicable, or exported envs.

# Set the base URL for the API
export CLAUDE_BASE_URL=$API_URL

# Launch Claude Code with specific local models mapped via Axiom
# We use aliases that Claude Code expects but point them to your Axiom IDs

echo "✨ Starting Claude Code with Axiom models..."
echo "Tip: You can change models inside Claude Code, and Axiom will maintain context!"

# Execute Claude Code. 
# We pass the custom base URL and recommended model mappings.
CLAUDE_BASE_URL=$API_URL \
CLAUDE_MODEL_OPUS="anthropic/claude-opus-4.7" \
CLAUDE_MODEL_SONNET="anthropic/claude-sonnet-4.6" \
CLAUDE_MODEL_HAIKU="openai/gpt-5.5" \
claude
