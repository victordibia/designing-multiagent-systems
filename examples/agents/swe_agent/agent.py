"""
Software Engineering Agent Example

Demonstrates a software engineering agent configured with:
- Coding tools (file ops, execution, search)
- Memory for persistent knowledge across tasks
- Meta-cognitive tools (think, todo tracking)
- HeadTailCompaction for context management
- Hooks for planning and completion verification

Two tasks are included:
1. Code review: reviews a repository, produces findings
2. Build task: creates a web application from scratch

Run: python examples/agents/swe_agent/agent.py

Prerequisites:
    - pip install -e ".[all]"
    - Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT
"""

import asyncio
import os
from pathlib import Path

from picoagents import Agent
from picoagents._hooks import LLMCompletionCheckHook, PlanningHook
from picoagents.compaction import HeadTailCompaction
from picoagents.llm import AzureOpenAIChatCompletionClient
from picoagents.tools import (
    MemoryTool,
    ThinkTool,
    TodoReadTool,
    TodoWriteTool,
    create_coding_tools,
)
from picoagents.types import AgentResponse

system_instructions = """
You are an expert software engineering agent. Follow this workflow:

## PHASE 1: MEMORY CHECK (ALWAYS DO THIS FIRST)
1. Use memory tool to view /memories directory
2. Check for relevant patterns and previous decisions
3. Apply any lessons from past tasks

## PHASE 2: PLANNING
1. Use think tool to analyze requirements
2. Use todo_write to create a structured task list
3. Mark the first task as in_progress

## PHASE 3: EXECUTION
For each task in your todo list:
1. Use coding tools (read_file, write_file, bash_execute)
2. Test changes immediately
3. Use todo_write to mark completed, start next task
4. Log important decisions to /memories/decisions/

## PHASE 4: VERIFICATION
1. Run tests to verify implementation
2. Use todo_read to check all tasks are completed
3. Verify code quality (documentation, error handling)

## PHASE 5: COMPLETION
Before finishing, verify ALL todos are marked complete.
If blocked, explain what remains and why.
NEVER stop with in_progress or pending tasks.
NEVER ask "would you like me to continue?" — you are in
autonomous task completion mode, not conversational mode.

## ERROR HANDLING
- If a command fails, analyze the error and try alternatives
- Log failures to memory to help future tasks
- Don't give up after first failure — iterate

Remember: Your memory persists across sessions. Build knowledge!
"""

# Get API credentials
api_key = os.getenv("AZURE_OPENAI_API_KEY")
endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")

if not api_key or not endpoint:
    print("Error: Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT")

# Set up workspace and memory directories
workspace = Path("./scratch/agent_workspace")
workspace.mkdir(parents=True, exist_ok=True)

memory_path = Path("./scratch/agent_memory")
memory_path.mkdir(parents=True, exist_ok=True)


def get_agent(
    token_budget: int = 25_000,
    max_restarts: int = 3,
    max_iterations: int = 50,
) -> Agent:
    """Create the software engineering agent.

    Args:
        token_budget: HeadTailCompaction budget. Set to 0 to disable.
        max_restarts: Max times the completion hook can resume the loop.
        max_iterations: Max tool loop iterations.
    """
    client = AzureOpenAIChatCompletionClient(
        model="gpt-4.1-mini",
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version="2024-10-21",
    )

    memory_tool = MemoryTool(base_path=memory_path)

    compaction = (
        HeadTailCompaction(token_budget=token_budget, head_ratio=0.2)
        if token_budget > 0
        else None
    )

    agent = Agent(
        name="software_engineer",
        description=(
            "Expert software engineering agent that plans, "
            "codes, and learns from experience"
        ),
        model_client=client,
        instructions=system_instructions,
        tools=[
            memory_tool,
            ThinkTool(),
            TodoWriteTool(),
            TodoReadTool(),
            *create_coding_tools(
                workspace=workspace, bash_timeout=60
            ),
        ],
        compaction=compaction,
        start_hooks=[PlanningHook()],
        end_hooks=[
            LLMCompletionCheckHook(max_restarts=max_restarts)
        ],
        max_iterations=max_iterations,
    )
    return agent


async def run_task(agent: Agent, task: str, label: str):
    """Run a task and print events."""
    print("\n" + "=" * 70)
    print(f"TASK: {label}")
    print("=" * 70)
    print(f"\n{task.strip()}\n")
    print("Agent working...\n")

    response = None
    async for event in agent.run_stream(task):
        print(event)
        if isinstance(event, AgentResponse):
            response = event

    print(f"\n{'─' * 70}")
    if response:
        u = response.usage
        print(f"LLM calls: {u.llm_calls}")
        print(
            f"Tokens: {u.tokens_input + u.tokens_output}"
        )
    return response


async def main():
    """Run software engineering agent on sample tasks."""

    agent = get_agent(token_budget=25_000)

    # Task 1: Code review (read-only, many files)
    await run_task(
        agent,
        task="""
Review the codebase in the workspace directory.
Explore every directory and read every Python file.
Produce a summary with:
1. Overall architecture description
2. Code quality issues found
3. Recommendations for improvement
Store your findings in /memories/reviews/.
        """,
        label="Code Review",
    )

    # Task 2: Build a web application
    await run_task(
        agent,
        task="""
Create a simple task tracker web application with:
1. A FastAPI backend with endpoints for creating,
   listing, and completing tasks (store in memory)
2. A single-page HTML frontend using Tailwind CSS
   (serve from FastAPI static files)
3. A README.md explaining how to run the app

Check memory for any patterns from previous tasks.
Run the app briefly to verify it starts without errors.
        """,
        label="Build Task Tracker App",
    )

    # Print summary
    print("\n" + "=" * 70)
    print("ALL TASKS COMPLETE")
    print("=" * 70)
    print(f"\nWorkspace: {workspace.absolute()}")
    print(f"Memory: {memory_path.absolute()}")

    print("\nGenerated files:")
    for file in workspace.rglob("*"):
        if file.is_file():
            print(f"  - {file.relative_to(workspace)}")

    print("\nMemory files:")
    for file in memory_path.rglob("*"):
        if file.is_file():
            print(f"  - {file.relative_to(memory_path)}")


if __name__ == "__main__":
    asyncio.run(main())
