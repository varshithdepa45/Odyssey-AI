import { Link } from "react-router-dom";

const STEPS = [
  ["01", "Decode", "Nine stages, nine classic ciphers. Each one hides a phrase."],
  ["02", "Consult", "Ask the Oracle. Its archive holds the keys, and a few lies."],
  ["03", "Outrun", "Score counts first, then speed. Hints and wrong guesses cost points."],
];

export default function Home({ team }) {
  return (
    <div className="space-y-10 py-6 sm:py-12">
      <section className="text-center">
        <p className="chip border-neon/40 text-neon">AI-powered campus treasure hunt</p>
        <h1 className="heading mt-5 text-3xl leading-tight tracking-wide sm:text-6xl sm:tracking-widest">
          Crack the <span className="text-neon">code</span>.<br />Find the <span className="text-cyan">trail</span>.
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-dim">
          Gather your team, break nine ciphers, and race the rest of campus to the final destination.
        </p>
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          {team ? (
            <Link to="/play" className="btn">Continue the hunt</Link>
          ) : (
            <>
              <Link to="/register" className="btn">Register a team</Link>
              <Link to="/login" className="btn-ghost">Sign in</Link>
            </>
          )}
          <Link to="/leaderboard" className="btn-ghost">Leaderboard</Link>
        </div>
      </section>
      <section className="grid gap-4 sm:grid-cols-3">
        {STEPS.map(([number, title, text]) => (
          <div key={number} className="panel">
            <p className="font-mono text-xs text-neon">{number}</p>
            <h2 className="heading mt-1 text-lg">{title}</h2>
            <p className="mt-2 text-sm text-dim">{text}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
