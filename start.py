# app/start.py

import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

uvicorn.run("api_server:app", host="0.0.0.0", port=8000)