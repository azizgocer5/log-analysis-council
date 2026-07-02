"""Configuration for the UAV Log Analysis LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# API key (Gemini API)
OPENROUTER_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("OPENROUTER_API_KEY")

# Anthropic API key (Claude)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

# Stable models with high daily limits (1500 requests/day free tier)
COUNCIL_MODEL = "gemini-flash-latest"
CHAIRMAN_MODEL = "gemini-flash-latest"

# Claude model identifiers
CLAUDE_MODELS = {
    "claude-sonnet": "claude-3-5-sonnet-latest",
    "claude-haiku": "claude-3-5-haiku-latest",
    "claude-opus": "claude-3-opus-20240229",
}

# Standard Gemini API completions endpoint
OPENROUTER_API_URL = "https://generativelanguage.googleapis.com/v1beta/chat/completions"

# Fallback models in case of transient errors
FALLBACK_MODELS = [
    "gemini-flash-lite-latest",
]

# Data directories
DATA_DIR = "data/conversations"
LOG_DIR = os.getenv("LOG_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/log"))
CACHE_DIR = "data/log_cache"
