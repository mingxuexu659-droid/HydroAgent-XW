"""Optional local service credentials.

Copy this file to ``local_settings.py`` only if a feature needs one of these
services. Environment variables with the same names are preferred for CI and
deployment. Never commit the copied file or any real credential.
"""

import os

AMAP_API_KEY = os.environ.get("AMAP_API_KEY", "")
SENTINEL_HUB_CLIENT_ID = os.environ.get("SENTINEL_HUB_CLIENT_ID", "")
SENTINEL_HUB_CLIENT_SECRET = os.environ.get("SENTINEL_HUB_CLIENT_SECRET", "")
USGS_USERNAME = os.environ.get("USGS_USERNAME", "")
USGS_TOKEN = os.environ.get("USGS_TOKEN", "")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", QWEN_API_KEY)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

QWEN_API_CONCURRENT_WORKERS = 10
OPENAI_API_CONCURRENT_WORKERS = 5
