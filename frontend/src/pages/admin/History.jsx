import { useState } from "react";
import { downloadCsv } from "../../api.js";
import { useAdmin } from "./shared.jsx";

const KINDS = [["", "All score changes"], ["hint", "Hint log"], ["wrong", "Wrong answers"], ["correct", "Solves"], ["bonus", "Bonuses"], ["adjust", "Adjustments"]];
const EXPORTS = [
  ["Results", "/api/admin/export.csv", "codehunt-results.csv"],
  ["Score history", "/api/admin/export/history.csv", "codehunt-score-history.csv"],
  ["Attempts", "/api/admin/export/attempts.csv", "codehunt-attempts.csv"],
  ["Participants", "/api/admin/export/participants.csv", "codehunt-participants.csv"],
];
const time = (iso) => new Date(iso).toLocaleTimeString();

export default function HistoryTab({ notify }) {
  const [kind, setKind] = useState("");
  const [ledger, , reloadLedger] = useAdmin(`/history${kind ? `?kind=${kind}` : ""}`, notify);
  const [attempts, , reloadAttempts] = useAdmin("/submissions", notify);

  return (
    <div className="space-y-5">
      <section className="panel space-y-3">
        <h2 className="heading text-sm text-dim">CSV exports</h2>
        <div className="flex flex-wrap gap-2">
          {EXPORTS.map(([label, path, file]) => (
            <button key={path} className="btn-ghost" onClick={() => downloadCsv(path, file).catch((e) => notify(e.message, true))}>{label}</button>
          ))}
        </div>
      </section>

      <section className="panel space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="heading text-lg">Score history</h2>
          <span className="flex gap-2">
            <select className="input !w-44 !py-1.5 text-sm" aria-label="Filter" value={kind} onChange={(e) => setKind(e.target.value)}>
              {KINDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <button className="btn-ghost" onClick={reloadLedger}>Refresh</button>
          </span>
        </div>
        <p className="text-xs text-dim">Every point gained or lost, newest first. A team's score is always the sum of its rows.</p>
        <ul className="max-h-96 divide-y divide-edge overflow-y-auto text-sm">
          {(ledger || []).map((row, i) => (
            <li key={i} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span><span className="font-semibold">{row.team}</span> <span className="text-dim">· {row.note}</span></span>
              <span className="flex items-center gap-2">
                <span className="chip">{row.kind}</span>
                <span className={`w-12 text-right font-mono font-bold ${row.delta < 0 ? "text-danger" : "text-neon"}`}>{row.delta > 0 ? "+" : ""}{row.delta}</span>
                <time className="font-mono text-xs text-dim">{time(row.at)}</time>
              </span>
            </li>
          ))}
          {ledger?.length === 0 && <li className="py-4 text-center text-dim">Nothing recorded yet.</li>}
        </ul>
      </section>

      <section className="panel space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="heading text-lg">Latest 100 attempts</h2>
          <button className="btn-ghost" onClick={reloadAttempts}>Refresh</button>
        </div>
        <ul className="max-h-96 divide-y divide-edge overflow-y-auto text-sm">
          {(attempts || []).map((r, i) => (
            <li key={i} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span><span className="font-semibold">{r.team}</span> <span className="text-dim">· question {r.stage}</span></span>
              <span className="flex items-center gap-2">
                {!r.correct && <code className="max-w-48 truncate font-mono text-xs text-dim">{r.answer}</code>}
                <span className={`chip ${r.correct ? "border-neon/40 text-neon" : "border-danger/40 text-danger"}`}>{r.correct ? "correct" : "wrong"}</span>
                <time className="font-mono text-xs text-dim">{time(r.at)}</time>
              </span>
            </li>
          ))}
          {attempts?.length === 0 && <li className="py-4 text-center text-dim">No attempts yet.</li>}
        </ul>
      </section>
    </div>
  );
}
