import { useState } from "react";
import { downloadCsv, saveCsv } from "../../api.js";
import { adm, Field, useAdmin } from "./shared.jsx";

const SAMPLE = "name,identifier,team\nAsha Rao,21CS001,\nRavi Kumar,21CS002,Night Owls";

/** Sign-in details for teams the organisers created. The server returns each password exactly once. */
function Credentials({ list, onClear }) {
  if (list.length === 0) return null;
  return (
    <section className="panel space-y-3 border-amber/50">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="heading text-sm text-amber">New sign-in details ({list.length})</h2>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={() => saveCsv("codehunt-team-logins.csv", [["team", "password", "members"], ...list.map((c) => [c.team, c.password, (c.members || []).join("; ")])])}>
            Download CSV
          </button>
          <button className="btn-ghost" onClick={onClear}>Dismiss</button>
        </div>
      </div>
      <p className="text-xs text-amber">Save these now. Passwords are stored hashed and cannot be shown again; you can only reset them.</p>
      <ul className="max-h-56 divide-y divide-edge overflow-y-auto text-sm">
        {list.map((c) => (
          <li key={c.team} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
            <span className="font-semibold">{c.team}{c.members?.length > 0 && <span className="ml-2 font-normal text-dim">{c.members.join(", ")}</span>}</span>
            <code className="rounded bg-ink px-2 py-0.5 font-mono text-neon">{c.password}</code>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function PeopleTab({ notify }) {
  const [data, run] = useAdmin("/participants", notify);
  const [credentials, setCredentials] = useState([]);
  const [person, setPerson] = useState({ name: "", identifier: "", team_id: "" });
  const [csv, setCsv] = useState("");
  const [skipped, setSkipped] = useState([]);
  const [auto, setAuto] = useState({ prefix: "Team", shuffle: false });
  const [teamName, setTeamName] = useState("");
  if (!data) return <p className="text-dim">Loading…</p>;

  const { participants, teams, team_size: size } = data;
  const unassigned = participants.filter((p) => !p.team_id).length;
  const keep = (result) => result?.credentials?.length && setCredentials((list) => [...list, ...result.credentials]);

  async function importCsv() {
    const result = await run(() => adm("/participants/import", { method: "POST", body: { csv } }), (r) => `Imported ${r.created} participant${r.created === 1 ? "" : "s"}`);
    if (!result) return;
    keep(result);
    setSkipped(result.skipped);
    if (result.skipped.length === 0) setCsv("");
  }

  return (
    <div className="space-y-5">
      <Credentials list={credentials} onClear={() => setCredentials([])} />

      <section className="panel space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="heading text-lg">Participants ({participants.length})</h2>
          <button className="btn-ghost" onClick={() => downloadCsv("/api/admin/export/participants.csv", "codehunt-participants.csv").catch((e) => notify(e.message, true))}>Export CSV</button>
        </div>
        <p className="text-xs text-dim">
          {size === 1 ? "This event is individual: each participant plays alone." : `Teams hold up to ${size}.`} Change this under Event → Team size.
          {unassigned > 0 && <span className="text-amber"> {unassigned} without a team.</span>}
        </p>
        <form className="grid gap-2 sm:grid-cols-4" onSubmit={(e) => {
          e.preventDefault();
          run(() => adm("/participants", { method: "POST", body: { name: person.name, identifier: person.identifier, team_id: Number(person.team_id) || null } }).then(() => setPerson({ name: "", identifier: "", team_id: person.team_id })), "Participant added");
        }}>
          <input className="input" placeholder="Name" value={person.name} onChange={(e) => setPerson({ ...person, name: e.target.value })} required />
          <input className="input" placeholder="Roll no. or email (optional)" value={person.identifier} onChange={(e) => setPerson({ ...person, identifier: e.target.value })} />
          <select className="input" aria-label="Team" value={person.team_id} onChange={(e) => setPerson({ ...person, team_id: e.target.value })}>
            <option value="">No team yet</option>
            {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <button className="btn-ghost">Add participant</button>
        </form>
        <ul className="max-h-96 divide-y divide-edge overflow-y-auto">
          {participants.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <span>{p.name}{p.identifier && <span className="ml-2 font-mono text-xs text-dim">{p.identifier}</span>}</span>
              <span className="flex items-center gap-2">
                <select className="input !w-40 !py-1.5 text-sm" aria-label={`Team for ${p.name}`} value={p.team_id || 0}
                  onChange={(e) => run(() => adm(`/participants/${p.id}`, { method: "PATCH", body: { team_id: Number(e.target.value) } }), "Participant moved")}>
                  <option value={0}>No team</option>
                  {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                <button className="btn-danger" onClick={() => window.confirm(`Remove ${p.name}?`) && run(() => adm(`/participants/${p.id}`, { method: "DELETE" }), "Participant removed")}>Remove</button>
              </span>
            </li>
          ))}
          {participants.length === 0 && <li className="py-4 text-center text-sm text-dim">Nobody registered yet. Add people above or import a list below.</li>}
        </ul>
      </section>

      <section className="panel space-y-3">
        <h2 className="heading text-sm text-dim">Import a list</h2>
        <p className="text-xs text-dim">
          One participant per line: <code>name, identifier, team</code>. Only the name is required. Naming a team places the
          person in it and creates the team if needed. Duplicate identifiers and overfull teams are skipped and listed.
        </p>
        <textarea className="input font-mono text-sm" rows={5} placeholder={SAMPLE} value={csv} onChange={(e) => setCsv(e.target.value)} />
        <button className="btn-ghost" onClick={importCsv} disabled={!csv.trim()}>Import</button>
        {skipped.length > 0 && (
          <ul className="rounded-lg border border-amber/40 bg-amber/5 p-3 text-xs text-amber">
            {skipped.map((s) => <li key={s.line}>Line {s.line}: {s.reason}</li>)}
          </ul>
        )}
      </section>

      <section className="panel space-y-3">
        <h2 className="heading text-sm text-dim">Form teams</h2>
        <p className="text-xs text-dim">
          {size === 1
            ? `Gives each of the ${unassigned} unassigned participants their own entry, named after them.`
            : `Groups the ${unassigned} unassigned participants into teams of ${size}. The last team takes whoever is left.`}
        </p>
        <div className="flex flex-wrap items-end gap-3">
          {size > 1 && (
            <Field label="Team name prefix"><input className="input !w-40" value={auto.prefix} onChange={(e) => setAuto({ ...auto, prefix: e.target.value })} /></Field>
          )}
          <label className="flex items-center gap-2 pb-2.5 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-neon" checked={auto.shuffle} onChange={(e) => setAuto({ ...auto, shuffle: e.target.checked })} />
            Shuffle first
          </label>
          <button className="btn" disabled={unassigned === 0}
            onClick={async () => keep(await run(() => adm("/teams/auto", { method: "POST", body: auto }), (r) => `Created ${r.teams} team${r.teams === 1 ? "" : "s"}`))}>
            Form teams automatically
          </button>
        </div>
        <form className="flex gap-2 border-t border-edge pt-3" onSubmit={async (e) => {
          e.preventDefault();
          const made = await run(() => adm("/teams", { method: "POST", body: { name: teamName } }), "Team created");
          if (made) { setCredentials((list) => [...list, { team: made.team, password: made.password }]); setTeamName(""); }
        }}>
          <input className="input" placeholder="Or create one empty team by name" value={teamName} onChange={(e) => setTeamName(e.target.value)} required minLength={2} maxLength={40} />
          <button className="btn-ghost shrink-0">Create team</button>
        </form>
      </section>
    </div>
  );
}
