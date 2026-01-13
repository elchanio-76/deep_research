from agents import Runner, trace, gen_trace_id, Usage
from search_agent import search_agent
from planner_agent import PlannerAgent, WebSearchItem, WebSearchPlan
from writer_agent import writer_agent, WriterOutput
from email_agent import email_agent
from qa_agent import qa_agent
from editor_agent import editor_agent, EditedReport
import asyncio
from new_models import FinalReportData, VerifiedClaims
from fact_check_planner_agent import fact_check_planner, FactCheckingResult
from claim_extraction_agent import claim_extractor, ExtractedClaims
    

class ResearchManager:
    def __init__(self):
        self.report: FinalReportData | None = None
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cost: float = 0.0

    
    async def edit_report(
        self, 
        original_report: str, 
        verified_claims: VerifiedClaims
    ) -> EditedReport:
        """Edit report based on fact-checking results"""
        
        # Prepare detailed input for editor
        claims_with_confidence = "\n\n".join([
            f"CLAIM {i+1}: {claim.claim}\n"
            f"Confidence: {claim.confidence_score}/100\n"
            f"Verification: {'VERIFIED' if claim.is_verified else 'UNVERIFIED'}\n"
            f"Supporting Citations: {', '.join(claim.supporting_citations)}\n"
            f"Contradictions: {', '.join(claim.contradicting_citations)}\n"
            f"Rationale: {claim.confidence_rationale}"
            for i, claim in enumerate(verified_claims.claims)
        ])
        
        input_text = f"""ORIGINAL REPORT:
    {original_report}

    ---

    VERIFIED CLAIMS WITH CONFIDENCE SCORES:
    {claims_with_confidence}

    ---

    Edit the report according to the confidence scores and verification status of each claim.
    Follow the editing guidelines in your instructions."""
        
        print("Editing report based on fact-checking results...")
        result = await Runner.run(
            editor_agent,
            input_text
        )
        
        self.update_usage_stats(result.context_wrapper.usage)
        print("Report editing complete")
        
        return result.final_output_as(EditedReport)


    # research_manager.py - REVISED run() method
    # revisions: update flow to include intelligent fact-checking and editing of report
    async def run(self, query: str):
        """Run the deep research process, yielding status updates and final report"""
        trace_id = gen_trace_id()
        with trace("Research trace", trace_id=trace_id):
            print(f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}")
            yield f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}\n"
            
            # Step 1: Plan and execute searches
            print("Starting research...")
            yield "Planning searches...\n"
            search_plan = await self.plan_searches(query, model="gpt-4o-mini", num_searches=5)
            
            yield "Executing searches...\n"
            search_results = await self.perform_searches(search_plan)
            
            # Step 2: Generate initial report
            yield "Writing initial report...\n"
            writer_output = await self.write_report(query, search_results)
            
            # Step 3: Fact-check the report
            yield "Fact-checking report...\n"
            verified_claims = await self.fact_check_report(
                writer_output.markdown_report, 
                search_results
            )
            
            # Step 4: Determine if editing is needed
            dubious_claims = [
                claim for claim in verified_claims.claims 
                if claim.confidence_score < 70
            ]
            
            if dubious_claims:
                yield f"Found {len(dubious_claims)} claims needing attention. Editing report...\n"
                
                # Edit the report
                edited = await self.edit_report(
                    writer_output.markdown_report,
                    verified_claims
                )
                
                # Create final report with edited content
                final_report = FinalReportData(
                    short_summary=writer_output.short_summary,
                    markdown_report=edited.edited_markdown,  # ← Use edited version
                    follow_up_questions=writer_output.follow_up_questions,
                    verified_claims=verified_claims,
                    total_claims_checked=len(verified_claims.claims),
                    dubious_claims_count=len(dubious_claims),
                    was_edited=True
                )
                
                yield f"Editing complete: {edited.edit_summary}\n"
            else:
                yield "All claims verified with high confidence. No editing needed.\n"
                
                # Create final report with original content
                final_report = FinalReportData.from_writer_and_verification(
                    writer_output=writer_output,
                    verified_claims=verified_claims,
                    was_edited=False
                )
            
            # Step 5: Store and send
            self.report = final_report
            
            yield "Sending email...\n"
            await self.send_email(final_report)
            
            yield "Research complete!\n"
            yield f"\n---\n## Final Report\n\n{final_report.markdown_report}"

           
    async def chat(self, message: str, history: list[tuple[str, str]]):
        """ Run the chat Q & A process for the generated report """
        if self.report is None:
            yield "No report available. Please run a research query first."
            return
        
        trace_id = gen_trace_id()
        # Only include report if this is the first message in the conversation
        if not history:
            message = f"##Question: {message}\n##Report:\n{self.report.markdown_report}"
        else:
            message = f"##Question: {message}\n##Context: {history}"
        with trace("Chat trace", trace_id=trace_id):
            print(f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}")
            yield f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}"
            print("Starting chat...")
            result = await Runner.run(
                qa_agent,
                message,
            )
            yield result.final_output.answer

    def update_usage_stats(self, usage:Usage)->None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        input_token_cost = 0.15/1000000
        output_token_cost = 0.60/1000000
        self.cost += usage.input_tokens*input_token_cost + usage.output_tokens*output_token_cost
    
    async def _extract_claims(self, report_text: str) -> ExtractedClaims:
        """Extract all claims from report in one pass"""
        result = await Runner.run(
            claim_extractor,
            f"Extract verifiable factual claims from this report:\n\n{report_text}"
        )
        self.update_usage_stats(result.context_wrapper.usage)
        return result.final_output_as(ExtractedClaims)

    async def fact_check_report(
        self,
        report_text: str,
        search_context: list[str]
    ) -> VerifiedClaims:
        """Adaptive fact-checking with intelligent strategy selection"""
        
        # Step 1: Extract claims with rich metadata
        print("Extracting claims with metadata...")
        extracted_claims = await self._extract_claims(report_text)
        print(f"Found {len(extracted_claims.claims)} claims")
        
        # Step 2: Let planner agent orchestrate verification
        print("Planning verification strategy...")
        
        # Prepare input for planner
        claims_summary = "\n\n".join([
            f"CLAIM {i+1}:\n"
            f"Text: {claim.claim_text}\n"
            f"Importance: {claim.importance}\n"
            f"Controversy: {claim.controversy_level}\n"
            f"Type: {claim.claim_type}\n"
            f"Topic: {claim.semantic_topic}"
            for i, claim in enumerate(extracted_claims.claims)
        ])
        
        input_text = f"""CLAIMS TO VERIFY:
            {claims_summary}

            BACKGROUND RESEARCH CONTEXT:
            {chr(10).join(search_context[:5])}

            Analyze these claims and execute appropriate verification strategies.
            Optimize for accuracy on important claims while being cost-efficient on trivial ones."""
        
        # Step 3: Planner agent executes verification
        print("Executing adaptive fact-checking...")
        result = await Runner.run(
            fact_check_planner,
            input_text
        )
        
        self.update_usage_stats(result.context_wrapper.usage)
        
        fact_check_result = result.final_output_as(FactCheckingResult)
        
        print("Fact-checking complete:")
        print(f"  - Skipped: {fact_check_result.skipped_count}")
        print(f"  - Quick: {fact_check_result.quick_count}")
        print(f"  - Thorough: {fact_check_result.thorough_count}")
        print(f"  - Red Team: {fact_check_result.red_team_count}")
        print(f"  - Estimated cost: ${fact_check_result.total_cost_estimate:.3f}")
        
        return VerifiedClaims(claims=fact_check_result.verified_claims)

    
    async def plan_searches(self, query: str, model:str="gpt-4o-mini", num_searches: int = 5) -> WebSearchPlan:
        """ Plan the searches to perform for the query """
        print("Planning searches...")
        planner_agent = PlannerAgent(model=model, num_searches=num_searches)
        result = await Runner.run(
            planner_agent,
            f"Query: {query}",
        )
        print(f"Will perform {len(result.final_output.searches)} searches")
        self.update_usage_stats(result.context_wrapper.usage)
        print(f"Total cost: {self.cost}")
        return result.final_output_as(WebSearchPlan)

    async def perform_searches(self, search_plan: WebSearchPlan) -> list[str]:
        """ Perform the searches to perform for the query """
        print("Searching...")
        num_completed = 0
        tasks = [asyncio.create_task(self.search(item)) for item in search_plan.searches]
        results = []
        for task in asyncio.as_completed(tasks):
            result = await task
            if result is not None:
                results.append(result)
                
            num_completed += 1
            print(f"Searching... {num_completed}/{len(tasks)} completed")

        print("Finished searching")
        
        print(f"Total cost: {self.cost}")
        return results

    async def search(self, item: WebSearchItem) -> str | None:
        """ Perform a search for the query """
        input = f"Search term: {item.query}\nReason for searching: {item.reason}"
        try:
            result = await Runner.run(
                search_agent,
                input,
            )
            self.update_usage_stats(result.context_wrapper.usage)
            # Add the search tool cost to the total cost
            # TODO: Find out if there's a more elegant way to do this
            self.cost += 25/1000
            return str(result.final_output)
        except Exception:
            return None

    async def write_report(self, query: str, search_results: list[str]) -> WriterOutput:
        """ Write the report for the query """
        print("Thinking about report...")
        input = f"Original query: {query}\nSummarized search results: {search_results}"
        result = await Runner.run(
            writer_agent,
            input,
        )
        self.update_usage_stats(result.context_wrapper.usage)
        print("Finished writing report")
        print(f"Total cost: {self.cost}")
        return result.final_output_as(WriterOutput)
    
    async def send_email(self, report: FinalReportData) -> None:
        print("Writing email...")
        result = await Runner.run(
            email_agent,
            report.markdown_report,
        )
        self.update_usage_stats(result.context_wrapper.usage)
        print("Email sent")
        print(f"Total cost: {self.cost}")
        return report