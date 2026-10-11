import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, teamSession } from "../api.js";

export default function Auth({ mode }) {
  const registering = mode === "register";
  const navigate = useNavigate();
  const [form, setForm] = useState({ team_name: "", password: "", members: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [event, setEvent] = useState(null);

  useEffect(() => {
    api("/api/event").then(setEvent).catch(() => {});
  }, []);
  const solo = event?.team_size === 1;
  const closed = registering && event && !event.registration_open;

  const field = (name) => ({
    value: form[name],
    onChange: (e) => setForm({ ...form, [name]: e.target.value }),
  });

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const body = { team_name: form.team_name, password: form.password };
      if (registering) body.members = form.members.split(",").map((m) => m.trim()).filter(Boolean);
      const data = await api(`/api/auth/${registering ? "register" : "login"}`, { method: "POST", body });
      teamSession.set({ token: data.token, name: data.team.name });
      window.dispatchEvent(new Event("codehunt-session"));
      navigate("/play");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="panel mx-auto mt-6 max-w-md space-y-4">
      <h1 className="heading text-xl text-neon">{registering ? (solo ? "Register to play" : "Register your team") : "Sign in"}</h1>
      {closed && <p className="rounded-lg border border-amber/40 bg-amber/10 px-3 py-2 text-sm text-amber">Registration is closed. Ask an organiser for your sign-in details.</p>}
      <div>
        <label className="label" htmlFor="team">{solo ? "Your name" : "Team name"}</label>
        <input id="team" className="input" required minLength={2} maxLength={40} autoComplete="username" {...field("team_name")} />
      </div>
      <div>
        <label className="label" htmlFor="password">Password</label>
        <input id="password" type="password" className="input" required minLength={6} maxLength={128}
          autoComplete={registering ? "new-password" : "current-password"} {...field("password")} />
        {registering && <p className="mt-1 text-xs text-dim">At least 6 characters.{solo ? "" : " Share it with your teammates only."}</p>}
      </div>
      {registering && !solo && (
        <div>
          <label className="label" htmlFor="members">Members (comma separated{event ? `, up to ${event.team_size}` : ""})</label>
          <input id="members" className="input" placeholder="Asha, Ravi, Meera" {...field("members")} />
        </div>
      )}
      {error && <p role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}
      <button className="btn w-full" disabled={busy || closed}>{busy ? "Working…" : registering ? "Create team" : "Sign in"}</button>
      <p className="text-center text-sm text-dim">
        {registering ? "Already registered? " : "Not registered yet? "}
        <Link className="text-neon hover:underline" to={registering ? "/login" : "/register"}>
          {registering ? "Sign in" : "Register"}
        </Link>
      </p>
    </form>
  );
}
