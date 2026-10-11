import { lazy, Suspense, useEffect, useState } from "react";
import { api } from "../api.js";
import SchematicMap, { MARKER_STYLES } from "../components/SchematicMap.jsx";

// Leaflet is only downloaded when the event actually uses the real-world map.
const LeafletMap = lazy(() => import("../components/LeafletMap.jsx"));

export default function MapPage() {
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const load = () =>
      api("/api/map", { as: "team" })
        .then((d) => active && (setData(d), setError("")))
        .catch((err) => active && setError(err.message));
    load();
    const timer = setInterval(load, 20000); // newly unlocked markers appear without a refresh
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  if (!data) return <p className="text-center text-dim">{error || "Loading the map…"}</p>;

  const { markers, provider } = data;
  const chosen = selected != null ? markers[selected] : null;
  const unplaced = provider === "osm" ? markers.filter((m) => m.lat == null).length : 0;

  return (
    <div className="space-y-4">
      <section className="panel !py-4">
        <p className="label mb-1">Next step</p>
        <p className="text-sm text-slate-200">{data.next_step}</p>
      </section>

      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {provider === "osm" ? (
            <Suspense fallback={<div className="flex aspect-[4/3] items-center justify-center rounded-xl border border-edge text-dim">Loading map…</div>}>
              <LeafletMap center={data.center} markers={markers} selected={selected} onSelect={setSelected} />
            </Suspense>
          ) : (
            <SchematicMap imageUrl={provider === "image" ? data.image_url : ""} markers={markers} selected={selected} onSelect={setSelected} />
          )}
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-dim">
            {Object.entries(MARKER_STYLES).map(([kind, style]) => (
              <span key={kind} className="flex items-center gap-1.5"><span className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />{style.label}</span>
            ))}
            {unplaced > 0 && <span>{unplaced} marker{unplaced > 1 ? "s" : ""} listed without a map position</span>}
          </div>
          {error && <p role="alert" className="mt-2 text-xs text-danger">{error}</p>}
        </div>

        <section className="panel !p-0">
          <h1 className="heading border-b border-edge px-4 py-3 text-sm text-neon">Unlocked places ({markers.length})</h1>
          <ul className="max-h-[28rem] divide-y divide-edge overflow-y-auto">
            {markers.map((m, i) => {
              const style = MARKER_STYLES[m.kind] || MARKER_STYLES.landmark;
              return (
                <li key={i}>
                  <button className={`w-full px-4 py-3 text-left transition hover:bg-raised ${selected === i ? "bg-raised" : ""}`} onClick={() => setSelected(selected === i ? null : i)}>
                    <span className="flex items-center gap-2 text-sm font-semibold">
                      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${style.dot}`} />{m.name}
                    </span>
                    {selected === i && (
                      <span className="mt-2 block space-y-2 text-sm text-slate-300">
                        {m.description && <span className="block">{m.description}</span>}
                        {m.directions && (
                          <span className="block rounded-lg border border-edge bg-ink p-2.5">
                            <span className="label mb-1">How to get there</span>{m.directions}
                          </span>
                        )}
                      </span>
                    )}
                  </button>
                  {selected === i && m.lat != null && m.lng != null && (
                    <a className="mx-4 mb-3 inline-block font-mono text-xs uppercase tracking-wide text-neon hover:underline" target="_blank" rel="noreferrer"
                      href={`https://www.google.com/maps/dir/?api=1&destination=${m.lat},${m.lng}&travelmode=walking`}>
                      Walking directions ↗
                    </a>
                  )}
                </li>
              );
            })}
            {markers.length === 0 && <li className="px-4 py-6 text-center text-sm text-dim">Nothing unlocked yet.</li>}
          </ul>
          <p className="border-t border-edge px-4 py-3 text-xs text-dim">
            More places appear as you solve questions.{chosen ? "" : " Tap a place for directions."}
          </p>
        </section>
      </div>
    </div>
  );
}
