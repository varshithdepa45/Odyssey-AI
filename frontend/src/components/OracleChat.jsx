import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const QUICK = ["How does this cipher work?", "How does scoring work?", "What should we do next?"];

function Bubble({ message }) {
  if (message.from === "team") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[88%] whitespace-pre-wrap break-words rounded-2xl rounded-br-sm bg-neon/15 px-3.5 py-2 text-sm text-slate-100">{message.text}</p>
      </div>
    );
  }
  const hint = message.kind === "hint";
  const blocked = message.kind === "blocked";
  return (
    <div className="flex justify-start gap-2">
      <span aria-hidden className={`mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-mono text-[10px] font-bold ${hint ? "bg-amber text-ink" : "bg-cyan/20 text-cyan"}`}>
        {hint ? "!" : "O"}
      </span>
      <div className={`max-w-[88%] rounded-2xl rounded-bl-sm border px-3.5 py-2 text-sm ${hint ? "border-amber/40 bg-amber/10 text-amber" : blocked ? "border-edge bg-raised text-dim" : "border-edge bg-raised text-slate-200"}`}>
        {hint && (
          <p className="mb-1 font-mono text-[11px] uppercase tracking-wider">
            {message.title}{message.charged != null && ` · ${message.charged ? `−${message.charged} points` : "no charge"}`}
          </p>
        )}
        <p className="whitespace-pre-wrap break-words">{message.text}</p>
        {message.sources?.length > 0 && (
          <p className="mt-2 flex flex-wrap gap-1">{message.sources.map((title) => <span key={title} className="chip">{title}</span>)}</p>
        )}
      </div>
    </div>
  );
}

/**
 * The dashboard chatbot. `stage` is the team's current question from /api/game (or null), which
 * carries the next hint and its price; `onScoreChange` reloads the game after a hint is charged.
 */
export default function OracleChat({ stage, live, onScoreChange }) {
  const [messages, setMessages] = useState([]);
  const [remaining, setRemaining] = useState(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(null); // the hint offer awaiting a yes or no
  const scroller = useRef(null);
  const offer = stage?.next_hint || null;

  useEffect(() => {
    api("/api/chat/history", { as: "team" })
      .then((data) => {
        setMessages(data.messages.flatMap((m) =>
          m.kind === "hint"
            ? [{ from: "oracle", kind: "hint", title: m.question.replace(" requested", ""), text: m.answer }]
            : [{ from: "team", text: m.question }, { from: "oracle", kind: m.kind, text: m.answer }]
        ));
        setRemaining(data.remaining);
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    // Scroll the message list only, so the page itself does not jump on a phone.
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [messages, busy, confirming]);

  useEffect(() => setConfirming(null), [stage?.stage]); // an offer for a solved question is void

  async function ask(question) {
    if (question.length < 2 || busy) return;
    setInput("");
    setError("");
    setBusy(true);
    setMessages((list) => [...list, { from: "team", text: question }]);
    try {
      const reply = await api("/api/chat", { method: "POST", body: { message: question }, as: "team" });
      setMessages((list) => [...list, { from: "oracle", kind: reply.mode === "blocked" ? "blocked" : "chat", text: reply.answer, sources: reply.sources }]);
      setRemaining(reply.remaining);
      if (reply.hint_offer) setConfirming(reply.hint_offer);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function revealHint() {
    const wanted = confirming;
    setError("");
    setBusy(true);
    try {
      // Sending the hint number makes this safe to retry: the server never charges twice for one hint.
      const result = await api("/api/game/hint", { method: "POST", body: { number: wanted.number }, as: "team" });
      setMessages((list) => [...list, {
        from: "oracle", kind: "hint", title: `Hint ${result.hint.number}`, text: result.hint.text, charged: result.charged,
      }]);
      setConfirming(null);
      await onScoreChange?.();
    } catch (err) {
      setError(`${err.message} No points were taken.`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel flex h-[32rem] flex-col !p-0 lg:h-[calc(100dvh-8rem)] lg:max-h-[46rem]" aria-label="Oracle chatbot">
      <header className="flex items-center justify-between gap-2 border-b border-edge px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span aria-hidden className="relative flex h-8 w-8 items-center justify-center rounded-full bg-cyan/15 font-mono text-sm font-bold text-cyan">
            O<span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-panel bg-neon" />
          </span>
          <div>
            <h2 className="heading text-sm text-cyan">Oracle</h2>
            <p className="text-[11px] text-dim">Rules, techniques and hints. Never answers.</p>
          </div>
        </div>
        {remaining != null && <span className="chip shrink-0">{remaining} left</span>}
      </header>

      <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto px-4 py-4" aria-live="polite">
        {messages.length === 0 && !busy && (
          <p className="px-2 pt-6 text-center text-sm text-dim">
            Ask how a cipher works, what the rules are, or what to do next. The archive holds a few unreliable
            records, so cross-check what it tells you.
          </p>
        )}
        {messages.map((m, i) => <Bubble key={i} message={m} />)}
        {busy && <p className="pl-8 font-mono text-xs text-cyan">Oracle is thinking…</p>}
        {confirming && (
          <div role="alertdialog" aria-label="Confirm hint" className="ml-8 rounded-xl border border-amber/50 bg-amber/10 p-3">
            <p className="text-sm text-amber">
              Reveal <strong>Hint {confirming.number} of {confirming.total}</strong> for{" "}
              <strong>{confirming.cost} points</strong>? Points are taken only when the hint is delivered.
            </p>
            <div className="mt-2.5 flex flex-wrap gap-2">
              <button className="btn !bg-amber !px-3 !py-2 !text-xs" onClick={revealHint} disabled={busy}>
                Reveal for −{confirming.cost}
              </button>
              <button className="btn-ghost" onClick={() => setConfirming(null)} disabled={busy}>Keep my points</button>
            </div>
          </div>
        )}
      </div>

      <div className="space-y-2 border-t border-edge px-4 py-3">
        {error && <p role="alert" className="text-xs text-danger">{error}</p>}
        <div className="flex gap-1.5 overflow-x-auto pb-0.5">
          {offer && (
            <button className="chip shrink-0 border-amber/50 !text-amber hover:bg-amber/10 disabled:opacity-40"
              onClick={() => setConfirming(offer)} disabled={busy || !live}>
              Hint {offer.number}/{offer.total} · −{offer.cost}
            </button>
          )}
          {stage && !offer && stage.hints_total > 0 && <span className="chip shrink-0">All hints used</span>}
          {QUICK.map((q) => (
            <button key={q} className="chip shrink-0 hover:border-cyan hover:text-cyan disabled:opacity-40" onClick={() => ask(q)} disabled={busy || !live}>
              {q}
            </button>
          ))}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); ask(input.trim()); }} className="flex gap-2">
          <label className="sr-only" htmlFor="oracle-input">Message the Oracle</label>
          <input id="oracle-input" className="input" placeholder={live ? "Ask the Oracle…" : "Available while the hunt is live"} value={input}
            onChange={(e) => setInput(e.target.value)} maxLength={500} autoComplete="off" disabled={!live} />
          <button className="btn shrink-0" disabled={busy || !live || input.trim().length < 2}>Send</button>
        </form>
      </div>
    </section>
  );
}
