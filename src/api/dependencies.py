from fastapi import Request
import asyncpg

from src.core.research_manager import ResearchManager


def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


def get_research_manager(request: Request) -> ResearchManager:
    return request.app.state.research_manager
