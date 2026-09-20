"""Evaluation module: offline-reproducible retrieval / generation / agent benchmarks.

Run from the ``backend/`` directory:

    python -m eval.runner                     # offline, in-memory vectors
    python -m eval.runner --backend qdrant    # real Qdrant + real embeddings
"""

from __future__ import annotations

import os

# ``app.config`` builds Settings() at import time and openai_api_key is a
# required field. The offline evaluation never calls a real model, so a
# placeholder is enough - without this, ``python -m eval.runner`` would die on
# import for anyone who hasn't configured a key.
os.environ.setdefault("OPENAI_API_KEY", "offline-eval")
