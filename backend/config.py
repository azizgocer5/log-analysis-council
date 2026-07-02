"""Configuration for the UAV Log Analysis LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# API key (Gemini API)
OPENROUTER_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("OPENROUTER_API_KEY")

# Stable models with high daily limits (1500 requests/day free tier)
COUNCIL_MODEL = "gemini-flash-latest"
CHAIRMAN_MODEL = "gemini-flash-latest"

# Standard Gemini API completions endpoint
OPENROUTER_API_URL = "https://generativelanguage.googleapis.com/v1beta/chat/completions"

# Fallback models in case of transient errors
FALLBACK_MODELS = [
    "gemini-flash-lite-latest",
]

# Data directories
DATA_DIR = "data/conversations"
LOG_DIR = os.getenv("LOG_DIR", "../../data/log")
CACHE_DIR = "data/log_cache"
