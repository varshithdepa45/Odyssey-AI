import { useCallback, useEffect, useState } from "react";
import { adminSession, api, downloadCsv, formatElapsed } from "../api.js";
import Assignments from "./admin/Assignments.jsx";
import HistoryTab from "./admin/History.jsx";
import MapTab from "./admin/MapAdmin.jsx";
import PeopleTab from "./admin/People.jsx";
import { adm, CIPHERS, Field, useAdmin } from "./admin/shared.jsx";

const TABS = ["Event", "People", "Teams", "Puzzles", "Archive", "Map", "History"];
const KEY_HELP = { caesar: "Shift, e.g. 7", vigenere: "Keyword", book: "The full passage, one line per line" };

function AdminLogin({ onDone }) {
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    try {
      adminSession.set(await api("/api/auth/admin", { method: "POST", body: form }));
      onDone();
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <form onSubmit={submit} className="panel mx-auto mt-6 max-w-sm space-y-4">
      <h1 className="heading text-xl text-amber">Organiser access</h1>
      <Field label="Username">
        <input className="input" autoComplete="username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
      </Field>
      <Field label="Password">
        <input className="input" type="password" autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
      </Field>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <button className="btn w-full">Sign in</button>
    </form>
  );
}

function EventTab({ notify }) {
  const [events, run] = useAdmin("/events", notify);
  const [overview, , reloadOverview] = useAdmin("/overview", notify);
  const [draft, setDraft] = useState(null);
  const [newName, setNewName] = useState("");
  const active = events?.find((e) => e.is_active);

  useEffect(() => {
    if (active) setDraft({ ...active, hint_costs: active.hint_costs.join(", ") });
  }, [active?.id, active?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!events) return <p className="text-dim">Loading…</p>;
  const patch = (body, done) => run(() => adm(`/events/${active.id}`, { method: "PATCH", body }).then(reloadOverview), done);
  const set = (name) => (e) => setDraft({ ...draft, [name]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  return (
    <div className="space-y-5">
      {active && draft && (
        <section className="panel space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="heading text-lg">{active.name}</h2>
            <span className="chip border-amber/40 text-amber">{active.status}</span>
          </div>
          {overview && (
            <dl className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              {[["Teams", overview.teams], ["Finished", overview.finished], ["Puzzles", overview.puzzles], ["Documents", overview.documents], ["Oracle questions", overview.chat_messages]].map(([k, v]) => (
                <div key={k} className="rounded-lg border border-edge bg-ink p-3">
                  <dt className="label mb-0">{k}</dt>
                  <dd className="font-mono text-xl font-bold text-neon">{v}</dd>
                </div>
              ))}
            </dl>
          )}
          <div className="flex flex-wrap gap-2">
            {[["live", "Go live"], ["paused", "Pause"], ["ended", "End hunt"], ["draft", "Back to draft"]].map(([status, label]) => (
              <button key={status} className="btn-ghost" disabled={active.status === status}
                onClick={() => window.confirm(`${label}?`) && patch({ status }, `Event is now ${status}`)}>
                {label}
              </button>
            ))}
          </div>
          {active.ends_at && <p className="text-xs text-dim">Ends automatically at {new Date(active.ends_at).toLocaleString()}.</p>}
          <div className="grid gap-3 sm:grid-cols-4">
            <Field label="Name" className="sm:col-span-2"><input className="input" value={draft.name} onChange={set("name")} /></Field>
            <Field label="Duration, minutes (0 = no limit)"><input className="input" type="number" min="0" value={draft.duration_minutes} onChange={set("duration_minutes")} /></Field>
            <Field label="Team size (1 = individual)"><input className="input" type="number" min="1" value={draft.team_size} onChange={set("team_size")} /></Field>
          </div>
          <h3 className="label !mb-0 border-t border-edge pt-3">Scoring</h3>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Points per correct answer"><input className="input" type="number" min="0" value={draft.default_points} onChange={set("default_points")} /></Field>
            <Field label="Wrong-answer penalty"><input className="input" type="number" min="0" value={draft.wrong_penalty} onChange={set("wrong_penalty")} /></Field>
            <Field label="Hint costs: hint 1, 2, 3…"><input className="input font-mono" value={draft.hint_costs} onChange={set("hint_costs")} /></Field>
            <Field label="Completion bonus"><input className="input" type="number" min="0" value={draft.completion_bonus} onChange={set("completion_bonus")} /></Field>
            <Field label="Floor: least a question can be worth"><input className="input" type="number" min="0" value={draft.min_points} onChange={set("min_points")} /></Field>
            <Field label="Questions per team (0 = all)"><input className="input" type="number" min="0" value={draft.questions_per_team} onChange={set("questions_per_team")} /></Field>
          </div>
          <p className="text-xs text-dim">
            Points and hint costs here are defaults for new questions and hints. Existing ones keep their own values
            (edit them under Puzzles) until you press "Apply to all questions".
          </p>
          <Field label="Final message (shown only to teams that finish)">
            <textarea className="input min-h-24" value={draft.final_message} onChange={set("final_message")} />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-neon" checked={draft.registration_open} onChange={set("registration_open")} />
            Registration open
          </label>
          <div className="flex flex-wrap gap-2">
            <button className="btn" onClick={() => patch({
              name: draft.name, wrong_penalty: Number(draft.wrong_penalty), min_points: Number(draft.min_points),
              final_message: draft.final_message, registration_open: draft.registration_open,
              duration_minutes: Number(draft.duration_minutes), team_size: Number(draft.team_size),
              default_points: Number(draft.default_points), completion_bonus: Number(draft.completion_bonus),
              questions_per_team: Number(draft.questions_per_team),
              hint_costs: String(draft.hint_costs).split(/[\s,]+/).filter(Boolean).map(Number),
            }, "Event saved")}>Save event</button>
            <button className="btn-ghost" onClick={() => window.confirm("Set every question to the default points and every hint to its slot's cost? Save the event first if you changed the values.") && run(() => adm("/scoring/apply", { method: "POST" }), "Scoring applied to all questions")}>
              Apply to all questions
            </button>
          </div>
        </section>
      )}

      <section className="panel space-y-3">
        <h2 className="heading text-sm text-dim">All events</h2>
        <ul className="divide-y divide-edge">
          {events.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <span>{e.name} <span className="chip ml-1">{e.status}</span> {e.is_active && <span className="chip border-neon/40 text-neon">active</span>}</span>
              {!e.is_active && (
                <span className="flex gap-2">
                  <button className="btn-ghost" onClick={() => run(() => adm(`/events/${e.id}/activate`, { method: "POST" }).then(reloadOverview), "Event activated")}>Activate</button>
                  <button className="btn-danger" onClick={() => window.confirm(`Delete "${e.name}" with all its teams, puzzles and documents?`) && run(() => adm(`/events/${e.id}`, { method: "DELETE" }), "Event deleted")}>Delete</button>
                </span>
              )}
            </li>
          ))}
        </ul>
        <form className="flex gap-2" onSubmit={(ev) => { ev.preventDefault(); run(() => adm("/events", { method: "POST", body: { name: newName } }).then(() => setNewName("")), "Event created"); }}>
          <input className="input" placeholder="New event name" value={newName} onChange={(e) => setNewName(e.target.value)} required minLength={2} />
          <button className="btn-ghost shrink-0">Create</button>
        </form>
      </section>
    </div>
  );
}

function TeamsTab({ notify }) {
  const [teams, run] = useAdmin("/teams", notify);
  if (!teams) return <p className="text-dim">Loading…</p>;
  const patch = (id, body, done) => run(() => adm(`/teams/${id}`, { method: "PATCH", body }), done);

  function adjust(team) {
    const raw = window.prompt(`Adjust ${team.team}'s score by how many points? Use a minus sign to deduct.`, "0");
    const delta = Number(raw);
    if (raw === null || !Number.isInteger(delta) || delta === 0) return;
    const note = window.prompt("Reason (recorded in the score history)", "") || "";
    patch(team.team_id, { score_delta: delta, note }, "Score adjusted");
  }
  function password(team) {
    const value = window.prompt(`New password for ${team.team} (at least 6 characters)`);
    if (value) patch(team.team_id, { new_password: value }, "Password reset");
  }

  return (
    <div className="space-y-5">
    <section className="panel space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="heading text-lg">Teams and scores</h2>
        <button className="btn-ghost" onClick={() => downloadCsv("/api/admin/export.csv", "codehunt-results.csv").catch((e) => notify(e.message, true))}>
          Export CSV
        </button>
      </div>
      {teams.length === 0 && <p className="text-sm text-dim">No teams registered yet.</p>}
      <ul className="space-y-2">
        {teams.map((t) => (
          <li key={t.team_id} className={`rounded-lg border bg-ink p-3 ${t.disqualified ? "border-danger/40 opacity-70" : "border-edge"}`}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="font-semibold">
                <span className="mr-2 font-mono text-dim">#{t.rank}</span>{t.team}
                {t.disqualified && <span className="chip ml-2 border-danger/40 text-danger">disqualified</span>}
                {t.finished && <span className="chip ml-2 border-neon/40 text-neon">finished {formatElapsed(t.elapsed_seconds)}</span>}
              </p>
              <p className="font-mono text-lg font-bold text-amber">{t.score}</p>
            </div>
            <p className="mt-1 text-xs text-dim">
              {t.members.join(", ") || "No members listed"} · solved {t.solved}/{t.total} · wrong {t.wrong_attempts} · hints {t.hints_used}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button className="btn-ghost" onClick={() => adjust(t)}>± Points</button>
              <button className="btn-ghost" onClick={() => password(t)}>Reset password</button>
              <button className="btn-ghost" onClick={() => patch(t.team_id, { disqualified: !t.disqualified }, t.disqualified ? "Team reinstated" : "Team disqualified")}>
                {t.disqualified ? "Reinstate" : "Disqualify"}
              </button>
              <button className="btn-danger" onClick={() => window.confirm(`Wipe all progress for ${t.team}?`) && run(() => adm(`/teams/${t.team_id}/reset`, { method: "POST" }), "Progress reset")}>Reset progress</button>
              <button className="btn-danger" onClick={() => window.confirm(`Delete ${t.team} permanently?`) && run(() => adm(`/teams/${t.team_id}`, { method: "DELETE" }), "Team deleted")}>Delete</button>
            </div>
          </li>
        ))}
      </ul>
    </section>
    <Assignments notify={notify} />
    </div>
  );
}

function Encoder({ notify }) {
  const [form, setForm] = useState({ cipher: "caesar", text: "", key: "" });
  const [encoded, setEncoded] = useState("");
  const needsKey = form.cipher in KEY_HELP;
  async function encode(e) {
    e.preventDefault();
    try {
      setEncoded((await adm("/encode", { method: "POST", body: form })).encoded);
    } catch (err) {
      notify(err.message, true);
    }
  }
  return (
    <form onSubmit={encode} className="panel space-y-3">
      <h2 className="heading text-sm text-dim">Clue encoder</h2>
      <p className="text-xs text-dim">Turns an answer into cipher text. Nothing typed here is saved.</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Cipher">
          <select className="input" value={form.cipher} onChange={(e) => setForm({ ...form, cipher: e.target.value })}>
            {CIPHERS.map((c) => <option key={c}>{c}</option>)}
          </select>
        </Field>
        <Field label="Plain text" className="sm:col-span-2">
          <input className="input" value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} required />
        </Field>
      </div>
      {needsKey && (
        <Field label={`Key: ${KEY_HELP[form.cipher]}`}>
          <textarea className="input" rows={form.cipher === "book" ? 4 : 1} value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} />
        </Field>
      )}
      <button className="btn-ghost">Encode</button>
      {encoded && <pre className="whitespace-pre-wrap break-words rounded-lg border border-edge bg-ink p-3 font-mono text-sm text-neon">{encoded}</pre>}
    </form>
  );
}

