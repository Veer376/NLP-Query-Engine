import { useCallback, useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Panel,
} from "reactflow";
import type { FitViewOptions } from "reactflow";
import "reactflow/dist/style.css";
import type { BackendSchema, BackendTable } from "../state/types";

export type SchemaGraphProps = {
  schema: BackendSchema;
  onNodeClick?: (table: BackendTable) => void;
  height?: number | string;
};

const fitView: FitViewOptions = { padding: 0.2, includeHiddenNodes: true };

export default function SchemaGraph({
  schema,
  onNodeClick,
  height = 520,
}: SchemaGraphProps) {
  const tables = schema?.tables ?? [];
  const rels = schema?.relationships ?? [];

  const initialNodes = useMemo(
    () =>
      tables.map((t, idx) => ({
        id: t.name,
        data: { label: t.name },
        position: { x: (idx % 4) * 260, y: Math.floor(idx / 4) * 140 },
        style: {
          borderRadius: 12,
          padding: 8,
          border: "1px solid #d7d7d7",
          background: "#fff",
          fontSize: 12,
          fontWeight: 600,
        },
      })),
    [tables]
  );

  const initialEdges = useMemo(
    () =>
      rels.map((r, i) => ({
        id: `${r.table}->${r.referred_table}-${i}`,
        source: r.table,
        target: r.referred_table,
        animated: false,
        label: r.constraint_name || `${r.column}→${r.referred_column}`,
        style: { stroke: "#bcbcbc" },
        labelStyle: { fill: "#555", fontSize: 10 },
      })),
    [rels]
  );

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  const handleNodeClick = useCallback(
    (_: any, node: any) => {
      if (!onNodeClick) return;
      const table = tables.find((t) => t.name === node.id);
      if (table) onNodeClick(table);
    },
    [onNodeClick, tables]
  );

  return (
    <div style={{ height, border: "1px solid #e5e5e5", borderRadius: 14 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        fitView
        fitViewOptions={fitView}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#f3f3f3" gap={16} />
        <MiniMap pannable zoomable />
        <Controls showInteractive={false} />
        <Panel position="top-left">
          <strong>Tables:</strong> {tables.length} &nbsp; | &nbsp;
          <strong>Relationships:</strong> {rels.length}
        </Panel>
      </ReactFlow>
    </div>
  );
}
