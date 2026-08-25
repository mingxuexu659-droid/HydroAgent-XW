# -*- coding: utf-8 -*-
"""Optional local credentials with safe environment-variable fallbacks."""

import os

try:
    from .local_settings import *
except ImportError:
    AMAP_API_KEY = os.environ.get("AMAP_API_KEY", "")
    SENTINEL_HUB_CLIENT_ID = os.environ.get("SENTINEL_HUB_CLIENT_ID", "")
    SENTINEL_HUB_CLIENT_SECRET = os.environ.get("SENTINEL_HUB_CLIENT_SECRET", "")
    USGS_USERNAME = os.environ.get("USGS_USERNAME", "")
    USGS_TOKEN = os.environ.get("USGS_TOKEN", "")
    QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
    DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", QWEN_API_KEY)
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