function PuzzleCard({ puzzle, run }) {
  const [form, setForm] = useState({ ...puzzle, answers: "" });
  const [hint, setHint] = useState({ text: "", penalty: "" });
  const set = (name) => (e) => setForm({ ...form, [name]: e.target.value });

  function save() {
    const body = {
      stage: Number(form.stage), title: form.title, cipher: form.cipher, prompt: form.prompt,
      encoded_text: form.encoded_text, points: Number(form.points),
    };
    const answers = form.answers.split("|").map((a) => a.trim()).filter(Boolean);
    if (answers.length) body.answers = answers;
    run(() => adm(`/puzzles/${puzzle.id}`, { method: "PATCH", body }).then(() => setForm((f) => ({ ...f, answers: "" }))), `Stage ${form.stage} saved`);
  }

  return (
    <details className="rounded-lg border border-edge bg-ink">
      <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-2 p-3">
        <span className="font-semibold"><span className="mr-2 font-mono text-neon">{String(puzzle.stage).padStart(2, "0")}</span>{puzzle.title}</span>
        <span className="flex gap-2"><span className="chip">{puzzle.cipher}</span><span className="chip">{puzzle.points} pts</span><span className="chip">{puzzle.hints.length} hints</span></span>
      </summary>
      <div className="space-y-3 border-t border-edge p-3">
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Stage"><input className="input" type="number" min="1" value={form.stage} onChange={set("stage")} /></Field>
          <Field label="Title" className="sm:col-span-2"><input className="input" value={form.title} onChange={set("title")} /></Field>
          <Field label="Points"><input className="input" type="number" min="0" value={form.points} onChange={set("points")} /></Field>
        </div>
        <Field label="Cipher">
          <select className="input" value={form.cipher} onChange={set("cipher")}>{CIPHERS.map((c) => <option key={c}>{c}</option>)}</select>
        </Field>
        <Field label="Prompt shown to teams"><textarea className="input" rows={2} value={form.prompt} onChange={set("prompt")} /></Field>
        <Field label="Encoded clue text"><textarea className="input font-mono text-sm" rows={3} value={form.encoded_text} onChange={set("encoded_text")} /></Field>
        <Field label={`New answer(s), separated by | — leave blank to keep the ${puzzle.answer_count} stored`}>
          <input className="input" type="password" autoComplete="off" placeholder="Stored as a hash and never shown again" value={form.answers} onChange={set("answers")} />
        </Field>
        <div className="flex gap-2">
          <button className="btn" onClick={save}>Save stage</button>
          <button className="btn-danger" onClick={() => window.confirm(`Delete stage ${puzzle.stage}? Team progress on it is deleted too.`) && run(() => adm(`/puzzles/${puzzle.id}`, { method: "DELETE" }), "Stage deleted")}>Delete</button>
        </div>

        <div className="space-y-2 border-t border-edge pt-3">
          <h4 className="label">Hints, revealed in this order</h4>
          {puzzle.hints.map((h) => (
            <div key={h.id} className="flex items-start justify-between gap-2 rounded-lg border border-edge p-2 text-sm">
              <p><span className="mr-2 font-mono text-amber">−{h.penalty}</span>{h.text}</p>
              <button className="btn-danger shrink-0" onClick={() => run(() => adm(`/hints/${h.id}`, { method: "DELETE" }), "Hint deleted")}>Remove</button>
            </div>
          ))}
          <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); run(() => adm(`/puzzles/${puzzle.id}/hints`, { method: "POST", body: { text: hint.text, penalty: hint.penalty === "" ? null : Number(hint.penalty) } }).then(() => setHint({ text: "", penalty: "" })), "Hint added"); }}>
            <input className="input" placeholder="New hint" value={hint.text} onChange={(e) => setHint({ ...hint, text: e.target.value })} required />
            <input className="input sm:w-24" type="number" min="0" aria-label="Hint cost" placeholder="auto" title="Blank uses the event's cost for this hint slot" value={hint.penalty} onChange={(e) => setHint({ ...hint, penalty: e.target.value })} />
            <button className="btn-ghost shrink-0">Add hint</button>
          </form>
        </div>
      </div>
    </details>
  );
}

