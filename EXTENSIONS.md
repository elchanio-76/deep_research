# Research Assistant Extensions

This document outlines potential extensions to enhance the deep research assistant using the OpenAI Agents SDK.

## 1. Citation & Fact-Checking Agent

*Implemented, multiple tools with adaptive strategies and intelligent scoring*  
*model below is obsolete, check README.md for actual implementation details*

### Overview

Validates claims in generated reports by cross-referencing sources and adds proper academic citations.

### Implementation Plan

- **New Agent**: `citation_agent.py`
- **Output Model**: `CitationData` with verified claims, citations, and confidence scores
- **Tools**: Enhanced web search for fact verification
- **Integration**: Add step in `ResearchManager.write_report()` after initial report generation
- **Key Functions**:
  - Extract factual claims from report text
  - Search for corroborating/contradicting sources
  - Generate citation format (APA, MLA, etc.)
  - Flag unverified or disputed claims

### Files to Create/Modify

- `citation_agent.py` - New agent implementation
- `research_manager.py` - Add citation verification step
- Update `ReportData` model to include citations

## 2. Multi-Format Export Agent

### Overview

Converts research reports into various professional formats (PDF, PowerPoint, Word) with appropriate styling.

### Implementation Plan

- **New Agent**: `export_agent.py`
- **Output Model**: `ExportData` with format type and file paths
- **Tools**: Document generation functions (PDF, DOCX, PPTX libraries)
- **Integration**: Add export options to Gradio UI
- **Key Functions**:
  - Parse markdown report structure
  - Generate executive summary slides
  - Create formatted documents with headers/footers
  - Add charts/visualizations where appropriate

### Files to Create/Modify

- `export_agent.py` - New agent with document generation tools
- `deep_research.py` - Add export buttons to UI
- `requirements.txt` - Add document libraries (reportlab, python-docx, python-pptx)

## 3. Research Memory & Knowledge Base Agent

### Overview

Maintains persistent storage of research findings and identifies connections between topics.

### Implementation Plan

- **New Agent**: `memory_agent.py`
- **Output Model**: `MemoryData` with stored research and connections
- **Tools**: Vector database operations (ChromaDB or similar)
- **Integration**: Query memory before starting new research, store results after completion
- **Key Functions**:
  - Embed and store research summaries
  - Search for related past research
  - Identify topic connections and patterns
  - Suggest follow-up research based on history

### Files to Create/Modify

- `memory_agent.py` - New agent with vector DB tools
- `research_manager.py` - Add memory check/store steps
- Database setup for persistent storage

## 4. Interactive Q&A Agent

*Implemented*

### Overview

Provides conversational interface for follow-up questions about completed research reports.

### Implementation Plan

- **New Agent**: `qa_agent.py`
- **Output Model**: `QAResponse` with answers and source references
- **Tools**: Report context search, targeted web search
- **Integration**: Add chat interface to Gradio UI below main report
- **Key Functions**:
  - Parse user questions about the report
  - Search within report content for relevant sections
  - Perform mini-searches for additional details
  - Maintain conversation context

### Files to Create/Modify

- `qa_agent.py` - New conversational agent
- `deep_research.py` - Add chat interface component
- `research_manager.py` - Add Q&A session management

## 5. Research Quality & Bias Analysis Agent

*Implemented (user-triggered via Q&A)*

### Overview

Evaluates research quality, identifies potential biases, and suggests improvements to research methodology.

### Implementation Plan

- **New Agent**: `quality_agent.py`
- **Output Model**: `QualityReport` with bias analysis and recommendations
- **Tools**: Targeted web searches (max 3) for credibility/recency/author checks
- **Integration**: Run on-demand via Q&A triggers (`/quality`, `/bias`, or phrases like "run bias analysis")
- **Key Functions**:
  - Analyze source diversity and credibility tiers
  - Score recency and author expertise
  - Derive geographic/political/stance meta-scores
  - Flag risks and suggest follow-up research questions

### Files to Create/Modify

- `quality_agent.py` - Quality and bias analysis agent
- `qa_agent.py` - Triggers and tool integration
- `research_manager.py` - Provide report/query/search context for Q&A
- `README.md` - Usage example for `/quality`

## 6. Advanced Search Planning & Optimization

### Overview

Implements progressive search refinement and intelligent search strategy to maximize information quality within budget constraints.

### Implementation Plan

- **New Components**: `AdaptiveSearchPlanner`, `SearchQualityScorer`, `OutlinePlannerAgent`
- **Output Models**: `ReportOutline`, `SearchResult` with quality metrics, `SearchCluster`
- **Tools**: Semantic clustering, source diversity tracking, real-time search optimization
- **Integration**: Replace current single-phase search planning in `ResearchManager`
- **Key Functions**:
  - Multi-phase search strategy (initial → deep-dive → gap-filling)
  - Search quality scoring based on relevance, credibility, recency
  - Outline-first approach with evidence requirements identification
  - Dynamic search expansion based on initial findings
  - Source diversity requirements and tracking

### Files to Create/Modify

- `adaptive_search_planner.py` - New multi-phase search orchestrator
- `search_quality_scorer.py` - Search result evaluation and ranking
- `outline_planner_agent.py` - Report structure planning before writing
- `planner_agent.py` - Enhance with clustering and prioritization
- `research_manager.py` - Update search workflow to use progressive refinement

## 7. Cost-Effective Search Alternatives

### Overview

Reduces search costs by 50-80% through intelligent search routing and alternative search providers while maintaining quality.

### Implementation Plan

- **New Components**: `HybridSearchManager`, `SearchCache`, `CostEffectiveSearchTool`
- **Output Models**: Enhanced search results with cost tracking
- **Tools**: SerpAPI, Bing Search API, DuckDuckGo integration, search result caching
- **Integration**: Replace OpenAI WebSearch tool with intelligent routing system
- **Key Functions**:
  - Smart search routing based on query importance and remaining budget
  - Search result caching to avoid duplicate queries
  - Batch search optimization for related queries
  - Cost tracking and budget management
  - Fallback search providers for different priority levels

### Files to Create/Modify

- `hybrid_search_manager.py` - Multi-provider search routing
- `search_cache.py` - Query caching and deduplication
- `cost_effective_search_tools.py` - Alternative search provider integrations
- `search_agent.py` - Update to use hybrid search manager
- `research_manager.py` - Add cost tracking and budget management
- `requirements.txt` - Add serpapi, duckduckgo-search dependencies

## Implementation Priority

1. [x] **Start with Extension #4 (Interactive Q&A)** - Easiest to implement, immediate user value
2. [x] **Extension #1 (Citation Agent)** - Builds on existing search functionality
3. [x] **Extension #5 (Quality Analysis)** - Enhances research credibility
4. [ ] **Extension #7 (Cost-Effective Search)** - High impact cost savings, moderate effort
5. [ ] **Extension #6 (Advanced Search Planning)** - Enhances search quality and efficiency
6. [ ] **Extension #3 (Memory System)** - Requires database setup
7. [ ] **Extension #2 (Export Formats)** - Most complex due to document generation

## General Implementation Notes

- Each agent follows the same pattern as existing agents (instructions + tools + output model)
- Use `function_tool` decorator for custom tools
- Integrate new agents into `ResearchManager` workflow
- Add UI components to `deep_research.py` as needed
- Consider adding configuration options for enabling/disabling extensions
- Maintain async patterns for all new functionality
