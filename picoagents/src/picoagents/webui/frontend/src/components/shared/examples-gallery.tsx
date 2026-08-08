/**
 * ExamplesGallery - Shows available examples from GitHub when no local agents/orchestrators/workflows found
 * Features: Example cards with category grouping, download & register functionality
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Bot, Users, Workflow, Download, CheckCircle2, AlertCircle } from "lucide-react";
import { apiClient } from "@/services/api";
import type { Entity } from "@/types";

interface Example {
  id: string;
  title: string;
  description: string;
  category: "agent" | "workflow" | "orchestrator";
  githubPath: string;
  difficulty: "beginner" | "intermediate" | "advanced";
}

interface ExamplesGalleryProps {
  onExampleLoaded: (entity: Entity) => void;
}

const EXAMPLES: Example[] = [
  // Agents (2)
  {
    id: "basic-agent",
    title: "Basic Agent",
    description: "Start here: Simple agent with weather and calculator tools",
    category: "agent",
    githubPath: "examples/agents/basic-agent.py",
    difficulty: "beginner",
  },
  {
    id: "agent-as-tool",
    title: "Agent as Tool",
    description: "Coordinator agent using specialist agents as tools",
    category: "agent",
    githubPath: "examples/agents/agent_as_tool.py",
    difficulty: "intermediate",
  },
  // Workflows (2)
  {
    id: "sequential",
    title: "Sequential Workflow",
    description: "Linear pipeline: double → square → add_ten",
    category: "workflow",
    githubPath: "examples/workflows/sequential.py",
    difficulty: "beginner",
  },
  {
    id: "general",
    title: "General Workflow",
    description: "Flexible workflow with branching and parallel steps",
    category: "workflow",
    githubPath: "examples/workflows/general.py",
    difficulty: "intermediate",
  },
  // Orchestrators (3)
  {
    id: "round-robin",
    title: "Round-Robin",
    description: "Poet and critic taking turns to refine haiku",
    category: "orchestrator",
    githubPath: "examples/orchestration/round-robin.py",
    difficulty: "beginner",
  },
  {
    id: "ai-driven",
    title: "AI-Driven",
    description: "LLM dynamically selects which agent speaks next",
    category: "orchestrator",
    githubPath: "examples/orchestration/ai-driven.py",
    difficulty: "intermediate",
  },
  {
    id: "plan-based",
    title: "Plan-Based",
    description: "Orchestrator creates plans and executes them strategically",
    category: "orchestrator",
    githubPath: "examples/orchestration/plan-based.py",
    difficulty: "advanced",
  },
];

const getCategoryIcon = (category: string) => {
  switch (category) {
    case "agent":
      return Bot;
    case "orchestrator":
      return Users;
    case "workflow":
      return Workflow;
    default:
      return Bot;
  }
};

const getDifficultyColor = (difficulty: string) => {
  switch (difficulty) {
    case "beginner":
      return "bg-success/10 text-success border-success/40";
    case "intermediate":
      return "bg-warning/10 text-warning border-warning/40";
    case "advanced":
      return "bg-destructive/10 text-destructive border-destructive/40";
    default:
      return "bg-muted text-muted-foreground";
  }
};

export function ExamplesGallery({ onExampleLoaded }: ExamplesGalleryProps) {
  const [loadingExamples, setLoadingExamples] = useState<Set<string>>(new Set());
  const [loadedExamples, setLoadedExamples] = useState<Set<string>>(new Set());
  const [errorExamples, setErrorExamples] = useState<Map<string, string>>(new Map());

  const handleLoadExample = async (example: Example) => {
    setLoadingExamples((prev) => new Set([...prev, example.id]));
    setErrorExamples((prev) => {
      const newMap = new Map(prev);
      newMap.delete(example.id);
      return newMap;
    });

    try {
      const entity = await apiClient.addExample({
        example_id: example.id,
        github_path: example.githubPath,
      });

      setLoadedExamples((prev) => new Set([...prev, example.id]));
      onExampleLoaded(entity);
    } catch (error) {
      console.error(`Failed to load example ${example.id}:`, error);
      setErrorExamples((prev) => {
        const newMap = new Map(prev);
        newMap.set(
          example.id,
          error instanceof Error ? error.message : "Failed to load example"
        );
        return newMap;
      });
    } finally {
      setLoadingExamples((prev) => {
        const newSet = new Set(prev);
        newSet.delete(example.id);
        return newSet;
      });
    }
  };

  const groupedExamples = {
    agent: EXAMPLES.filter((e) => e.category === "agent"),
    workflow: EXAMPLES.filter((e) => e.category === "workflow"),
    orchestrator: EXAMPLES.filter((e) => e.category === "orchestrator"),
  };

  const renderExampleCard = (example: Example) => {
    const Icon = getCategoryIcon(example.category);
    const isLoading = loadingExamples.has(example.id);
    const isLoaded = loadedExamples.has(example.id);
    const error = errorExamples.get(example.id);

    return (
      <Card key={example.id} className="p-4 hover:shadow-md transition-shadow">
        <div className="flex flex-col gap-3">
          {/* Header */}
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <Icon className="h-5 w-5 flex-shrink-0" />
              <h3 className="font-semibold text-sm">{example.title}</h3>
            </div>
            <Badge variant="outline" className={`text-xs ${getDifficultyColor(example.difficulty)}`}>
              {example.difficulty}
            </Badge>
          </div>

          {/* Description */}
          <p className="text-xs text-muted-foreground leading-relaxed">
            {example.description}
          </p>

          {/* Error Message */}
          {error && (
            <div className="flex items-start gap-2 text-xs text-destructive bg-destructive/10 p-2 rounded">
              <AlertCircle className="h-3 w-3 mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Action Button */}
          <Button
            size="sm"
            variant={isLoaded ? "outline" : "default"}
            onClick={() => handleLoadExample(example)}
            disabled={isLoading || isLoaded}
            className="w-full"
          >
            {isLoading && <LoadingSpinner size="sm" className="mr-2" />}
            {isLoaded && <CheckCircle2 className="h-4 w-4 mr-2" />}
            {!isLoading && !isLoaded && <Download className="h-4 w-4 mr-2" />}
            {isLoading ? "Loading..." : isLoaded ? "Loaded" : "Try Example"}
          </Button>
        </div>
      </Card>
    );
  };

  return (
    <div className="w-full max-w-6xl p-6">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-lg font-semibold mb-2">Try Example Agents, Workflows & Orchestrators</h2>
        <p className="text-muted-foreground">
          Get started by loading an example from the repository
        </p>
      </div>

      {/* Categories */}
      <div className="space-y-8">
        {/* Agents */}
        <div>
          <div className="flex items-center gap-2 mb-4">
            <Bot className="h-5 w-5" />
            <h3 className="text-lg font-semibold">Agents</h3>
            <Badge variant="secondary">{groupedExamples.agent.length}</Badge>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {groupedExamples.agent.map(renderExampleCard)}
          </div>
        </div>

        {/* Workflows */}
        {groupedExamples.workflow.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Workflow className="h-5 w-5" />
              <h3 className="text-lg font-semibold">Workflows</h3>
              <Badge variant="secondary">{groupedExamples.workflow.length}</Badge>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {groupedExamples.workflow.map(renderExampleCard)}
            </div>
          </div>
        )}

        {/* Orchestrators */}
        {groupedExamples.orchestrator.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Users className="h-5 w-5" />
              <h3 className="text-lg font-semibold">Orchestrators</h3>
              <Badge variant="secondary">{groupedExamples.orchestrator.length}</Badge>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {groupedExamples.orchestrator.map(renderExampleCard)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
