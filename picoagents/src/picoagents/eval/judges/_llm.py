"""
LLM-based evaluation judge.

This module provides an evaluation judge that uses an LLM to score trajectories.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ..._cancellation_token import CancellationToken
from ...llm import BaseChatCompletionClient
from ...messages import SystemMessage, UserMessage
from ...types import EvalScore, RunTrajectory
from ._base import BaseEvalJudge


class CriterionScore(BaseModel):
    """Score for a single evaluation criterion."""

    name: str = Field(description="Criterion name (e.g. 'completeness')")
    score: float = Field(description="Score from 0 to 10")
    reasoning: str = Field(description="Brief reasoning for this score")


class JudgeResponse(BaseModel):
    """Structured judge evaluation response."""

    scores: list[CriterionScore] = Field(
        description="One score entry per evaluation criterion"
    )


class LLMEvalJudge(BaseEvalJudge):
    """LLM-based evaluation judge that uses another model to score trajectories."""

    def __init__(
        self,
        client: BaseChatCompletionClient,
        name: Optional[str] = None,
        default_criteria: Optional[List[str]] = None,
        answer_strategy: str = "last_non_empty",
        custom_instructions: Optional[str] = None,
    ):
        """Initialize the LLM judge.

        Args:
            client: LLM client to use for scoring
            name: Optional custom name (defaults to model name)
            default_criteria: Default evaluation criteria if none specified
            answer_strategy: How to extract answer from trajectory
            custom_instructions: Optional additional instructions for the judge
        """
        super().__init__(
            name or f"LLM-{getattr(client, 'model', 'Judge')}", answer_strategy
        )
        self.client = client
        self.default_criteria = default_criteria or [
            "accuracy",
            "completeness",
            "helpfulness",
        ]
        self.custom_instructions = custom_instructions

    async def score(
        self,
        trajectory: RunTrajectory,
        criteria: Optional[List[str]] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> EvalScore:
        """Score an evaluation trajectory using LLM with structured output."""
        eval_criteria = criteria or trajectory.task.eval_criteria or self.default_criteria
        rubric = trajectory.task.rubric

        try:
            system_prompt = self._build_system_prompt(eval_criteria, rubric)
            user_prompt = self._build_user_prompt(trajectory)

            messages = [
                SystemMessage(content=system_prompt, source="system"),
                UserMessage(content=user_prompt, source="user"),
            ]

            result = await self.client.create(
                messages, output_format=JudgeResponse
            )

            # Extract from structured output (guaranteed valid by API)
            if result.structured_output:
                judge_resp: JudgeResponse = result.structured_output
                dimensions = {s.name: s.score for s in judge_resp.scores}
                reasoning = {s.name: s.reasoning for s in judge_resp.scores}
            else:
                # Fallback: parse from content (for clients without
                # structured output support)
                import json
                import re

                text = (result.message.content or "").strip()
                match = re.search(r"\{.*\}", text, re.DOTALL)
                parsed = json.loads(match.group(0) if match else text)
                dimensions = parsed.get("dimensions", {})
                reasoning = parsed.get("reasoning", {})

            # Fill missing criteria with defaults
            for criterion in eval_criteria:
                dimensions.setdefault(criterion, 5.0)
                reasoning.setdefault(criterion, "No reasoning provided")

            dim_scores = list(dimensions.values())
            overall = sum(dim_scores) / len(dim_scores) if dim_scores else 0.0

            return EvalScore(
                overall=overall,
                dimensions=dimensions,
                reasoning=reasoning,
                trajectory=trajectory,
                metadata={
                    "judge_name": self.name,
                    "model": result.model,
                    "criteria_used": eval_criteria,
                    "raw_response": result.message.content,
                    "judge_usage": result.usage,  # tokens/cost of the judge call itself
                },
            )

        except Exception as e:
            return EvalScore(
                overall=5.0,
                dimensions={dim: 5.0 for dim in eval_criteria},
                reasoning={dim: f"Judge error: {str(e)}" for dim in eval_criteria},
                trajectory=trajectory,
                metadata={
                    "judge_name": self.name,
                    "error": str(e),
                    "criteria_used": eval_criteria,
                },
            )

    def _build_system_prompt(self, criteria: List[str], rubric: Optional[Dict[str, str]] = None) -> str:
        """Build the system prompt for the evaluation LLM."""
        default_descriptions = {
            "accuracy": "How factually correct and truthful is the response?",
            "completeness": "How thoroughly does the response address the task?",
            "helpfulness": "How useful and actionable is the response?",
            "clarity": "How clear and well-structured is the response?",
            "creativity": "How creative and original is the response?",
            "safety": "How safe and appropriate is the response?",
        }

        criteria_details = []
        for criterion in criteria:
            if rubric and criterion in rubric:
                description = rubric[criterion]
            else:
                description = default_descriptions.get(
                    criterion, f"Quality of {criterion}"
                )
            criteria_details.append(f"- {criterion}: {description}")

        base_prompt = f"""You are an expert evaluation judge. Your task is to score AI agent conversations based on specific criteria.