function PuzzlesTab({ notify }) {
  const [puzzles, run] = useAdmin("/puzzles", notify);
  const blank = { stage: "", title: "", cipher: "binary", answers: "" };
  const [form, setForm] = useState(blank);
  if (!puzzles) return <p className="text-dim">Loading…</p>;

  function create(e) {
    e.preventDefault();
    const body = { stage: Number(form.stage), title: form.title, cipher: form.cipher, answers: form.answers.split("|").map((a) => a.trim()).filter(Boolean) };
    run(() => adm("/puzzles", { method: "POST", body }).then(() => setForm(blank)), "Stage created");
  }

  return (
    <div className="space-y-5">
      <section className="panel space-y-2">
        <h2 className="heading text-lg">Puzzles</h2>
        <p className="text-xs text-dim">Answers are write-only. Teams' answers are compared ignoring case, spaces and punctuation.</p>
        {puzzles.map((p) => <PuzzleCard key={p.id} puzzle={p} run={run} />)}
        <form onSubmit={create} className="grid gap-2 border-t border-edge pt-3 sm:grid-cols-5">
          <input className="input" type="number" min="1" placeholder="Stage" value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value })} required />
          <input className="input sm:col-span-2" placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          <select className="input" aria-label="Cipher" value={form.cipher} onChange={(e) => setForm({ ...form, cipher: e.target.value })}>{CIPHERS.map((c) => <option key={c}>{c}</option>)}</select>
          <input className="input" type="password" autoComplete="off" placeholder="Answer" value={form.answers} onChange={(e) => setForm({ ...form, answers: e.target.value })} required />
          <button className="btn-ghost sm:col-span-5">Add stage</button>
        </form>
      </section>
      <Encoder notify={notify} />
    </div>
  );
}

