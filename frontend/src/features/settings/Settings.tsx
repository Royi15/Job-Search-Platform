import { useEffect, useState } from "react";
import api from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

interface LinkInfo {
  linked: boolean;
  deep_link: string;
}

export default function Settings() {
  const { user, refreshMe } = useAuth();
  const [info, setInfo] = useState<LinkInfo | null>(null);

  async function load() {
    const { data } = await api.get<LinkInfo>("/telegram/link");
    setInfo(data);
  }

  useEffect(() => {
    load();
  }, []);

  async function unlink() {
    await api.post("/telegram/unlink");
    await Promise.all([load(), refreshMe()]);
  }

  return (
    <div>
      <h1>Settings</h1>
      <p className="page-sub">Signed in as {user?.email}</p>

      <div className="stack">
        <div className="panel">
          <h3>
            Telegram alerts{" "}
            <span className={`badge ${info?.linked ? "done" : ""}`}>
              {info ? (info.linked ? "linked ✓" : "not linked") : "…"}
            </span>
          </h3>
          <p className="meta">
            Link your Telegram to get a <strong>personal</strong> message the
            moment a job matching <strong>your</strong> preferences is found
            (only your matches — the full jobs feed lives in Discord).
          </p>
          <ol className="meta" style={{ paddingLeft: 18, margin: "8px 0 0" }}>
            <li>Tap <strong>Link Telegram</strong> — our bot opens in your Telegram app.</li>
            <li>Press <strong>START</strong> at the bottom of the chat. That's it.</li>
            <li>Come back here and hit refresh — the badge turns "linked ✓".</li>
          </ol>
          <div className="actions">
            {info && !info.linked && (
              <>
                <a className="btn btn-blue btn-sm" href={info.deep_link} target="_blank" rel="noreferrer">
                  Link Telegram ↗
                </a>
                <button className="btn btn-ghost btn-sm" onClick={load}>
                  I pressed Start — refresh
                </button>
              </>
            )}
            {info?.linked && (
              <button className="btn btn-danger btn-sm" onClick={unlink}>
                Unlink Telegram
              </button>
            )}
          </div>
        </div>

        <div className="panel">
          <h3>Community Discord feed</h3>
          <p className="meta">
            Every student job the platform finds — not just your matches — is
            posted to the community Discord channel. Ask the platform admin
            for the invite link; no setup needed on your side.
          </p>
        </div>
      </div>
    </div>
  );
}
