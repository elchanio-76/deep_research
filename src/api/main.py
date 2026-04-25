from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from src.api.chat import router as chat_router
from src.api.research import router as research_router
from src.api.sessions import router as sessions_router
from src.core.research_manager import ResearchManager
from src.db.pool import close_pool, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(override=True)
    pool = await init_db()
    app.state.pool = pool
    app.state.research_manager = ResearchManager(pool=pool)
    yield
    await close_pool()


app = FastAPI(title="Deep Research API", lifespan=lifespan)
app.include_router(research_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
