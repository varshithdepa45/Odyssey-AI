import { useState } from "react";
import { adm, Field, useAdmin } from "./shared.jsx";

function TeamRow({ team, run }) {
  const [text, setText] = useState(team.questions.join(", "));
  const save = (questions, done) => run(() => adm(`/teams/${team.team_id}/assignments`, { method: "PUT", body: { questions } }).then((r) => setText(r.questions.join(", "))), done);
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
      <span className="min-w-32 font-semibold">
        {team.team}
        <span className={`chip ml-2 ${team.custom ? "border-cyan/40 text-cyan" : ""}`}>{team.custom ? "custom" : "default"}</span>
        {team.solved > 0 && <span className="ml-2 text-xs text-dim">{team.solved} solved</span>}
      </span>
      <span className="flex flex-1 items-center justify-end gap-2">
        <input className="input !w-48 !py-1.5 font-mono text-sm" aria-label={`Questions for ${team.team}`} value={text} onChange={(e) => setText(e.target.value)} />
        <button className="btn-ghost" onClick={() => save(text.split(/[\s,]+/).filter(Boolean).map(Number), "Questions saved")}>Save</button>
        {team.custom && <button className="btn-ghost" onClick={() => save([], "Back to the default order")}>Default</button>}
      </span>
    </li>
  );
}

/** Which questions each team plays, and in what order. */
export default function Assignments({ notify }) {
  const [data, run] = useAdmin("/assignments", notify);
  const [auto, setAuto] = useState({ count: "", shuffle: false, overwrite: false });
  if (!data) return null;
  return (
    <section className="panel space-y-3">
      <h2 className="heading text-lg">Question assignments</h2>
      <p className="text-xs text-dim">
        By default every team plays the event's questions in order (limited by Event → Questions per team). Give a team its
        own list as question numbers in play order, for example <code>5, 2, 8</code>. A question cannot repeat, must exist,
        and cannot be dropped once the team has started it. Available: {data.available.map((q) => q.question).join(", ") || "none"}.
      </p>
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-edge bg-ink p-3">
        <Field label="Questions per team"><input className="input !w-28" type="number" min="1" placeholder="event's" value={auto.count} onChange={(e) => setAuto({ ...auto, count: e.target.value })} /></Field>
        <label className="flex items-center gap-2 pb-2.5 text-sm" title="Off: each team starts one question further along, so teams spread out">
          <input type="checkbox" className="h-4 w-4 accent-neon" checked={auto.shuffle} onChange={(e) => setAuto({ ...auto, shuffle: e.target.checked })} />Random pick
        </label>
        <label className="flex items-center gap-2 pb-2.5 text-sm">
          <input type="checkbox" className="h-4 w-4 accent-neon" checked={auto.overwrite} onChange={(e) => setAuto({ ...auto, overwrite: e.target.checked })} />Replace existing
        </label>
        <button className="btn-ghost" onClick={() => run(
          () => adm("/assignments/auto", { method: "POST", body: { count: Number(auto.count) || null, shuffle: auto.shuffle, overwrite: auto.overwrite } }),
          (r) => `Assigned ${r.per_team} questions to ${r.assigned} team${r.assigned === 1 ? "" : "s"}${r.skipped.length ? `; skipped ${r.skipped.length} (${r.skipped[0].reason})` : ""}`
        )}>Assign automatically</button>
      </div>
      <ul className="divide-y divide-edge">
        {data.teams.map((t) => <TeamRow key={`${t.team_id}-${t.questions.join()}`} team={t} run={run} />)}
        {data.teams.length === 0 && <li className="py-3 text-sm text-dim">No teams yet.</li>}
      </ul>
    </section>
  );
}
