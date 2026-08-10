"""
Test component serialization across the picoagents framework.

Ensures all core components can serialize/deserialize correctly.
"""

import pytest

from picoagents.agents import Agent
from picoagents.llm import OpenAIChatCompletionClient
from picoagents.memory import FileMemory, ListMemory
from picoagents.orchestration import AIOrchestrator, RoundRobinOrchestrator
from picoagents.termination import (
    CompositeTermination,
    MaxMessageTermination,
    TextMentionTermination,
)
from picoagents.tools import FunctionTool


def test_llm_client_serialization():
    """Test LLM client serialization roundtrip."""
    # Create client
    client = OpenAIChatCompletionClient(
        model="gpt-4.1-mini", api_key="test-key", base_url="https://test.openai.com/v1/"
    )

    # Serialize and deserialize
    component_model = client.dump_component()
    loaded_client = OpenAIChatCompletionClient.load_component(component_model)

    # Verify
    assert loaded_client.model == client.model
    assert loaded_client.api_key == client.api_key
    assert str(loaded_client.client.base_url) == "https://test.openai.com/v1/"


def test_memory_serialization():
    """Test memory serialization roundtrip."""
    # Test ListMemory
    list_memory = ListMemory(max_memories=50)
    component_model = list_memory.dump_component()
    loaded_memory = ListMemory.load_component(component_model)

    assert loaded_memory.max_memories == 50
    assert loaded_memory.memories == []  # Should start empty

    # Test FileMemory
    file_memory = FileMemory("test.json", max_memories=100)
    component_model = file_memory.dump_component()
    loaded_file_memory = FileMemory.load_component(component_model)

    assert loaded_file_memory.file_path == "test.json"
    assert loaded_file_memory.max_memories == 100


def test_function_tool_serialization_blocked():
    """Test that FunctionTool serialization is properly blocked."""

    def test_func():
        return "test"

    tool = FunctionTool(test_func)

    with pytest.raises(
        NotImplementedError, match="cannot be serialized for security reasons"
    ):
        tool.dump_component()


def test_termination_serialization():
    """Test termination condition serialization."""
    # Test MaxMessageTermination
    max_term = MaxMessageTermination(max_messages=10)
    component_model = max_term.dump_component()
    loaded_term = MaxMessageTermination.load_component(component_model)

    assert loaded_term.max_messages == 10
    assert loaded_term.message_count == 0  # Should reset

    # Test TextMentionTermination
    text_term = TextMentionTermination("DONE", case_sensitive=True)
    component_model = text_term.dump_component()
    loaded_text_term = TextMentionTermination.load_component(component_model)

    assert loaded_text_term.text == "DONE"
    assert loaded_text_term.case_sensitive is True

    # Test CompositeTermination
    composite = CompositeTermination([max_term, text_term], mode="any")
    component_model = composite.dump_component()
    loaded_composite = CompositeTermination.load_component(component_model)

    assert len(loaded_composite.conditions) == 2
    assert loaded_composite.mode == "any"


def test_agent_serialization():
    """Test agent serialization with nested components."""
    # Create components
    model_client = OpenAIChatCompletionClient(model="gpt-4.1-mini", api_key="test-key")
    memory = ListMemory(max_memories=20)

    # Create agent
    agent = Agent(
        name="TestAgent",
        description="A test agent",
        instructions="Test instructions",
        model_client=model_client,
        memory=memory,
        max_iterations=8,
    )

    # Serialize and deserialize
    component_model = agent.dump_component()
    loaded_agent = Agent.load_component(component_model)

    # Verify
    assert loaded_agent.name == "TestAgent"
    assert loaded_agent.description == "A test agent"
    assert loaded_agent.instructions == "Test instructions"
    assert loaded_agent.max_iterations == 8
    assert loaded_agent.model_client.model == "gpt-4.1-mini"
    assert loaded_agent.memory is not None
    assert loaded_agent.memory.max_memories == 20
    assert isinstance(loaded_agent.memory, ListMemory)


