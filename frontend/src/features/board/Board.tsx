import {
  DndContext,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { useEffect, useState, type FormEvent } from "react";
import api from "../../api/client";
import type { Application, ApplicationStatus } from "../../api/types";

const COLUMNS: { key: ApplicationStatus; label: string }[] = [
  { key: "applied", label: "Applied" },
  { key: "phone_interview", label: "Phone Interview" },
  { key: "home_assignment", label: "Home Assignment" },
  { key: "technical_interview", label: "Technical Interview" },
  { key: "offer", label: "Offer 🎉" },
  { key: "rejected", label: "Rejected" },
];

function Card({ app, onDelete }: { app: Application; onDelete: (id: number) => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: String(app.id),
  });
  const style = transform
    ? { transform: `translate(${transform.x}px, ${transform.y}px)` }
    : undefined;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`kcard ${isDragging ? "dragging" : ""}`}
      {...listeners}
      {...attributes}
    >
      <div className="t">{app.title}</div>
      <div className="c">{app.company}</div>
      <div className="row">
        <span>{app.applied_at}</span>
        <span style={{ display: "flex", gap: 8 }}>
          {app.url && (
            <a href={app.url} target="_blank" rel="noreferrer" onPointerDown={(e) => e.stopPropagation()}>
              link
            </a>
          )}
          <button
            className="btn btn-danger btn-sm"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => onDelete(app.id)}
          >
            ✕
          </button>
        </span>
      </div>
    </div>
  );
}

function Column({
  col,
  apps,
  onDelete,
}: {
  col: (typeof COLUMNS)[number];
  apps: Application[];
  onDelete: (id: number) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: col.key });
  return (
    <div ref={setNodeRef} className={`kanban-col ${isOver ? "over" : ""}`}>
      <h3>
        {col.label} <span className="count">{apps.length}</span>
      </h3>
      <div className="kanban-cards">
        {apps.map((a) => (
          <Card key={a.id} app={a} onDelete={onDelete} />
        ))}
      </div>
    </div>
  );
}

export default function Board() {
  const [apps, setApps] = useState<Application[]>([]);
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  // distance: 5px lets clicks on buttons/links inside a card work normally
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  useEffect(() => {
    api.get<Application[]>("/applications").then((r) => setApps(r.data));
  }, []);

  function onDragEnd(event: DragEndEvent) {
    const appId = Number(event.active.id);
    const target = event.over?.id as ApplicationStatus | undefined;
    const app = apps.find((a) => a.id === appId);
    if (!target || !app || app.status === target) return;

    // Drop at the bottom of the target column (fractional ordering).
    const bottom =
      Math.max(0, ...apps.filter((a) => a.status === target).map((a) => a.sort_order)) + 1000;
    const previous = apps;
    setApps(apps.map((a) => (a.id === appId ? { ...a, status: target, sort_order: bottom } : a)));
    api
      .post(`/applications/${appId}/move`, { status: target, sort_order: bottom })
      .catch(() => setApps(previous)); // roll back the optimistic update
  }

  async function addCard(e: FormEvent) {
    e.preventDefault();
    const { data } = await api.post<Application>("/applications", {
      company,
      title,
      url: url || null,
    });
    setApps([...apps, data]);
    setCompany("");
    setTitle("");
    setUrl("");
  }

  async function deleteCard(id: number) {
    await api.delete(`/applications/${id}`);
    setApps(apps.filter((a) => a.id !== id));
  }

  return (
    <div>
      <h1>Application Board</h1>
      <p className="page-sub">Drag cards between columns as your process moves forward.</p>
      <form className="add-card-form" onSubmit={addCard}>
        <input required placeholder="Company" value={company} onChange={(e) => setCompany(e.target.value)} />
        <input required placeholder="Job title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <input placeholder="Job URL (optional)" value={url} onChange={(e) => setUrl(e.target.value)} />
        <button className="btn btn-blue">+ Add</button>
      </form>
      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <div className="board">
          {COLUMNS.map((col) => (
            <Column
              key={col.key}
              col={col}
              apps={apps
                .filter((a) => a.status === col.key)
                .sort((a, b) => a.sort_order - b.sort_order)}
              onDelete={deleteCard}
            />
          ))}
        </div>
      </DndContext>
    </div>
  );
}
