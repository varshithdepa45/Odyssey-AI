import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatElapsed } from "../api.js";
import OracleChat from "../components/OracleChat.jsx";

const CIPHER_NAMES = {
  binary: "Binary", morse: "Morse", caesar: "Caesar", polybius: "Polybius", vigenere: "Vigenère",
  hex: "Hexadecimal", braille: "Braille", ascii: "ASCII decimal", book: "Book cipher",
};
const STATUS_NOTES = {
  draft: "The hunt has not started yet. Your questions appear here the moment it goes live.",
  paused: "The hunt is paused. Hold your position.",
  ended: "The hunt has ended. Thanks for playing.",
};
const LEDGER_LABELS = { correct: "Solved", wrong: "Wrong answer", hint: "Hint", bonus: "Bonus", adjust: "Adjustment" };

function Countdown({ endsAt }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const left = Math.max(Math.floor((new Date(endsAt).getTime() - now) / 1000), 0);
  return (
    <div className="text-right">
      <p className="label mb-0">Time left</p>
      <p className={`font-mono text-xl font-bold ${left < 300 ? "text-danger" : "text-cyan"}`}>{formatElapsed(left)}</p>
    </div>
  );
}

function StageTrack({ stages }) {
  return (
    <ol className="flex flex-wrap items-center gap-1.5" aria-label="Question progress">
      {stages.map((s) => (
        <li
          key={s.stage}
          aria-label={`Question ${s.stage}: ${s.status}`}
          className={`flex h-8 min-w-8 flex-1 items-center justify-center rounded-md border font-mono text-xs font-bold ${
            s.status === "solved"
              ? "border-neon bg-neon text-ink"
              : s.status === "current"
              ? "animate-pulse border-cyan text-cyan"
              : "border-edge text-dim/50"
          }`}
        >
          {s.status === "solved" ? "✓" : s.stage}
        </li>
      ))}
    </ol>
  );
}

function CurrentStage({ stage, total, live, onChange }) {
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      // `stage` tells the server which question this answer is for, so a double tap can never be
      // judged (and penalised) against the next question.
      const result = await api("/api/game/submit", { method: "POST", body: { answer, stage: stage.stage }, as: "team" });
      setFeedback({ ok: result.correct, text: result.correct ? `${result.message} +${result.points_awarded} points.` : result.message });
      if (result.correct) setAnswer("");
      await onChange();
    } catch (err) {
      setFeedback({ ok: false, text: err.message });
      if (err.status === 409) await onChange();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel space-y-5 border-cyan/40">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-cyan">Question {stage.stage} of {total}</p>
          <h2 className="heading mt-1 text-xl sm:text-2xl">{stage.title}</h2>
        </div>
        <div className="flex gap-2">
          <span className="chip border-cyan/40 text-cyan">{CIPHER_NAMES[stage.cipher] || stage.cipher}</span>
          <span className="chip border-amber/40 text-amber" title="Points for this question, less penalties already paid">
            Net {stage.potential_points} / {stage.points}
          </span>
        </div>
      </div>
      {stage.prompt && <p className="text-sm text-slate-300">{stage.prompt}</p>}
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-edge bg-ink p-4 font-mono text-sm leading-relaxed text-neon sm:text-base">
        {stage.encoded_text}
      </pre>

      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <label className="sr-only" htmlFor="answer">Your answer</label>
        <input id="answer" className="input font-mono uppercase" placeholder="Decoded phrase" value={answer}
          onChange={(e) => setAnswer(e.target.value)} maxLength={200} autoComplete="off" disabled={!live} />
        <button className="btn shrink-0" disabled={busy || !live || !answer.trim()}>Submit</button>
      </form>
      {feedback && (
        <p role="status" className={`rounded-lg border px-3 py-2 text-sm ${feedback.ok ? "border-neon/40 bg-neon/10 text-neon" : "border-danger/40 bg-danger/10 text-danger"}`}>
          {feedback.text}
        </p>
      )}
      {stage.wrong_attempts > 0 && <p className="text-xs text-dim">Wrong attempts on this question: {stage.wrong_attempts}</p>}

      {stage.hints.length > 0 && (
        <div className="space-y-2 border-t border-edge pt-4">
          <h3 className="label mb-0">Hints revealed {stage.hints.length}/{stage.hints_total}</h3>
          {stage.hints.map((hint) => (
            <p key={hint.number} className="rounded-lg border border-amber/30 bg-amber/5 px-3 py-2 text-sm text-amber">
              <span className="mr-2 font-mono text-xs">#{hint.number}</span>{hint.text}
            </p>
          ))}
        </div>
      )}
      <p className="text-xs text-dim">
        Stuck? Ask the Oracle for a technique or a hint. Solved it? <Link to="/map" className="text-neon hover:underline">Check the map</Link>.
      </p>
    </section>
  );
}

