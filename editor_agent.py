# editor_agent.py - REVISED
# Instructions and data model updated for use with intelligent fact-checking

from agents import Agent
from pydantic import BaseModel, Field

INSTRUCTIONS = """You are a careful report editor. You will receive:
1. An original research report (markdown format)
2. Verified claims with confidence scores and citations

Your editing tasks:

FOR EACH CLAIM IN THE REPORT:
1. REMOVE or REPHRASE claims with confidence < 50:
   - If confidence 0-30: Remove entirely
   - If confidence 30-50: Heavily qualify or remove

2. ADD QUALIFIERS for claims with confidence 50-70:
   - Use phrases like: "According to sources...", "Some evidence suggests...", 
     "Reportedly...", "Studies indicate...", "One perspective is..."

3. ADD INLINE CITATIONS for verified claims (confidence > 70):
   - Insert citations directly after claims: [Source: X, Y, Z]
   - Use the citations provided in the verification data

4. MAINTAIN COHERENCE:
   - Ensure the report still flows naturally after edits
   - Don't leave orphaned sections
   - Adjust transitions as needed
   - Keep the overall structure intact

OUTPUT:
- The edited markdown report incorporating all changes
- A summary of edits made (what was removed, qualified, or cited)"""

class EditedReport(BaseModel):
    """Result of editing a report based on fact-checking"""
    edited_markdown: str = Field(
        description="The edited report in markdown format"
    )
    edit_summary: str = Field(
        description="Summary of changes made (claims removed, qualified, citations added)"
    )
    claims_removed_count: int = Field(
        description="Number of claims removed or significantly changed"
    )
    citations_added_count: int = Field(
        description="Number of inline citations added"
    )

editor_agent = Agent(
    name="Report Editor",
    instructions=INSTRUCTIONS,
    model="gpt-5-mini",
    output_type=EditedReport  # ← Changed from FinalReportData
)