function DocCard({ doc, run }) {
  const [form, setForm] = useState(doc);
  const set = (name) => (e) => setForm({ ...form, [name]: e.target.value });
  return (
    <details className="rounded-lg border border-edge bg-ink">
      <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-2 p-3">
        <span className="font-semibold">{doc.title}</span>
        <span className="flex gap-2">
          <span className={`chip ${doc.kind === "decoy" ? "border-danger/40 text-danger" : "border-neon/40 text-neon"}`}>{doc.kind}</span>
          <span className="chip">{doc.stage === 0 ? "always" : `from stage ${doc.stage}`}</span>
        </span>
      </summary>
      <div className="space-y-3 border-t border-edge p-3">
        <DocFields form={form} set={set} />
        <div className="flex gap-2">
          <button className="btn" onClick={() => run(() => adm(`/documents/${doc.id}`, { method: "PATCH", body: { title: form.title, content: form.content, kind: form.kind, stage: Number(form.stage) } }), "Document saved and re-indexed")}>Save</button>
          <button className="btn-danger" onClick={() => window.confirm(`Delete "${doc.title}"?`) && run(() => adm(`/documents/${doc.id}`, { method: "DELETE" }), "Document deleted")}>Delete</button>
        </div>
      </div>
    </details>
  );
}

