import { useEffect, useState, type FormEvent } from "react";
import api from "../../api/client";
import type { Preference } from "../../api/types";

const splitCsv = (s: string) =>
  s.split(",").map((x) => x.trim()).filter(Boolean);

export default function Preferences() {
  const [prefs, setPrefs] = useState<Preference[]>([]);
  const [name, setName] = useState("");
  const [titles, setTitles] = useState("");
  const [mustHave, setMustHave] = useState("");
  const [exclude, setExclude] = useState("");
  const [locations, setLocations] = useState("");
  const [remoteOk, setRemoteOk] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<Preference[]>("/preferences").then((r) => setPrefs(r.data));
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    const title_keywords = splitCsv(titles);
    if (title_keywords.length === 0) {
      setError("Add at least one title keyword");
      return;
    }
    const { data } = await api.post<Preference>("/preferences", {
      name,
      title_keywords,
      must_have_keywords: splitCsv(mustHave),
      exclude_keywords: splitCsv(exclude),
      locations: splitCsv(locations),
      remote_ok: remoteOk,
    });
    setPrefs([...prefs, data]);
    setName(""); setTitles(""); setMustHave(""); setExclude(""); setLocations("");
  }

  async function toggleActive(pref: Preference) {
    const { data } = await api.patch<Preference>(`/preferences/${pref.id}`, {
      is_active: !pref.is_active,
    });
    setPrefs(prefs.map((p) => (p.id === pref.id ? data : p)));
  }

  async function remove(pref: Preference) {
    await api.delete(`/preferences/${pref.id}`);
    setPrefs(prefs.filter((p) => p.id !== pref.id));
  }

  return (
    <div>
      <h1>Search Preferences</h1>
      <p className="page-sub">
        Every new student job found on LinkedIn is checked against these. A
        match triggers a Telegram alert and shows up under Job Alerts.
      </p>

      <form className="form-grid panel" onSubmit={create}>
        <div>
          <label>Name</label>
          <input required value={name} onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Junior Backend — Tel Aviv" />
        </div>
        <div>
          <label>Title keywords (comma separated — any of these in the job title)</label>
          <input required value={titles} onChange={(e) => setTitles(e.target.value)}
            placeholder="student, junior, intern, backend" />
        </div>
        <div className="form-row">
          <div>
            <label>Must-have keywords (all required, optional)</label>
            <input value={mustHave} onChange={(e) => setMustHave(e.target.value)}
              placeholder="python" />
          </div>
          <div>
            <label>Exclude keywords (optional)</label>
            <input value={exclude} onChange={(e) => setExclude(e.target.value)}
              placeholder="senior, lead" />
          </div>
        </div>
        <div className="form-row">
          <div>
            <label>Locations (optional — empty = anywhere)</label>
            <input value={locations} onChange={(e) => setLocations(e.target.value)}
              placeholder="tel aviv, haifa" />
          </div>
          <div className="inline" style={{ alignSelf: "end" }}>
            <input id="remote" type="checkbox" checked={remoteOk}
              onChange={(e) => setRemoteOk(e.target.checked)} />
            <label htmlFor="remote" style={{ margin: 0 }}>Remote jobs are OK</label>
          </div>
        </div>
        {error && <div className="auth-error">{error}</div>}
        <button className="btn btn-yellow" style={{ justifySelf: "start" }}>
          + Create preference
        </button>
      </form>

      <div className="stack" style={{ marginTop: 20 }}>
        {prefs.map((pref) => (
          <div className="panel" key={pref.id}>
            <h3>
              {pref.name}{" "}
              <span className={`badge ${pref.is_active ? "done" : ""}`}>
                {pref.is_active ? "active" : "paused"}
              </span>
            </h3>
            <div className="chips">
              {pref.title_keywords.map((k) => <span className="chip" key={k}>{k}</span>)}
              {pref.must_have_keywords.map((k) => <span className="chip green" key={k}>+{k}</span>)}
              {pref.exclude_keywords.map((k) => <span className="chip red" key={k}>−{k}</span>)}
              {pref.locations.map((k) => <span className="chip" key={k}>📍{k}</span>)}
              {pref.remote_ok && <span className="chip">🌍 remote ok</span>}
            </div>
            <div className="actions">
              <button className="btn btn-ghost btn-sm" onClick={() => toggleActive(pref)}>
                {pref.is_active ? "Pause" : "Activate"}
              </button>
              <button className="btn btn-danger btn-sm" onClick={() => remove(pref)}>
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
