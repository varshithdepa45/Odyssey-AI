import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { teamSession } from "./api.js";
import Admin from "./pages/Admin.jsx";
import Auth from "./pages/Auth.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Home from "./pages/Home.jsx";
import Leaderboard from "./pages/Leaderboard.jsx";
import MapPage from "./pages/Map.jsx";

function useTeam() {
  const [team, setTeam] = useState(teamSession.get());
  useEffect(() => {
    const sync = () => setTeam(teamSession.get());
    window.addEventListener("codehunt-session", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("codehunt-session", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return team;
}

function NavItem({ to, children }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `rounded-md px-2.5 py-1.5 font-mono text-xs uppercase tracking-wider transition sm:text-sm ${
          isActive ? "bg-neon/10 text-neon" : "text-dim hover:text-slate-100"
        }`
      }
    >
      {children}
    </NavLink>
  );
}

export default function App() {
  const team = useTeam();
  const navigate = useNavigate();

  function signOut() {
    teamSession.clear();
    window.dispatchEvent(new Event("codehunt-session"));
    navigate("/");
  }

  const guarded = (page) => (team ? page : <Navigate to="/login" replace />);

  return (
    <div className="mx-auto flex min-h-dvh max-w-6xl flex-col px-4">
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-edge py-3">
        <Link to="/" className="heading text-lg text-neon">
          Code<span className="text-slate-100">Hunt</span>
        </Link>
        <nav className="flex flex-wrap items-center gap-1">
          {team && <NavItem to="/play">Play</NavItem>}
          {team && <NavItem to="/map">Map</NavItem>}
          <NavItem to="/leaderboard">Ranks</NavItem>
          {team ? (
            <button onClick={signOut} className="px-2.5 py-1.5 font-mono text-xs uppercase tracking-wider text-dim hover:text-danger sm:text-sm">
              Exit
            </button>
          ) : (
            <NavItem to="/login">Sign in</NavItem>
          )}
        </nav>
      </header>
      <main className="flex-1 py-6">
        <Routes>
          <Route path="/" element={<Home team={team} />} />
          <Route path="/login" element={team ? <Navigate to="/play" replace /> : <Auth mode="login" />} />
          <Route path="/register" element={team ? <Navigate to="/play" replace /> : <Auth mode="register" />} />
          <Route path="/play" element={guarded(<Dashboard />)} />
          <Route path="/map" element={guarded(<MapPage />)} />
          <Route path="/oracle" element={<Navigate to="/play" replace />} />
          <Route path="/leaderboard" element={<Leaderboard team={team} />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <footer className="border-t border-edge py-4 text-center font-mono text-[11px] uppercase tracking-widest text-dim">
        Decode. Explore. Outrun.
      </footer>
    </div>
  );
}
