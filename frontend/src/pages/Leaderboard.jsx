import { useEffect, useState } from "react";
import { api, formatElapsed } from "../api.js";

const MEDALS = { 1: "text-amber", 2: "text-slate-300", 3: "text-orange-400" };
const TH = "py-2 pr-2";

function Row({ row, mine, children }) {
  return (
    <tr className={mine ? "bg-neon/10 outline outline-1 -outline-offset-1 outline-neon/40" : ""}>
      <td className={`py-2.5 pl-2 pr-2 font-mono font-bold ${MEDALS[row.rank] || "text-dim"}`}>{row.rank}</td>
      <td className="max-w-40 truncate py-2.5 pr-2 font-semibold">
        {row.team}
        {mine && <span className="ml-2 font-mono text-[10px] uppercase text-neon">you</span>}
      </td>
      {children}
    </tr>
  );
}

export default function Leaderboard({ team }) {
  const [view, setView] = useState("overall"); // "overall" or a question number
  const [overall, setOverall] = useState(null);
  const [question, setQuestion] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const board = await api("/api/leaderboard");
        const detail = view === "overall" ? null : await api(`/api/leaderboard/question/${view}`);
        if (active) {
          setOverall(board);
          setQuestion(detail);
          setError("");
        }
      } catch (err) {
        if (active) setError(err.message);
      }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [view]);

  if (!overall) return <p className="text-center text-dim">{error || "Loading ranks…"}</p>;
  const showing = view === "overall" ? overall : question;
  const mine = (row) => row.team === team?.name;

  return (
    <section className="panel">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h1 className="heading text-xl text-neon">Leaderboard</h1>
        <span className="chip border-neon/40 text-neon">
          <span className="mr-1.5 h-1.5 w-1.5 animate-pulse rounded-full bg-neon" />
          {overall.event.name} · {overall.event.status}
        </span>
      </div>

      <div className="mb-4 flex gap-1.5 overflow-x-auto pb-1" role="tablist" aria-label="Leaderboard view">
        {["overall", ...overall.questions].map((key) => (
          <button key={key} role="tab" aria-selected={view === key} onClick={() => setView(key)}
            className={`shrink-0 rounded-md border px-3 py-1.5 font-mono text-xs uppercase tracking-wider ${view === key ? "border-neon bg-neon/10 text-neon" : "border-edge text-dim hover:text-slate-100"}`}>
            {key === "overall" ? "Overall" : `Q${key}`}
          </button>
        ))}
      </div>

      {error && <p role="alert" className="mb-2 text-xs text-danger">{error}</p>}
      {!showing ? (
        <p className="py-8 text-center text-dim">Loading…</p>
      ) : showing.rows.length === 0 ? (
        <p className="py-8 text-center text-dim">{view === "overall" ? "No teams yet. Be the first on the board." : "Nobody has attempted this question yet."}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="font-mono text-[11px] uppercase tracking-wider text-dim">
              {view === "overall" ? (
                <tr><th className={`${TH} pl-2`}>#</th><th className={TH}>Team</th><th className={`${TH} text-right`}>Score</th><th className={`${TH} text-right`}>Solved</th><th className={`${TH} text-right`}>Hints</th><th className={`${TH} text-right`}>Time</th></tr>
              ) : (
                <tr><th className={`${TH} pl-2`}>#</th><th className={TH}>Team</th><th className={`${TH} text-right`}>Points</th><th className={`${TH} text-right`}>Hints</th><th className={`${TH} text-right`}>Wrong</th><th className={`${TH} text-right`}>Solved at</th></tr>
              )}
            </thead>
            <tbody className="divide-y divide-edge">
              {view === "overall"
                ? showing.rows.map((row) => (
                    <Row key={row.rank} row={row} mine={mine(row)}>
                      <td className="py-2.5 pr-2 text-right font-mono font-bold text-amber">{row.score}</td>
                      <td className="py-2.5 pr-2 text-right font-mono">{row.solved}/{row.total}</td>
                      <td className="py-2.5 pr-2 text-right font-mono text-dim">{row.hints_used}</td>
                      <td className="py-2.5 pr-2 text-right font-mono text-dim">{row.finished ? formatElapsed(row.elapsed_seconds) : "in play"}</td>
                    </Row>
                  ))
                : showing.rows.map((row) => (
                    <Row key={row.rank} row={row} mine={mine(row)}>
                      <td className={`py-2.5 pr-2 text-right font-mono font-bold ${row.points < 0 ? "text-danger" : "text-amber"}`}>{row.points}</td>
                      <td className="py-2.5 pr-2 text-right font-mono text-dim">{row.hints_used}</td>
                      <td className="py-2.5 pr-2 text-right font-mono text-dim">{row.wrong_attempts}</td>
                      <td className="py-2.5 pr-2 text-right font-mono text-dim">{row.solved ? formatElapsed(row.solved_seconds) : "unsolved"}</td>
                    </Row>
                  ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-4 text-xs text-dim">
        Tie-breaks: {showing?.tie_breaks || overall.tie_breaks} Scores are calculated on the server and refresh every 5 seconds.
      </p>
    </section>
  );
}
