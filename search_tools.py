# SerpAPI (Google results) - $0.001-0.005 per search
#from serpapi import GoogleSearch

# Brave Search API - $0.00 - $0.005 per search
import httpx
import os
from dotenv import load_dotenv

# DuckDuckGo (completely free)
from duckduckgo_search import DDGS

from pydantic import BaseModel, Field
from agents import Agent, function_tool

class EffectiveSearchTool:
    def __init__(self, provider="serpapi"):
        self.provider = provider
        self.cost_per_search = {"serpapi": 0.005, "brave": 0.0, "ddg": 0.0}

    
# Create Brave tool
def brave_search(query: str, count:int = 10) -> str:
    """Search the web using Brave Search API.
    
    Args:
        query: The search query
        count: Number of results to return
    """
    
    brave_api_key = os.getenv("BRAVE_API_KEY")
   
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": brave_api_key
    }
    params = {"q": query, "count": count}
    
    response = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers=headers,
        params=params,
        timeout=30.0
    )
    response.raise_for_status()
    
    results = response.json()
    # Return formatted results
    output = []
    for result in results.get("web", {}).get("results", []):
        output.append(f"Title: {result.get('title')}\nURL: {result.get('url')}\nDescription: {result.get('description')}\n")
    
    return "\n".join(output)

# Create DDG tool
def ddg_search(query: str, count:int = 10) -> str:
    """Search the web using Duck Duck Go search API
    
    Args:
        query: The search query
        count: Number of results to return
    """

    results = DDGS(timeout=30).text(query, max_results=count)
    
    output = []
    for result in results:
        output.append(f"Title: {result['title']}\nURL: {result['href']}\nDescription: {result['body']}\n")

    return "\n".join(output)

if __name__ == "__main__":
    load_dotenv(override=True)
    print(ddg_search("Gaza Blockade"))
