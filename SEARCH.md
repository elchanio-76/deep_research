## Web Content Retrieval Tools

### 1. Basic Web Scraper Tool
```python
from agents import function_tool
import requests
from bs4 import BeautifulSoup
import asyncio
import aiohttp

@function_tool
async def fetch_web_content(url: str) -> str:
    """Fetch and extract main content from a web page"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                html = await response.text()
                
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'nav', 'footer', 'aside']):
            element.decompose()
            
        # Extract main content (prioritize article, main, or body)
        content = soup.find('article') or soup.find('main') or soup.find('body')
        return content.get_text(strip=True)[:5000]  # Limit to 5k chars
        
    except Exception as e:
        return f"Error fetching {url}: {str(e)}"
```

### 2. Enhanced Search Agent with Content Fetching
```python
class EnhancedSearchAgent(Agent):
    def __init__(self):
        super().__init__(
            name="EnhancedSearchAgent",
            instructions="""
            1. Search for the query using available search engines
            2. Select the 3-5 most relevant URLs from results
            3. Fetch full content from those URLs
            4. Summarize and synthesize the information
            """,
            tools=[
                search_web,  # Your chosen search provider
                fetch_web_content,
                batch_fetch_content
            ]
        )

@function_tool
async def batch_fetch_content(urls: list[str]) -> dict[str, str]:
    """Fetch content from multiple URLs concurrently"""
    tasks = [fetch_web_content(url) for url in urls[:5]]  # Limit to 5 URLs
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return {
        url: result if isinstance(result, str) else f"Error: {result}"
        for url, result in zip(urls, results)
    }
```

### 3. Smart URL Selection
```python
@function_tool
def select_best_urls(search_results: list[dict]) -> list[str]:
    """Select most promising URLs from search results"""
    scored_urls = []
    
    for result in search_results:
        score = 0
        url = result.get('url', '')
        title = result.get('title', '').lower()
        snippet = result.get('snippet', '').lower()
        
        # Prioritize credible sources
        if any(domain in url for domain in ['.edu', '.gov', '.org']):
            score += 3
        if any(domain in url for domain in ['wikipedia', 'reuters', 'bbc']):
            score += 2
            
        # Avoid low-value pages
        if any(term in url for term in ['forum', 'reddit', 'quora']):
            score -= 1
            
        scored_urls.append((url, score))
    
    # Return top 5 URLs by score
    return [url for url, _ in sorted(scored_urls, key=lambda x: x[1], reverse=True)[:5]]
```

### 4. Updated Cost-Effective Search with Content Fetching
```python
class ContentAwareSearchManager:
    async def search_with_content(self, query: str, max_pages: int = 3) -> str:
        # Step 1: Get search results (cheap)
        search_results = await self.cheap_search(query)  # DuckDuckGo/SerpAPI
        
        # Step 2: Select best URLs
        selected_urls = select_best_urls(search_results)
        
        # Step 3: Fetch content (free but time-consuming)
        content_results = await batch_fetch_content(selected_urls[:max_pages])
        
        # Step 4: Synthesize information
        full_content = "\n\n---\n\n".join([
            f"Source: {url}\nContent: {content}"
            for url, content in content_results.items()
            if "Error:" not in content
        ])
        
        return full_content[:10000]  # Limit total content
```

### 5. Required Dependencies
```python
# Add to requirements.txt
aiohttp>=3.8.0
beautifulsoup4>=4.11.0
lxml>=4.9.0
requests>=2.28.0
```

## Implementation Strategy

### Cost-Effective Approach:
1. Use free search APIs (DuckDuckGo) for URL discovery
2. Scrape content directly (free, just takes time)
3. Smart URL filtering to avoid low-quality sources
4. Concurrent fetching to minimize latency

### Updated Search Flow:
Query → Search API ($0.00-0.005) → Select URLs → Fetch Content (free) → Synthesize

## Agent-Based URL Selection

### 1. URL Evaluation Agent
```python
from pydantic import BaseModel, Field
from agents import Agent

class URLEvaluation(BaseModel):
    selected_urls: list[str] = Field(description="Top 3-5 URLs to fetch content from")
    reasoning: str = Field(description="Brief explanation of selection criteria used")

url_evaluator = Agent(
    name="URLEvaluator",
    instructions="""
    Evaluate search result URLs for credibility and relevance.
    
    Consider:
    - Source reputation (academic, government, established media, expert organizations)
    - Content relevance to the search query
    - Likely content depth and quality
    - Avoid: forums, social media, obvious spam/SEO sites
    
    Select the 3-5 most promising URLs for content extraction.
    """,
    model="gpt-4o-mini",
    output_type=URLEvaluation
)
```

### 2. Integrated Search with Smart Selection
```python
class SmartSearchAgent(Agent):
    def __init__(self):
        super().__init__(
            name="SmartSearchAgent", 
            instructions="""
            1. Search for the query
            2. Evaluate URLs for credibility and relevance
            3. Fetch content from selected URLs
            4. Synthesize information into coherent summary
            """,
            tools=[search_web, evaluate_urls, fetch_web_content],
            model="gpt-4o-mini"
        )

@function_tool
async def evaluate_urls(search_results: str, query: str) -> list[str]:
    """Let agent select best URLs from search results"""
    input_text = f"Query: {query}\n\nSearch Results:\n{search_results}"
    
    result = await Runner.run(url_evaluator, input_text)
    return result.final_output.selected_urls
```

### 3. Streamlined Search Flow
```python
async def intelligent_search(self, query: str) -> str:
    # Get search results
    raw_results = await self.search_api(query)
    
    # Agent selects best URLs
    selected_urls = await evaluate_urls(raw_results, query)
    
    # Fetch content from selected URLs
    content = await batch_fetch_content(selected_urls)
    
    return self.synthesize_content(content, query)
```

This approach:
- **Scales automatically** - agent learns from patterns rather than hardcoded rules
- **Context-aware** - considers query relevance, not just general reputation
- **Adaptable** - can handle new domains and changing web landscape
- **Minimal cost** - uses cheap gpt-4o-mini for URL evaluation

The agent will naturally learn to prefer .edu, .gov, established news sources, etc., while being flexible enough to recognize quality content from newer or 
specialized sources.