function DocFields({ form, set }) {
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="Title" className="sm:col-span-2"><input className="input" value={form.title} onChange={set("title")} required /></Field>
        <Field label="Kind">
          <select className="input" value={form.kind} onChange={set("kind")}><option>genuine</option><option>decoy</option></select>
        </Field>
        <Field label="Unlocks at stage (0 = always)"><input className="input" type="number" min="0" value={form.stage} onChange={set("stage")} /></Field>
      </div>
      <Field label="Content"><textarea className="input" rows={5} value={form.content} onChange={set("content")} required /></Field>
    </>
  );
}

function ArchiveTab({ notify }) {
  const [docs, run] = useAdmin("/documents", notify);
  const blank = { title: "", content: "", kind: "genuine", stage: 0 };
  const [form, setForm] = useState(blank);
  if (!docs) return <p className="text-dim">Loading…</p>;
  return (
    <div className="space-y-5">
      <section className="panel space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="heading text-lg">Oracle archive</h2>
          <button className="btn-ghost" onClick={() => run(() => adm("/documents/reindex", { method: "POST" }), "Archive re-indexed")}>Re-index all</button>
        </div>
        <p className="text-xs text-dim">
          Teams can search everything here through the Oracle once they reach a document's stage. Never put answers,
          locations or the final destination in a document. The genuine/decoy label is for organisers only.
        </p>
        {docs.map((d) => <DocCard key={d.id} doc={d} run={run} />)}
      </section>
      <form className="panel space-y-3" onSubmit={(e) => { e.preventDefault(); run(() => adm("/documents", { method: "POST", body: { ...form, stage: Number(form.stage) } }).then(() => setForm(blank)), "Document added and indexed"); }}>
        <h2 className="heading text-sm text-dim">Add a document</h2>
        <DocFields form={form} set={(name) => (e) => setForm({ ...form, [name]: e.target.value })} />
        <button className="btn-ghost">Add document</button>
      </form>
    </div>
  );
}

export default function Admin() {
  const [signedIn, setSignedIn] = useState(Boolean(adminSession.get()));
  // The open tab lives in the URL (#Map), so a refresh or a shared link lands on the same tab.
  const [tab, setTabState] = useState(() => TABS.find((t) => t === window.location.hash.slice(1)) || "Event");
  const setTab = (name) => {
    window.history.replaceState(null, "", `#${name}`);
    setTabState(name);
  };
  const [notice, setNotice] = useState(null);

  const notify = useCallback((text, isError = false) => {
    setNotice({ text, isError });
    if (!adminSession.get()) setSignedIn(false);
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  if (!signedIn) return <AdminLogin onDone={() => setSignedIn(true)} />;
  const Tab = { Event: EventTab, People: PeopleTab, Teams: TeamsTab, Puzzles: PuzzlesTab, Archive: ArchiveTab, Map: MapTab, History: HistoryTab }[tab];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="heading text-xl text-amber">Control room</h1>
        <button className="btn-ghost" onClick={() => { adminSession.clear(); setSignedIn(false); }}>Sign out</button>
      </div>
      <div className="flex gap-1 overflow-x-auto border-b border-edge" role="tablist">
        {TABS.map((name) => (
          <button key={name} role="tab" aria-selected={tab === name} onClick={() => setTab(name)}
            className={`shrink-0 border-b-2 px-3 py-2 font-mono text-xs uppercase tracking-wider ${tab === name ? "border-amber text-amber" : "border-transparent text-dim hover:text-slate-100"}`}>
            {name}
          </button>
        ))}
      </div>
      {notice && (
        <p role="status" className={`rounded-lg border px-3 py-2 text-sm ${notice.isError ? "border-danger/40 bg-danger/10 text-danger" : "border-neon/40 bg-neon/10 text-neon"}`}>
          {notice.text}
        </p>
      )}
      <Tab notify={notify} />
    </div>
  );
}
