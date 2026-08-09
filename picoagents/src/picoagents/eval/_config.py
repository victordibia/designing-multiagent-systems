"""
Agent configuration for evaluation.

This module defines AgentConfig - a complete specification of how to set up
an agent for evaluation comparison.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ensure_skill_frontmatter(name: str, content: str) -> str:
    """Ensure a SKILL.md body has YAML frontmatter for JIT discovery.

    The optimizer edits skills as free-form text. If a generated skill omits the
    frontmatter that picoagents' SkillsTool needs to surface it (name/description),
    synthesize a minimal block from the skill name so it still loads on demand.
    """
    if content.lstrip().startswith("---"):
        return content
    first_line = next((ln.strip() for ln in content.splitlines() if ln.strip()), name)
    description = (first_line.lstrip("# ").strip() or name)[:200]
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{content}"


@dataclass
class AgentConfig:
    """Complete agent configuration for evaluation.

    An AgentConfig specifies all the knobs that can be tuned when comparing
    agent performance: model, compaction strategy, system prompt, tools, etc.

    Example:
        >>> config = AgentConfig(
        ...     name="head_tail_gpt4o",
        ...     model_provider="azure",
        ...     model_name="gpt-4o-mini",
        ...     compaction="head_tail",
        ...     token_budget=50_000,
        ... )
        >>> agent = config.to_agent()
    """

    # Unique identifier for this configuration
    name: str

    # Model settings
    model_provider: str = "openai"  # "openai", "azure", "anthropic"
    model_name: str = "gpt-4o-mini"

    # Context management
    compaction: Optional[str] = None  # None, "head_tail", "sliding"
    token_budget: int = 50_000
    head_ratio: float = 0.3  # For head_tail strategy

    # Agent behavior
    system_prompt: str = "You are a helpful assistant."
    instruction_preset: Optional[str] = None  # "general" - uses get_instructions()
    tools: List[str] = field(default_factory=lambda: ["coding"])
    max_iterations: int = 30

    # Optimizable text artifacts (used by picoagents.optim).
    # skills: name -> markdown skill body, appended to instructions.
    # tool_descriptions: tool name -> description override applied at build time.
    skills: Dict[str, str] = field(default_factory=dict)
    tool_descriptions: Dict[str, str] = field(default_factory=dict)

    # Optional tuning
    temperature: float = 0.0

    # Tool configuration
    workspace: Optional[str] = None  # Root directory for file tools
    bash_timeout: int = 300  # 5 min timeout for bash

    # Custom tool instances (overrides tool categories when set)
    tool_instances: Optional[List[Any]] = field(default=None, repr=False)

    # Additional kwargs passed to agent constructor
    extra_kwargs: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize configuration to dictionary."""
        return {
            "name": self.name,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "compaction": self.compaction,
            "token_budget": self.token_budget,
            "head_ratio": self.head_ratio,
            "system_prompt": self.system_prompt,
            "instruction_preset": self.instruction_preset,
            "tools": self.tools,
            "max_iterations": self.max_iterations,
            "temperature": self.temperature,
            "workspace": self.workspace,
            "bash_timeout": self.bash_timeout,
            "skills": self.skills,
            "tool_descriptions": self.tool_descriptions,
            "extra_kwargs": self.extra_kwargs,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentConfig":
        """Create configuration from dictionary."""
        return cls(
            name=data["name"],
            model_provider=data.get("model_provider", "openai"),
            model_name=data.get("model_name", "gpt-4o-mini"),
            compaction=data.get("compaction"),
            token_budget=data.get("token_budget", 50_000),
            head_ratio=data.get("head_ratio", 0.3),
            system_prompt=data.get("system_prompt", "You are a helpful assistant."),
            instruction_preset=data.get("instruction_preset"),
            tools=data.get("tools", ["coding"]),
            workspace=data.get("workspace"),
            max_iterations=data.get("max_iterations", 30),
            temperature=data.get("temperature", 0.0),
            bash_timeout=data.get("bash_timeout", 300),
            skills=data.get("skills", {}),
            tool_descriptions=data.get("tool_descriptions", {}),
            extra_kwargs=data.get("extra_kwargs", {}),
        )

    @classmethod
    def from_string(cls, config_str: str) -> "AgentConfig":
        """Parse configuration from CLI-style string.

        Format: name:key=value,key=value,...

        Example:
            >>> config = AgentConfig.from_string(
            ...     "head_tail:model_name=gpt-4o,strategy=head_tail,budget=50000"
            ... )
        """
        if ":" not in config_str:
            return cls(name=config_str)

        name, params_str = config_str.split(":", 1)
        params: Dict[str, Any] = {"name": name}

        for param in params_str.split(","):
            if "=" not in param:
                continue
            key, value = param.split("=", 1)
            key = key.strip()
            value = value.strip()

            # Type coercion
            if key in ("token_budget", "max_iterations", "bash_timeout"):
                params[key] = int(value)
            elif key in ("temperature", "head_ratio"):
                params[key] = float(value)
            elif key == "tools":
                params[key] = value.split("+")
            elif key == "strategy":
                params["compaction"] = value if value != "none" else None
            elif key == "model":
                params["model_name"] = value
            elif key == "provider":
                params["model_provider"] = value
            else:
                params[key] = value

        return cls.from_dict(params)

    def _create_model_client(self):
        """Create appropriate model client based on provider."""
        if self.model_provider == "openai":
            from ..llm import OpenAIChatCompletionClient

            return OpenAIChatCompletionClient(
                model=self.model_name,
            )
        elif self.model_provider == "azure":
            from ..llm import AzureOpenAIChatCompletionClient
            import os

            temp = self.temperature if self.temperature > 0 else None
            return AzureOpenAIChatCompletionClient(
                azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT", self.model_name),
                api_key=os.environ["AZURE_OPENAI_API_KEY"],
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
                temperature=temp,
            )
        elif self.model_provider == "anthropic":
            from ..llm import AnthropicChatCompletionClient
            import os

            return AnthropicChatCompletionClient(
                model=self.model_name,
                api_key=os.environ.get("ANTHROPIC_API_KEY"),
            )
        else:
            raise ValueError(f"Unknown model provider: {self.model_provider}")

    def _create_compaction(self):
        """Create compaction strategy based on configuration."""
        if self.compaction is None or self.compaction == "none":
            from ..compaction import NoCompaction

            return NoCompaction()
        elif self.compaction == "head_tail":
            from ..compaction import HeadTailCompaction

            return HeadTailCompaction(
                token_budget=self.token_budget,
                head_ratio=self.head_ratio,
            )
        elif self.compaction == "sliding":
            from ..compaction import SlidingWindowCompaction

            return SlidingWindowCompaction(
                token_budget=self.token_budget,
            )
        else:
            raise ValueError(f"Unknown compaction strategy: {self.compaction}")

    def _create_tools(self):
        """Create tools based on configuration.

        Each entry in ``self.tools`` is either a category (``"coding"``, ``"core"``)
        which expands to its whole tool group, or the name of an individual tool
        (e.g. ``"calculator"``, ``"bash_execute"``) for granular selection - this is
        what ``optim.ToolSelectionTunable`` mutates when adding/removing a tool.

        If ``tool_instances`` is set, those instances are used directly.
        """
        if self.tool_instances is not None:
            return list(self.tool_instances)

        from ..tools import create_coding_tools, create_core_tools

        workspace = Path(self.workspace) if self.workspace else None
        coding = create_coding_tools(workspace=workspace, bash_timeout=self.bash_timeout)
        core = create_core_tools()
        by_name = {t.name: t for t in (*coding, *core)}

        all_tools = []
        seen = set()
        for entry in self.tools:
            if entry == "coding":
                group = coding
            elif entry == "core":
                group = core
            elif entry in by_name:
                group = [by_name[entry]]  # individual tool by name
            else:
                continue  # unknown entry - skip (catalog guarantees valid names)
            for tool in group:
                if tool.name not in seen:
                    seen.add(tool.name)
                    all_tools.append(tool)

        return all_tools

    def to_agent(self, middlewares=None):
        """Instantiate an Agent from this configuration.

        Args:
            middlewares: Optional list of middleware to add to the agent.

        Returns:
            Configured Agent instance.
        """
        from ..agents import Agent

        model_client = self._create_model_client()
        compaction = self._create_compaction()
        tools = self._create_tools()

        # Apply tool description overrides (optimizable via picoagents.optim).
        if self.tool_descriptions:
            for tool in tools:
                override = self.tool_descriptions.get(getattr(tool, "name", ""))
                if override and hasattr(tool, "description"):
                    try:
                        tool.description = override
                    except Exception:
                        pass  # frozen/immutable tools are left as-is

        # Resolve instructions: preset takes priority over raw system_prompt
        if self.instruction_preset:
            from .._instructions import get_instructions

            tool_names = [t.name for t in tools]
            instructions = get_instructions(
                preset=self.instruction_preset,
                tool_names=tool_names,
            )
        else:
            instructions = self.system_prompt

        # Translate optimizable skills (held as SKILL.md text in the config) into
        # what an agent actually consumes: a skills directory exposed through the
        # progressive-disclosure SkillsTool. The optimizer edits the text; the
        # agent discovers/loads skills on demand, exactly like on-disk skills.
        if self.skills:
            import tempfile

            from ..tools import create_skills_tool

            base = Path(self.workspace) if self.workspace else Path(
                tempfile.mkdtemp(prefix="pico_skills_")
            )
            skills_dir = base / ".picoagents_skills"
            for skill_name, skill_md in self.skills.items():
                skill_path = skills_dir / skill_name
                skill_path.mkdir(parents=True, exist_ok=True)
                (skill_path / "SKILL.md").write_text(
                    _ensure_skill_frontmatter(skill_name, skill_md)
                )
            tools = list(tools) + [create_skills_tool(extra_paths=[skills_dir])]

        return Agent(
            name=self.name,
            description=f"Eval agent: {self.name}",
            instructions=instructions,
            model_client=model_client,
            tools=tools,
            compaction=compaction,
            max_iterations=self.max_iterations,
            middlewares=middlewares or [],
            **self.extra_kwargs,
        )

    def __repr__(self) -> str:
        return (
            f"AgentConfig(name={self.name!r}, model={self.model_provider}:{self.model_name}, "
            f"strategy={self.compaction}, budget={self.token_budget})"
        )
