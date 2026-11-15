"use client";
import { useState } from "react";
import ScenarioPanel from "./ScenarioPanel";
import { Field, ZipSelect } from "./ui";
import { selectCls } from "./styles";
import type { Metric } from "@/lib/contract";

export default function ScenarioTool() {
  const [zip, setZip] = useState("92104");
  const [metric, setMetric] = useState<Metric>("zori");
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="ZIP"><ZipSelect value={zip} onChange={setZip} /></Field>
        <Field label="Measure">
          <select className={`${selectCls} w-full`} value={metric} onChange={(e) => setMetric(e.target.value as Metric)}>
            <option value="zori">Typical rent</option>
            <option value="zhvi">Typical home value</option>
          </select>
        </Field>
      </div>
      <ScenarioPanel zip={zip} metric={metric} />
    </div>
  );
}