def test_round_robin_orchestrator_serialization():
    """Test RoundRobinOrchestrator serialization."""
    # Create components
    model_client1 = OpenAIChatCompletionClient(model="gpt-4.1-mini", api_key="test-1")
    model_client2 = OpenAIChatCompletionClient(model="gpt-4.1-mini", api_key="test-2")

    agent1 = Agent("Agent1", instructions="You are agent 1", description="First agent", model_client=model_client1)
    agent2 = Agent("Agent2", instructions="You are agent 2", description="Second agent", model_client=model_client2)

    termination = MaxMessageTermination(max_messages=5)

    # Create orchestrator
    orchestrator = RoundRobinOrchestrator(
        agents=[agent1, agent2], termination=termination, max_iterations=10
    )

    # Serialize and deserialize
    component_model = orchestrator.dump_component()
    loaded_orchestrator = RoundRobinOrchestrator.load_component(component_model)

    # Verify
    assert len(loaded_orchestrator.agents) == 2
    assert loaded_orchestrator.agents[0].name == "Agent1"
    assert loaded_orchestrator.agents[1].name == "Agent2"
    assert loaded_orchestrator.max_iterations == 10
    assert isinstance(loaded_orchestrator.termination, MaxMessageTermination)
    assert loaded_orchestrator.termination.max_messages == 5
    # Runtime state should reset
    assert loaded_orchestrator.current_agent_index == 0


def test_ai_orchestrator_serialization():
    """Test AIOrchestrator serialization."""
    # Create components
    model_client = OpenAIChatCompletionClient(model="gpt-4.1-mini", api_key="test-key")
    selector_client = OpenAIChatCompletionClient(
        model="gpt-4.1-mini", api_key="selector-key"
    )

    agent1 = Agent("Agent1", instructions="You are agent 1", description="First agent", model_client=model_client)
    agent2 = Agent("Agent2", instructions="You are agent 2", description="Second agent", model_client=model_client)

    termination = TextMentionTermination("COMPLETE")

    # Create AI orchestrator
    ai_orchestrator = AIOrchestrator(
        agents=[agent1, agent2],
        termination=termination,
        model_client=selector_client,
        max_iterations=15,
    )

    # Serialize and deserialize
    component_model = ai_orchestrator.dump_component()
    loaded_ai = AIOrchestrator.load_component(component_model)

    # Verify
    assert len(loaded_ai.agents) == 2
    assert loaded_ai.agents[0].name == "Agent1"
    assert loaded_ai.agents[1].name == "Agent2"
    assert loaded_ai.max_iterations == 15
    assert loaded_ai.model_client.api_key == "selector-key"
    assert isinstance(loaded_ai.termination, TextMentionTermination)
    assert loaded_ai.termination.text == "COMPLETE"
    # Runtime state should reset
    assert loaded_ai.selection_history == []
    assert loaded_ai.agent_capabilities_cache is None


def test_nested_serialization_integrity():
    """Test that deeply nested serialization preserves all data integrity."""
    # Create a complex nested structure
    model_client = OpenAIChatCompletionClient(
        model="gpt-4.1-mini", api_key="nested-test"
    )
    memory = FileMemory("nested_test.json", max_memories=100)

    agent = Agent(
        name="NestedAgent",
        description="Complex nested agent",
        instructions="Complex instructions",
        model_client=model_client,
        memory=memory,
    )

    # Create composite termination
    max_term = MaxMessageTermination(25)
    text_term = TextMentionTermination("FINISH", case_sensitive=False)
    composite_term = CompositeTermination([max_term, text_term], mode="all")

    # Create AI orchestrator with all the nested components
    orchestrator = AIOrchestrator(
        agents=[agent],
        termination=composite_term,
        model_client=OpenAIChatCompletionClient(
            model="gpt-4.1-mini", api_key="orchestrator-key"
        ),
        max_iterations=20,
    )

    # Full serialization roundtrip
    component_model = orchestrator.dump_component()
    loaded_orchestrator = AIOrchestrator.load_component(component_model)

    # Deep verification
    loaded_agent = loaded_orchestrator.agents[0]
    assert loaded_agent.name == "NestedAgent"
    assert loaded_agent.model_client.api_key == "nested-test"
    assert loaded_agent.memory is not None
    assert isinstance(loaded_agent.memory, FileMemory)
    assert loaded_agent.memory.file_path == "nested_test.json"
    assert loaded_agent.memory.max_memories == 100

    loaded_termination = loaded_orchestrator.termination
    assert isinstance(loaded_termination, CompositeTermination)
    assert len(loaded_termination.conditions) == 2
    assert loaded_termination.mode == "all"

    # Verify nested termination conditions
    conditions = loaded_termination.conditions
    max_condition = next(c for c in conditions if isinstance(c, MaxMessageTermination))
    text_condition = next(
        c for c in conditions if isinstance(c, TextMentionTermination)
    )

    assert max_condition.max_messages == 25
    assert text_condition.text == "FINISH"
    assert text_condition.case_sensitive is False


if __name__ == "__main__":
    # Run tests manually if needed
    pytest.main([__file__, "-v"])
