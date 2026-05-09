#!/bin/bash

# AxiomAI API <> Claude Code CONFIG INTEGRATOR
# This script directly updates your ~/.claude/settings.json to use local Axiom API.

SETTINGS_FILE="$HOME/.claude/settings.json"
# Remove /v1 from the URL because Claude Code appends it automatically
# Using http://localhost:8000 ensures requests land at /v1/messages instead of /v1/v1/messages
API_URL="http://localhost:8000"

echo "🚀 Integrating AxiomAI API into Claude Code settings..."

if [ ! -f "$SETTINGS_FILE" ]; then
    echo "❌ Claude settings file not found at $SETTINGS_FILE"
    exit 1
fi

# Inform user about the mappings
echo "📝 Applying model mappings:"
echo "  Opus   -> anthropic/claude-opus-4.7"
echo "  Sonnet -> anthropic/claude-sonnet-4.6"
echo "  Haiku  -> openai/gpt-5.5"

# Backup existing settings
cp "$SETTINGS_FILE" "${SETTINGS_FILE}.bak"
echo "💾 Backup created at ${SETTINGS_FILE}.bak"

# Use python to safely update the JSON file
python3 - <<EOF
import json
import os

path = os.path.expanduser("$SETTINGS_FILE")
with open(path, 'r') as f:
    data = json.load(f)

# Ensure 'env' key exists
if 'env' not in data:
    data['env'] = {}

# Update environment variables for Claude Code
data['env']['ANTHROPIC_BASE_URL'] = "$API_URL"
# Axiom handles its own auth, but Claude Code might require a dummy token
data['env']['ANTHROPIC_AUTH_TOKEN'] = "axiom-local-token"

# Map the models as requested
data['env']['ANTHROPIC_DEFAULT_OPUS_MODEL'] = "anthropic/claude-opus-4.7"
data['env']['ANTHROPIC_DEFAULT_SONNET_MODEL'] = "anthropic/claude-sonnet-4.6"
data['env']['ANTHROPIC_DEFAULT_HAIKU_MODEL'] = "openai/gpt-5.5"

with open(path, 'w') as f:
    json.dump(data, f, indent=2)
EOF

if [ $? -eq 0 ]; then
    echo "✅ Success! ~/.claude/settings.json has been updated."
    echo "🛠️  Now Claude Code will use Axiom (localhost:8000) for all requests."
    echo "🔄 Make sure your Axiom API server is running (uvicorn main:app)."
else
    echo "❌ Failed to update settings."
    exit 1
fi
