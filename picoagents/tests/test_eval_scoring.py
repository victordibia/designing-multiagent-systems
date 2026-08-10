"""
Tests for how evaluation scores are produced.

These cover failure modes where the eval system returned a plausible number
instead of an error - the worst kind of bug in a scoring system, because
nothing surfaces it.
"""

import pytest

from picoagents.eval._runner import EvalRunner
from picoagents.eval.judges._llm import LLMEvalJudge
from picoagents.messages import AssistantMessage
from picoagents.types import (
    ChatCompletionResult,
    RunTrajectory,
    Task,
    Usage,
)

USAGE = Usage(
    duration_ms=1,
    llm_calls=1,
    tokens_input=1,
    tokens_output=1,
    tool_calls=0,
    memory_operations=0,
)

SCORES_JSON = (
    '{{"scores":[{{"name":"{0}","score":1.0,"reasoning":"p"}},'
    '{{"name":"{1}","score":2.0,"reasoning":"b"}},'
    '{{"name":"{2}","score":0.0,"reasoning":"u"}}]}}'
)
CRITERIA = ["completeness", "accuracy", "clarity"]


class _NoStructuredOutputClient:
    """A client that returns text only - the fallback parsing path."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.model = "stub"

    async def create(self, messages, output_format=None, **kwargs):
        return ChatCompletionResult(
            message=AssistantMessage(content=self.text, source="judge"),
            usage=USAGE,
            model="stub",
            finish_reason="stop",
            structured_output=None,
        )


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def trajectory():
    return RunTrajectory(
        task=Task(name="t", input="x"),
        messages=[AssistantMessage(content="answer", source="agent")],
        success=True,
        usage=USAGE,
    )


@pytest.mark.anyio
async def test_scores_survive_a_client_without_structured_output(trajectory):
    """The prompt documents this JSON shape, so the fallback must parse it."""
    judge = LLMEvalJudge(
        client=_NoStructuredOutputClient(SCORES_JSON.format(*CRITERIA))
    )

    score = await judge.score(trajectory, criteria=CRITERIA)

    assert score.dimensions == {"completeness": 1.0, "accuracy": 2.0, "clarity": 0.0}
    assert score.overall == pytest.approx(1.0)


@pytest.mark.anyio
async def test_criterion_names_match_case_insensitively(trajectory):
    """Models capitalise criterion names; that must not inject placeholders."""
    judge = LLMEvalJudge(
        client=_NoStructuredOutputClient(
            SCORES_JSON.format("Completeness", "Accuracy", "Clarity")
        )
    )

    score = await judge.score(trajectory, criteria=CRITERIA)

    # Padding the three unmatched names with a neutral 5.0 gave 3.0.
    assert score.overall == pytest.approx(1.0)


@pytest.mark.anyio
async def test_legacy_dimensions_shape_still_parses(trajectory):
    judge = LLMEvalJudge(
        client=_NoStructuredOutputClient(
            '{"dimensions": {"completeness": 4.0}, "reasoning": {}}'
        )
    )

    score = await judge.score(trajectory, criteria=["completeness"])

    assert score.overall == pytest.approx(4.0)


@pytest.mark.anyio
async def test_unparseable_judge_response_is_neutral_and_logged(
    trajectory, caplog
):
    """A judge that cannot be parsed must say so, not quietly score 5.0."""
    judge = LLMEvalJudge(client=_NoStructuredOutputClient("looks good to me"))

    score = await judge.score(trajectory, criteria=CRITERIA)

    assert score.overall == 5.0
    assert "Judge scoring failed" in caplog.text


def test_crashed_task_is_recorded_not_dropped():
    """A dropped failure let a broken target outscore a complete one."""
    runner = EvalRunner.__new__(EvalRunner)

    class _Target:
        name = "flaky"

    result = runner._failed_task_result(
        _Target(), Task(id="t1", name="t1", input="x"), RuntimeError("boom")
    )

    assert result.task_id == "t1"
    assert result.score.overall == 0.0
    assert result.trajectory.success is False
    assert result.score.metadata["task_failed"] is True