Evaluation Criteria (each scored 0-10):
{chr(10).join(criteria_details)}

Instructions:
1. Analyze the task, expected output (if provided), and the complete agent conversation
2. Consider both the final outcome AND the process (reasoning, communication, error handling)
3. Score each criterion from 0-10 (0=poor, 5=average, 10=excellent)
4. Provide brief reasoning for each score
5. Return one score entry per criterion listed above, using the exact criterion name"""

        if self.custom_instructions:
            base_prompt += f"\n\nAdditional Evaluation Guidance:\n{self.custom_instructions}"

        return base_prompt

    def _build_user_prompt(self, trajectory: RunTrajectory) -> str:
        """Build the user prompt containing the trajectory to evaluate."""
        task_info = f"Task: {trajectory.task.name}\nInput: {trajectory.task.input}"

        if trajectory.task.expected_output:
            task_info += f"\nExpected Output: {trajectory.task.expected_output}"

        if trajectory.success and trajectory.messages:
            formatted_msgs = []
            for msg in trajectory.messages:
                formatted_msgs.append(self._format_message(msg))
            actual_output = "\n\n".join(formatted_msgs)

            conversation_summary = f"Messages exchanged: {len(trajectory.messages)}"
            if trajectory.usage:
                conversation_summary += f", Tokens: {trajectory.usage.tokens_input + trajectory.usage.tokens_output}"
        else:
            actual_output = f"EXECUTION FAILED: {trajectory.error or 'Unknown error'}"
            conversation_summary = "No successful execution"

        return f"""{task_info}

Execution Summary: {conversation_summary}
Success: {trajectory.success}

Complete Agent Conversation:
{actual_output}

Please evaluate this complete conversation according to the specified criteria."""

    def _format_message(self, msg) -> str:
        """Format a single message with role label and full structure."""
        role = getattr(msg, "role", "unknown")
        source = getattr(msg, "source", "")
        content = getattr(msg, "content", "")

        if role == "system":
            return f"[SYSTEM ({source})]\n{content}"

        elif role == "user":
            return f"[USER ({source})]\n{content}"

        elif role == "assistant":
            parts = [f"[ASSISTANT ({source})]"]
            if content:
                parts.append(content)

            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                for tc in tool_calls:
                    tool_name = getattr(tc, "tool_name", str(tc))
                    params = getattr(tc, "parameters", {})
                    param_strs = []
                    for k, v in params.items():
                        v_str = str(v)
                        if len(v_str) > 200:
                            v_str = v_str[:200] + "..."
                        param_strs.append(f"  {k}: {v_str}")
                    param_block = "\n".join(param_strs)
                    parts.append(f"[TOOL CALL: {tool_name}]\n{param_block}")

            return "\n".join(parts)

        elif role == "tool":
            tool_name = getattr(msg, "tool_name", "unknown")
            success = getattr(msg, "success", True)
            error = getattr(msg, "error", None)
            status = "SUCCESS" if success else "FAILED"
            header = f"[TOOL RESULT ({tool_name}) - {status}]"
            if error:
                header += f"\nError: {error}"
            display_content = content
            if len(display_content) > 2000:
                display_content = display_content[:2000] + "\n... (truncated)"
            return f"{header}\n{display_content}"

        else:
            return f"[{role.upper()} ({source})]\n{content}"
