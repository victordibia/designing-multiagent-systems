/**
 * EvalView - Evaluation section with routed tabs:
 * /evaluation/runs · /evaluation/datasets · /evaluation/targets
 */

import { PageHeader } from "@/components/shared/page-header";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { DatasetPanel } from "@/components/eval/dataset-panel";
import { TargetPanel } from "@/components/eval/target-panel";
import { EvalRunsPanel } from "@/components/eval/eval-runs-panel";
import { navigate } from "@/lib/router";

type EvalTab = "runs" | "datasets" | "targets";

export function EvalView({ tab }: { tab: string }) {
  const active: EvalTab = tab === "datasets" || tab === "targets" ? tab : "runs";

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Evaluation"
        description="Datasets, evaluation targets, and batch evaluation runs."
        actions={
          <SegmentedControl
            value={active}
            onValueChange={(next) => navigate(`/evaluation/${next}`)}
            options={[
              { value: "runs", label: "Evaluation runs" },
              { value: "datasets", label: "Datasets" },
              { value: "targets", label: "Targets" },
            ]}
          />
        }
      />
      <div className="min-h-0 flex-1 overflow-hidden">
        {active === "runs" && <EvalRunsPanel />}
        {active === "datasets" && <DatasetPanel />}
        {active === "targets" && <TargetPanel />}
      </div>
    </div>
  );
}
