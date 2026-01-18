import asyncio
import json
import uuid
from collections.abc import Mapping

from agents import Runner, Usage, gen_trace_id, trace

from claim_extraction_agent import claim_extractor
from db import init_db
from config import (
    AGENT_MODEL_MAP,
    DEFAULT_NUM_SEARCHES,
    FACT_CHECK_CONFIDENCE_THRESHOLD,
    MODEL_COSTS,
    PLANNER_MODEL,
    TOOL_COSTS,
)
from editor_agent import editor_agent
from email_agent import email_agent
from fact_check_planner_agent import fact_check_planner
from session_title_agent import session_title_agent
from new_models import (
    EditedReport,
    ExtractedClaims,
    FactCheckingResult,
    FinalReportData,
    SessionUsage,
    VerifiedClaims,
    WebSearchItem,
    WebSearchPlan,
    WriterOutput,
)
from planner_agent import PlannerAgent
from qa_agent import is_quality_request, qa_agent
from search_agent import search_agent
from writer_agent import writer_agent

from usage_tracker import record_tool_call, set_session_usage


class ResearchManager:
    def __init__(self):
        self.report: FinalReportData | None = None
        self.search_results: list[str] = []
        self.last_query: str | None = None
        self.session_usage = SessionUsage()
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cost: float = 0.0
        self.current_session_id: uuid.UUID | None = None

    def _usage_snapshot(self) -> dict[str, object]:
        return self.session_usage.model_dump()

    def _cost_summary_snapshot(self) -> dict[str, float | int]:
        total_tool_calls = sum(self.session_usage.total_tool_calls.values())
        total_cost = self.calculate_total_cost()
        return {
            "total_input_tokens": self.session_usage.total_input_tokens,
            "total_output_tokens": self.session_usage.total_output_tokens,
            "total_tool_calls": total_tool_calls,
            "total_cost": total_cost,
        }

    def _normalize_json_payload(self, payload: object | None) -> dict:
        if payload is None:
            return {}
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            try:
                decoded = json.loads(payload)
            except json.JSONDecodeError:
                return {}
            return decoded if isinstance(decoded, dict) else {}
        if isinstance(payload, Mapping):
            return dict(payload)
        return {}

    async def _get_pool(self):
        return await init_db()

    async def _generate_session_header(
        self, initial_prompt: str, report_summary: str
    ) -> str:
        input_text = (
            f"INITIAL PROMPT:\n{initial_prompt}\n\nREPORT SUMMARY:\n{report_summary}"
        )
        result = await Runner.run(session_title_agent, input_text)
        self.update_usage_stats("session_title_agent", result.context_wrapper.usage)
        return result.final_output.title

    async def _update_session(
        self, header: str | None = None, report_markdown: str | None = None
    ) -> None:
        if self.current_session_id is None:
            return
        pool = await self._get_pool()
        usage_snapshot = self._usage_snapshot()
        cost_snapshot = self._cost_summary_snapshot()
        async with pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE sessions
                SET updated_at = NOW(),
                    last_activity_at = NOW(),
                    header = COALESCE($2, header),
                    report_markdown = COALESCE($3, report_markdown),
                    usage_jsonb = $4,
                    cost_summary_jsonb = $5
                WHERE id = $1
                """,
                self.current_session_id,
                header,
                report_markdown,
                json.dumps(usage_snapshot),
                json.dumps(cost_snapshot),
            )

    async def _insert_message(
        self,
        role: str,
        content: str,
        message_type: str,
        agent_name: str | None = None,
        usage: dict | None = None,
    ) -> None:
        if self.current_session_id is None:
            return
        pool = await self._get_pool()
        message_id = uuid.uuid4()
        usage_payload = json.dumps(usage) if isinstance(usage, dict) else None
        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO messages (
                    id, session_id, role, content, message_type, agent_name, usage_jsonb
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                message_id,
                self.current_session_id,
                role,
                content,
                message_type,
                agent_name,
                usage_payload,
            )
        await self._update_session()

    async def _create_session(self, initial_prompt: str) -> None:
        pool = await self._get_pool()
        session_id = uuid.uuid4()
        self.current_session_id = session_id
        usage_snapshot = self._usage_snapshot()
        cost_snapshot = self._cost_summary_snapshot()
        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO sessions (
                    id, header, initial_prompt, report_markdown, usage_jsonb, cost_summary_jsonb
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                session_id,
                None,
                initial_prompt,
                None,
                json.dumps(usage_snapshot),
                json.dumps(cost_snapshot),
            )
            await connection.execute(
                """
                INSERT INTO messages (
                    id, session_id, role, content, message_type, agent_name, usage_jsonb
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                uuid.uuid4(),
                session_id,
                "user",
                initial_prompt,
                "report",
                None,
                None,
            )

    def reset_session_state(self) -> None:
        self.report = None
        self.search_results = []
        self.last_query = None
        self.session_usage = SessionUsage()
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost = 0.0
        self.current_session_id = None

    def _format_cost_summary_from_snapshot(self, snapshot: object | None) -> str:
        snapshot_dict = self._normalize_json_payload(snapshot)
        if not snapshot_dict:
            return "### Session Cost Summary\n- No cost data available\n"
        return (
            "### Session Cost Summary\n"
            f"- Total input tokens: {snapshot_dict.get('total_input_tokens', 0)}\n"
            f"- Total output tokens: {snapshot_dict.get('total_output_tokens', 0)}\n"
            f"- Total tool calls: {snapshot_dict.get('total_tool_calls', 0)}\n"
            f"- Total running cost: ${snapshot_dict.get('total_cost', 0.0):.4f}\n"
        )

    async def list_sessions(self) -> list[tuple[str, str]]:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT id, header, initial_prompt
                FROM sessions
                ORDER BY last_activity_at DESC
                """
            )
        choices: list[tuple[str, str]] = []
        for row in rows:
            label = row["header"] or row["initial_prompt"] or "Untitled session"
            label = label.strip()
            if len(label) > 80:
                label = f"{label[:77]}..."
            choices.append((label, str(row["id"])))
        return choices

    async def load_session(
        self, session_id: str
    ) -> tuple[str, str, list[dict[str, str]], str]:
        pool = await self._get_pool()
        session_uuid = uuid.UUID(session_id)
        async with pool.acquire() as connection:
            session_row = await connection.fetchrow(
                """
                SELECT id, header, initial_prompt, report_markdown, usage_jsonb, cost_summary_jsonb
                FROM sessions
                WHERE id = $1
                """,
                session_uuid,
            )
            message_rows = await connection.fetch(
                """
                SELECT role, content
                FROM messages
                WHERE session_id = $1 AND message_type = 'chat'
                ORDER BY created_at
                """,
                session_uuid,
            )
        if session_row is None:
            return "", "", [], ""
        self.current_session_id = session_uuid
        self.last_query = session_row["initial_prompt"]
        usage_snapshot = self._normalize_json_payload(session_row["usage_jsonb"])
        cost_snapshot = self._normalize_json_payload(session_row["cost_summary_jsonb"])
        try:
            self.session_usage = SessionUsage.model_validate(usage_snapshot)
        except Exception:
            self.session_usage = SessionUsage()
        report_markdown = session_row["report_markdown"] or ""
        if report_markdown:
            self.report = FinalReportData(
                short_summary=session_row["header"] or "",
                markdown_report=report_markdown,
                follow_up_questions=[],
                verified_claims=VerifiedClaims(claims=[]),
                total_claims_checked=0,
                dubious_claims_count=0,
                was_edited=False,
            )
        else:
            self.report = None
        history: list[dict[str, str]] = []
        for row in message_rows:
            history.append(
                {
                    "role": row["role"],
                    "content": row["content"],
                }
            )
        cost_summary = self._format_cost_summary_from_snapshot(cost_snapshot)
        return report_markdown, cost_summary, history, self.last_query or ""

    async def edit_report(
        self, original_report: str, verified_claims: VerifiedClaims
    ) -> EditedReport:
        """Edit report based on fact-checking results"""

        # Prepare detailed input for editor
        claims_with_confidence = "\n\n".join(
            [
                f"CLAIM {i + 1}: {claim.claim}\n"
                f"Confidence: {claim.confidence_score}/100\n"
                f"Verification: {'VERIFIED' if claim.is_verified else 'UNVERIFIED'}\n"
                f"Supporting Citations: {', '.join(claim.supporting_citations)}\n"
                f"Contradictions: {', '.join(claim.contradicting_citations)}\n"
                f"Rationale: {claim.confidence_rationale}"
                for i, claim in enumerate(verified_claims.claims)
            ]
        )

        input_text = f"""ORIGINAL REPORT:
    {original_report}

    ---

    VERIFIED CLAIMS WITH CONFIDENCE SCORES:
    {claims_with_confidence}

    ---

    Edit the report according to the confidence scores and verification status of each claim.
    Follow the editing guidelines in your instructions."""

        print("Editing report based on fact-checking results...")
        result = await Runner.run(editor_agent, input_text)

        self.update_usage_stats("editor_agent", result.context_wrapper.usage)
        print("Report editing complete")

        return result.final_output_as(EditedReport)

    # research_manager.py - REVISED run() method
    # revisions: update flow to include intelligent fact-checking and editing of report
    async def run(self, query: str):
        """Run the deep research process, yielding status updates and final report"""
        self.last_query = query
        self.session_usage = SessionUsage()
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost = 0.0
        self.current_session_id = None
        set_session_usage(self.session_usage)
        await self._create_session(query)
        trace_id = gen_trace_id()
        with trace("Research trace", trace_id=trace_id):
            print(
                f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}"
            )
            yield f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}\n"

            # Step 1: Plan and execute searches
            print("Starting research...")
            yield "Planning searches...\n"
            search_plan = await self.plan_searches(query)

            yield "Executing searches...\n"
            search_results = await self.perform_searches(search_plan)
            self.search_results = search_results

            # Step 2: Generate initial report

            yield "Writing initial report...\n"
            writer_output = await self.write_report(query, search_results)

            # Step 3: Fact-check the report
            yield "Fact-checking report...\n"
            verified_claims = await self.fact_check_report(
                writer_output.markdown_report, search_results
            )

            # Step 4: Determine if editing is needed
            dubious_claims = [
                claim
                for claim in verified_claims.claims
                if claim.confidence_score < FACT_CHECK_CONFIDENCE_THRESHOLD
            ]

            if dubious_claims:
                yield f"Found {len(dubious_claims)} claims needing attention. Editing report...\n"

                # Edit the report
                edited = await self.edit_report(
                    writer_output.markdown_report, verified_claims
                )

                # Create final report with edited content
                final_report = FinalReportData(
                    short_summary=writer_output.short_summary,
                    markdown_report=edited.edited_markdown,  # ← Use edited version
                    follow_up_questions=writer_output.follow_up_questions,
                    verified_claims=verified_claims,
                    total_claims_checked=len(verified_claims.claims),
                    dubious_claims_count=len(dubious_claims),
                    was_edited=True,
                )

                yield f"Editing complete: {edited.edit_summary}\n"
            else:
                yield "All claims verified with high confidence. No editing needed.\n"

                # Create final report with original content
                final_report = FinalReportData.from_writer_and_verification(
                    writer_output=writer_output,
                    verified_claims=verified_claims,
                    was_edited=False,
                )

            # Step 5: Store and send
            self.report = final_report
            session_header = await self._generate_session_header(
                query, writer_output.short_summary
            )
            await self._insert_message(
                role="assistant",
                content=final_report.markdown_report,
                message_type="report",
                agent_name=(
                    "editor_agent" if final_report.was_edited else "writer_agent"
                ),
                usage=self._usage_snapshot(),
            )
            await self._update_session(
                header=session_header, report_markdown=final_report.markdown_report
            )

            yield "Sending email...\n"
            await self.send_email(final_report)

            yield "Research complete!\n"
            yield f"\n---\n## Final Report\n\n{final_report.markdown_report}"

    async def chat(self, message: str, history: list[tuple[str, str]]):
        """Run the chat Q & A process for the generated report"""
        if self.report is None:
            yield "No report available. Please run a research query first."
            return

        original_message = message
        if self.current_session_id is None:
            await self._create_session(self.last_query or "Unknown")
            if self.report is not None:
                await self._insert_message(
                    role="assistant",
                    content=self.report.markdown_report,
                    message_type="report",
                    agent_name="writer_agent",
                    usage=self._usage_snapshot(),
                )
                await self._update_session(report_markdown=self.report.markdown_report)

        await self._insert_message(
            role="user",
            content=original_message,
            message_type="chat",
        )
        set_session_usage(self.session_usage)
        trace_id = gen_trace_id()
        quality_requested = is_quality_request(message)
        search_context = (
            "\n".join(self.search_results)
            if self.search_results
            else "No search context available."
        )
        query_context = self.last_query or "Unknown"

        # Only include report if this is the first message in the conversation
        if not history or quality_requested:
            message = (
                f"##Question: {message}\n"
                f"##Report:\n{self.report.markdown_report}\n"
                f"##SearchContext:\n{search_context}\n"
                f"##OriginalQuery:\n{query_context}"
            )
            if history:
                message = f"{message}\n##Context:\n{history}"
        else:
            message = f"##Question: {message}\n##Context: {history}"
        with trace("Chat trace", trace_id=trace_id):
            print(
                f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}"
            )
            yield f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}"
            print("Starting chat...")
            result = await Runner.run(
                qa_agent,
                message,
            )
            self.update_usage_stats("qa_agent", result.context_wrapper.usage)
            await self._insert_message(
                role="assistant",
                content=result.final_output.answer,
                message_type="chat",
                agent_name="qa_agent",
                usage=self._usage_snapshot(),
            )
            yield result.final_output.answer

    def calculate_total_cost(self) -> float:
        total_cost = 0.0
        for agent_name, usage in self.session_usage.agents.items():
            model_name = AGENT_MODEL_MAP.get(agent_name)
            if model_name is None:
                continue
            model_cost = MODEL_COSTS.get(model_name, {})
            input_rate = model_cost.get("input", 0.0)
            output_rate = model_cost.get("output", 0.0)
            total_cost += (usage.input_tokens / 1_000_000) * input_rate
            total_cost += (usage.output_tokens / 1_000_000) * output_rate

        for tool_name, count in self.session_usage.total_tool_calls.items():
            total_cost += TOOL_COSTS.get(tool_name, 0.0) * count

        return total_cost

    def get_cost_summary(self) -> str:
        total_tool_calls = sum(self.session_usage.total_tool_calls.values())
        total_cost = self.calculate_total_cost()
        return (
            "### Session Cost Summary\n"
            f"- Total input tokens: {self.session_usage.total_input_tokens}\n"
            f"- Total output tokens: {self.session_usage.total_output_tokens}\n"
            f"- Total tool calls: {total_tool_calls}\n"
            f"- Total running cost: ${total_cost:.4f}\n"
        )

    def update_usage_stats(self, agent_name: str, usage: Usage) -> None:
        self.session_usage.add_agent_usage(
            agent_name, usage.input_tokens, usage.output_tokens
        )
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cost = self.calculate_total_cost()

    async def _extract_claims(self, report_text: str) -> ExtractedClaims:
        """Extract all claims from report in one pass"""
        result = await Runner.run(
            claim_extractor,
            f"Extract verifiable factual claims from this report:\n\n{report_text}",
        )
        self.update_usage_stats("claim_extractor", result.context_wrapper.usage)
        return result.final_output_as(ExtractedClaims)

    async def fact_check_report(
        self, report_text: str, search_context: list[str]
    ) -> VerifiedClaims:
        """Adaptive fact-checking with intelligent strategy selection"""

        # Step 1: Extract claims with rich metadata
        print("Extracting claims with metadata...")
        extracted_claims = await self._extract_claims(report_text)
        print(f"Found {len(extracted_claims.claims)} claims")

        # Step 2: Let planner agent orchestrate verification
        print("Planning verification strategy...")

        # Prepare input for planner
        claims_summary = "\n\n".join(
            [
                f"CLAIM {i + 1}:\n"
                f"Text: {claim.claim_text}\n"
                f"Importance: {claim.importance}\n"
                f"Controversy: {claim.controversy_level}\n"
                f"Type: {claim.claim_type}\n"
                f"Topic: {claim.semantic_topic}"
                for i, claim in enumerate(extracted_claims.claims)
            ]
        )

        input_text = f"""CLAIMS TO VERIFY:
            {claims_summary}

            BACKGROUND RESEARCH CONTEXT:
            {chr(10).join(search_context[:5])}

            Analyze these claims and execute appropriate verification strategies.
            Optimize for accuracy on important claims while being cost-efficient on trivial ones."""

        # Step 3: Planner agent executes verification
        print("Executing adaptive fact-checking...")
        result = await Runner.run(fact_check_planner, input_text)

        self.update_usage_stats("fact_check_planner", result.context_wrapper.usage)

        fact_check_result = result.final_output_as(FactCheckingResult)

        print("Fact-checking complete:")
        print(f"  - Skipped: {fact_check_result.skipped_count}")
        print(f"  - Quick: {fact_check_result.quick_count}")
        print(f"  - Thorough: {fact_check_result.thorough_count}")
        print(f"  - Red Team: {fact_check_result.red_team_count}")
        print(f"  - Estimated cost: ${fact_check_result.total_cost_estimate:.3f}")

        return VerifiedClaims(claims=fact_check_result.verified_claims)

    async def plan_searches(
        self,
        query: str,
        model: str = PLANNER_MODEL,
        num_searches: int = DEFAULT_NUM_SEARCHES,
    ) -> WebSearchPlan:
        """Plan the searches to perform for the query"""
        print("Planning searches...")
        planner_agent = PlannerAgent(model=model, num_searches=num_searches)
        result = await Runner.run(
            planner_agent,
            f"Query: {query}",
        )
        print(f"Will perform {len(result.final_output.searches)} searches")
        self.update_usage_stats("planner_agent", result.context_wrapper.usage)
        print(f"Total cost: {self.calculate_total_cost()}")
        return result.final_output_as(WebSearchPlan)

    async def perform_searches(self, search_plan: WebSearchPlan) -> list[str]:
        """Perform the searches to perform for the query"""
        print("Searching...")
        num_completed = 0
        tasks = [
            asyncio.create_task(self.search(item)) for item in search_plan.searches
        ]
        results = []
        for task in asyncio.as_completed(tasks):
            result = await task
            if result is not None:
                results.append(result)

            num_completed += 1
            print(f"Searching... {num_completed}/{len(tasks)} completed")

        print("Finished searching")

        print(f"Total cost: {self.calculate_total_cost()}")
        return results

    async def search(self, item: WebSearchItem) -> str | None:
        """Perform a search for the query"""
        input = f"Search term: {item.query}\nReason for searching: {item.reason}"
        try:
            result = await Runner.run(
                search_agent,
                input,
            )
            self.update_usage_stats("search_agent", result.context_wrapper.usage)
            record_tool_call("search_agent", "web_search")
            return str(result.final_output)
        except Exception:
            return None

    async def write_report(self, query: str, search_results: list[str]) -> WriterOutput:
        """Write the report for the query"""
        print("Thinking about report...")
        input = f"Original query: {query}\nSummarized search results: {search_results}"
        result = await Runner.run(
            writer_agent,
            input,
        )
        self.update_usage_stats("writer_agent", result.context_wrapper.usage)
        print("Finished writing report")
        print(f"Total cost: {self.calculate_total_cost()}")
        return result.final_output_as(WriterOutput)

    async def send_email(self, report: FinalReportData) -> None:
        print("Writing email...")
        result = await Runner.run(
            email_agent,
            report.markdown_report,
        )
        self.update_usage_stats("email_agent", result.context_wrapper.usage)
        print("Email sent")
        print(f"Total cost: {self.calculate_total_cost()}")
