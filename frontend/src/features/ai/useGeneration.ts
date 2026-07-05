import { useEffect, useState } from "react";
import api from "../../api/client";
import type { Generation, Resume } from "../../api/types";

/** Start an AI generation, then poll it every 2.5 s until done/failed. */
export function useGeneration() {
  const [generation, setGeneration] = useState<Generation | null>(null);

  useEffect(() => {
    if (!generation || generation.status === "done" || generation.status === "failed")
      return;
    const timer = setInterval(async () => {
      const { data } = await api.get<Generation>(`/ai/generations/${generation.id}`);
      setGeneration(data);
    }, 2500);
    return () => clearInterval(timer);
  }, [generation?.id, generation?.status]);

  const running =
    generation !== null &&
    (generation.status === "pending" || generation.status === "running");

  return { generation, setGeneration, running };
}

/** Resumes that finished parsing — the only ones AI features can use. */
export function useParsedResumes() {
  const [resumes, setResumes] = useState<Resume[]>([]);
  useEffect(() => {
    api.get<Resume[]>("/resumes").then((r) =>
      setResumes(r.data.filter((x) => x.parse_status === "done"))
    );
  }, []);
  return resumes;
}
