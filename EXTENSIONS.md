# Research Assistant Extensions

This document outlines potential extensions to enhance the deep research assistant using the OpenAI Agents SDK.

## 1. Citation & Fact-Checking Agent

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

### Overview
Evaluates research quality, identifies potential biases, and suggests improvements to research methodology.

### Implementation Plan
- **New Agent**: `quality_agent.py`
- **Output Model**: `QualityReport` with bias analysis and recommendations
- **Tools**: Source credibility checker, bias detection algorithms
- **Integration**: Run analysis after search completion, before final report
- **Key Functions**:
  - Analyze source diversity and credibility scores
  - Detect potential confirmation bias in search results
  - Identify missing perspectives or viewpoints
  - Generate quality confidence scores
  - Suggest additional research directions

### Files to Create/Modify
- `quality_agent.py` - New agent with bias analysis tools
- `research_manager.py` - Add quality check step
- Update report output to include quality metrics

## Implementation Priority

1. [x] **Start with Extension #4 (Interactive Q&A)** - Easiest to implement, immediate user value
2. [ ] **Extension #1 (Citation Agent)** - Builds on existing search functionality
3. [ ] **Extension #5 (Quality Analysis)** - Enhances research credibility
4. [ ] **Extension #3 (Memory System)** - Requires database setup
5. [ ] **Extension #2 (Export Formats)** - Most complex due to document generation

## General Implementation Notes

- Each agent follows the same pattern as existing agents (instructions + tools + output model)
- Use `function_tool` decorator for custom tools
- Integrate new agents into `ResearchManager` workflow
- Add UI components to `deep_research.py` as needed
- Consider adding configuration options for enabling/disabling extensions
- Maintain async patterns for all new functionality
