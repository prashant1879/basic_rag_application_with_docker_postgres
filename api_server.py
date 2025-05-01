import sys
import asyncio
import os

# ✅ Ensure event loop compatibility for Windows before anything else
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from logger import logger
from dotenv import load_dotenv
from api_tools import get_vector_store, invoke_model, init_chatbot
from pydantic import BaseModel
from fastapi import FastAPI
from contextlib import asynccontextmanager

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing chatbot service and vector store...")
    await init_chatbot()
    await get_vector_store()
    logger.info("Initialization done.")
    yield

# Initialize the FastAPI app
app = FastAPI(lifespan=lifespan)

class ChatRequest(BaseModel):
    phone_number: str = None
    question: str = None

@app.post("/chat/start")
async def start_chat(request: ChatRequest):
    phone_number = request.phone_number
    content = request.question
    try:
        message = await invoke_model(content, phone_number)
        return {"phone_number": phone_number, "message": message}
    except Exception as e:
        logger.exception("Exception at /chat/start API")
        return {"phone_number": phone_number, "message": "An error occurred."}