function Finale({ game }) {
  return (
    <section className="panel border-neon text-center">
      <p className="font-mono text-xs uppercase tracking-[0.3em] text-neon">Every question cleared</p>
      <h2 className="heading mt-2 text-3xl text-neon sm:text-5xl">Hunt complete</h2>
      <p className="mt-3 text-dim">
        {game.team.name} finished with <span className="font-mono font-bold text-amber">{game.team.score}</span> points.
      </p>
      {game.final_message && (
        <p className="mx-auto mt-5 max-w-xl rounded-lg border border-neon/40 bg-neon/5 p-4 text-left text-slate-100">{game.final_message}</p>
      )}
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        <Link to="/map" className="btn">Open the map</Link>
        <Link to="/leaderboard" className="btn-ghost">Leaderboard</Link>
      </div>
    </section>
  );
}

function ScoreHistory({ version }) {
  const [history, setHistory] = useState(null);
  useEffect(() => {
    api("/api/game/history", { as: "team" }).then(setHistory).catch(() => {});
  }, [version]);
  if (!history || history.events.length === 0) return null;
  return (
    <details className="panel">
      <summary className="label mb-0 cursor-pointer">Score history ({history.events.length})</summary>
      <ul className="mt-3 divide-y divide-edge text-sm">
        {history.events.map((e, i) => (
          <li key={i} className="flex items-center justify-between gap-3 py-1.5">
            <span><span className="chip mr-2">{LEDGER_LABELS[e.kind] || e.kind}</span>{e.note}</span>
            <span className={`shrink-0 font-mono font-bold ${e.delta < 0 ? "text-danger" : "text-neon"}`}>{e.delta > 0 ? "+" : ""}{e.delta}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

export default function Dashboard() {
  const [game, setGame] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setGame(await api("/api/game", { as: "team" }));
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 15000); // picks up go-live, pause and admin changes
    return () => clearInterval(timer);
  }, [load]);

  if (!game) return <p className="text-center text-dim">{error || "Loading the hunt…"}</p>;

  const { event, team, stages } = game;
  const current = stages.find((s) => s.status === "current" && s.title);
  const solved = stages.filter((s) => s.status === "solved" && s.title);
  const finished = Boolean(team.finished_at);
  const live = event.status === "live";

  return (
    <div className="space-y-5">
      <section className="panel space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="label mb-0">{event.name}</p>
            <h1 className="heading text-2xl">{team.name}</h1>
            {team.members.length > 0 && team.members.join("") !== team.name && <p className="text-xs text-dim">{team.members.join(" · ")}</p>}
          </div>
          <div className="flex items-end gap-6">
            {live && event.ends_at && <Countdown endsAt={event.ends_at} />}
            <div className="text-right">
              <p className="label mb-0">Score</p>
              <p className="font-mono text-3xl font-bold text-amber">{team.score}</p>
            </div>
          </div>
        </div>
        {stages.length > 0 ? <StageTrack stages={stages} /> : <p className="text-sm text-dim">No questions are assigned to your team yet.</p>}
      </section>

      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {!live && <p className="rounded-lg border border-amber/40 bg-amber/10 px-4 py-3 text-sm text-amber">{STATUS_NOTES[event.status]}</p>}

      <div className="grid items-start gap-5 lg:grid-cols-5">
        <div className="space-y-5 lg:col-span-3">
          {finished ? <Finale game={game} /> : current && <CurrentStage key={current.stage} stage={current} total={stages.length} live={live} onChange={load} />}
          {solved.length > 0 && (
            <section className="panel">
              <h2 className="label">Cleared questions</h2>
              <ul className="divide-y divide-edge">
                {solved.map((s) => (
                  <li key={s.stage} className="flex items-center justify-between gap-3 py-2 text-sm">
                    <span><span className="font-mono text-neon">{String(s.stage).padStart(2, "0")}</span> {s.title}</span>
                    <span className="font-mono text-amber" title="Net of hints and wrong answers">+{s.points_awarded}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <ScoreHistory version={team.score} />
        </div>
        <div className="lg:sticky lg:top-4 lg:col-span-2">
          <OracleChat stage={finished ? null : current || null} live={live} onScoreChange={load} />
        </div>
      </div>
    </div>
  );
}
