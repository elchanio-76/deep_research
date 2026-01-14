# QUALITY_AGENT_PLAN.md

## Goal

Introduce a user-triggered “Research Quality & Bias Analysis” workflow that evaluates research quality and bias signals, returning a standalone analysis artifact (not embedded in the report). It should be invoked via QA interactions.

## Scope

- New agent: `quality_agent.py`
- New Pydantic model: `QualityReport`
- QA integration to trigger analysis via hybrid command/phrases
- Additional web searches allowed (max 3)

## Triggering the Analysis (QA Agent)

**Hybrid triggers:**

- Structured commands: `/quality`, `/bias`
- Trigger phrases: “run bias analysis”, “quality check”, “evaluate research quality”

**Behavior:**

- When triggered, QA agent calls `ResearchManager.run_quality_analysis(...)` and returns the `QualityReport` output in the required format.

## Output Model: `QualityReport`

**Pydantic fields:**

- `scores: dict[str, int]`
  - `source_diversity` (1–5)
  - `credibility_tiers` (1–5)
  - `recency` (1–5)
  - `author_expertise` (1–5)
- `meta_scores: dict[str, int]`
  - `geographic_balance` (1–5)
  - `political_balance` (1–5)
  - `stance_distribution` (1–5)
- `risk_flags: list[str]`
  - Short, actionable flags (e.g., “Most sources originate from a single organization”)
- `summary: str`
  - Narrative paragraph(s) describing key bias/quality insights
- `appendix_sources: list[str]`
  - Evaluated sources (URLs + short notes)
- `appendix_followups: list[str]`
  - Suggested follow-up research questions/searches

**Ordering in output:**

1. Scores
2. Risk flags
3. Narrative summary
4. Appendix (sources + follow-ups)

## Tooling & Search Limits

- Allow additional searches for credibility/author checks
- Define a constant max search count:
  - `QUALITY_AGENT_MAX_SEARCHES = 3`

## Quality Scoring Rubric (1–5 Scale)

### 1) Source Diversity

- **5:** Multiple independent outlets/orgs across domains (e.g., academic, gov, industry)
- **3:** Several sources but clustered around a single network/affiliation
- **1:** Primarily a single source or repeated amplifications

### 2) Credibility Tiers

- **5:** Strong presence of peer-reviewed, official, or academic sources
- **3:** Mix of reputable media + secondary sources
- **1:** Mostly low-credibility, promotional, or unverifiable sources

### 3) Recency

- **5:** Majority of sources are recent and relevant to topic’s update cycle
- **3:** Mix of recent and outdated sources
- **1:** Mostly old sources for time-sensitive claims

### 4) Author Expertise

- **5:** Authors are domain experts or institutions with clear credentials
- **3:** Mixed expertise; credentials not always clear
- **1:** Authors unclear, anonymous, or lacking domain expertise

## Meta-Scoring (Derived from Above)

### Geographic Balance

- Based on diversity/credibility/author data and regional origin indicators

### Political Balance

- Based on source diversity + known affiliation signals (if available)

### Stance Distribution

- Based on whether sources include competing perspectives

## Data Inputs to the Agent

- Final report text
- Search summaries used in report generation
- Optional list of URLs / citations from prior steps
- Up to 3 extra searches for source/author credibility checks

## QA Output Format

**Example response structure:**

- **Scores**
  - `source_diversity: 4`, `credibility_tiers: 3`, `recency: 5`, `author_expertise: 2`
  - `geographic_balance: 3`, `political_balance: 2`, `stance_distribution: 3`
- **Risk Flags**
  - “Most evidence traces back to two affiliated think tanks”
- **Summary**
  - Narrative overview
- **Appendix**
  - Sources evaluated (with notes)
  - Follow-up questions/searches

## Integration Points

- New `ResearchManager.run_quality_analysis(report, search_context)`
- QA agent calls this method only upon trigger
- No changes to report content

## Validation

- Run `ruff check .`
- Manual QA prompt: `/quality` after research completes
