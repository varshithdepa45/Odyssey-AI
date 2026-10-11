import { useEffect, useState } from "react";
import SchematicMap from "../../components/SchematicMap.jsx";
import { adm, Field, useAdmin } from "./shared.jsx";

const UNLOCKS = {
  always: "Always visible",
  stage_reached: "When a team reaches question…",
  stage_solved: "When a team solves question…",
  finished: "When a team finishes everything",
};
const BLANK = { name: "", description: "", directions: "", kind: "landmark", unlock: "always", unlock_stage: "", x: 50, y: 50, lat: "", lng: "" };
const number = (value) => (value === "" || value == null ? null : Number(value));

function MarkerForm({ form, setForm }) {
  const set = (name) => (e) => setForm({ ...form, [name]: e.target.value });
  const staged = form.unlock === "stage_reached" || form.unlock === "stage_solved";
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Name" className="sm:col-span-2"><input className="input" value={form.name} onChange={set("name")} required /></Field>
        <Field label="Kind">
          <select className="input" value={form.kind} onChange={set("kind")}><option value="landmark">Landmark</option><option value="clue">Checkpoint</option><option value="final">Final destination</option></select>
        </Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Visible" className="sm:col-span-2">
          <select className="input" value={form.unlock} onChange={set("unlock")}>{Object.entries(UNLOCKS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        </Field>
        {staged && <Field label="Question number"><input className="input" type="number" min="1" value={form.unlock_stage ?? ""} onChange={set("unlock_stage")} required /></Field>}
      </div>
      <Field label="Description"><input className="input" value={form.description} onChange={set("description")} /></Field>
      <Field label="How to get there"><textarea className="input" rows={2} value={form.directions} onChange={set("directions")} /></Field>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="X %"><input className="input" type="number" min="0" max="100" step="0.1" value={form.x} onChange={set("x")} /></Field>
        <Field label="Y %"><input className="input" type="number" min="0" max="100" step="0.1" value={form.y} onChange={set("y")} /></Field>
        <Field label="Latitude"><input className="input" type="number" step="any" placeholder="OSM only" value={form.lat ?? ""} onChange={set("lat")} /></Field>
        <Field label="Longitude"><input className="input" type="number" step="any" placeholder="OSM only" value={form.lng ?? ""} onChange={set("lng")} /></Field>
      </div>
    </div>
  );
}

const body = (f) => ({
  name: f.name, description: f.description, directions: f.directions, kind: f.kind, unlock: f.unlock,
  unlock_stage: number(f.unlock_stage), x: Number(f.x), y: Number(f.y), lat: number(f.lat), lng: number(f.lng),
});

export default function MapTab({ notify }) {
  const [markers, run] = useAdmin("/markers", notify);
  const [events, runEvent] = useAdmin("/events", notify);
  const [editing, setEditing] = useState(null); // index into markers, or "new"
  const [form, setForm] = useState(BLANK);
  const [config, setConfig] = useState(null);
  const active = events?.find((e) => e.is_active);

  useEffect(() => {
    if (active) setConfig({ map_provider: active.map_provider, map_image_url: active.map_image_url, map_lat: active.map_lat ?? "", map_lng: active.map_lng ?? "", map_zoom: active.map_zoom });
  }, [active?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!markers || !config) return <p className="text-dim">Loading…</p>;

  const open = (index) => { setEditing(index); setForm(index === "new" ? BLANK : { ...markers[index] }); };
  const preview = editing === "new" ? [...markers, form] : markers.map((m, i) => (i === editing ? { ...m, ...form } : m));
  const selected = editing === "new" ? markers.length : editing;
  const setCfg = (name) => (e) => setConfig({ ...config, [name]: e.target.value });

  function save() {
    const done = () => setEditing(null);
    if (editing === "new") run(() => adm("/markers", { method: "POST", body: body(form) }).then(done), "Marker added");
    else run(() => adm(`/markers/${markers[editing].id}`, { method: "PATCH", body: body(form) }).then(done), "Marker saved");
  }

  return (
    <div className="space-y-5">
      <section className="panel space-y-3">
        <h2 className="heading text-lg">Map source</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Provider">
            <select className="input" value={config.map_provider} onChange={setCfg("map_provider")}>
              <option value="placeholder">Placeholder schematic</option>
              <option value="image">Campus map image</option>
              <option value="osm">OpenStreetMap (real world)</option>
            </select>
          </Field>
          {config.map_provider === "image" && (
            <Field label="Image URL (https)" className="sm:col-span-2"><input className="input" placeholder="https://…/campus-map.png" value={config.map_image_url} onChange={setCfg("map_image_url")} /></Field>
          )}
          {config.map_provider === "osm" && (
            <>
              <Field label="Centre latitude"><input className="input" type="number" step="any" value={config.map_lat} onChange={setCfg("map_lat")} /></Field>
              <Field label="Centre longitude"><input className="input" type="number" step="any" value={config.map_lng} onChange={setCfg("map_lng")} /></Field>
              <Field label="Zoom (1–22)"><input className="input" type="number" min="1" max="22" value={config.map_zoom} onChange={setCfg("map_zoom")} /></Field>
            </>
          )}
        </div>
        <p className="text-xs text-dim">
          {config.map_provider === "placeholder" && "A generic schematic until you have real map data. Marker positions use X/Y percentages."}
          {config.map_provider === "image" && "Host your campus map image anywhere public and paste its URL. Markers use X/Y percentages of the image; click the preview to place them."}
          {config.map_provider === "osm" && "Uses OpenStreetMap tiles, no key needed. Only markers with a latitude and longitude are drawn; the rest appear in the list."}
        </p>
        <button className="btn-ghost" onClick={() => runEvent(() => adm(`/events/${active.id}`, { method: "PATCH", body: {
          map_provider: config.map_provider, map_image_url: config.map_image_url,
          ...(config.map_lat !== "" && config.map_lng !== "" ? { map_lat: Number(config.map_lat), map_lng: Number(config.map_lng) } : {}),
          map_zoom: Number(config.map_zoom) || 17,
        } }), "Map source saved")}>Save map source</button>
      </section>

      <div className="grid items-start gap-5 lg:grid-cols-2">
        <section className="panel space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="heading text-lg">Markers ({markers.length})</h2>
            <button className="btn-ghost" onClick={() => open("new")}>Add marker</button>
          </div>
          <p className="text-xs text-dim">Organisers see every marker here. Players receive only the ones their progress has unlocked.</p>
          <ul className="max-h-96 divide-y divide-edge overflow-y-auto">
            {markers.map((m, i) => (
              <li key={m.id}>
                <button className={`flex w-full flex-wrap items-center justify-between gap-2 px-1 py-2 text-left text-sm hover:bg-raised ${editing === i ? "bg-raised" : ""}`} onClick={() => open(i)}>
                  <span className="font-semibold">{m.name}</span>
                  <span className={`chip ${m.unlock === "always" ? "" : "border-amber/40 text-amber"}`}>
                    {m.unlock === "always" ? "public" : m.unlock === "finished" ? "after finish" : `${m.unlock === "stage_solved" ? "solve" : "reach"} Q${m.unlock_stage}`}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel space-y-3">
          <h2 className="heading text-sm text-dim">{editing === null ? "Preview (all markers)" : "Click the map to place this marker"}</h2>
          <SchematicMap
            imageUrl={config.map_provider === "image" ? config.map_image_url : ""} markers={preview} selected={selected}
            onSelect={(i) => i < markers.length && open(i)}
            onPick={editing === null ? undefined : (x, y) => setForm((f) => ({ ...f, x, y }))}
          />
          {editing !== null && (
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save(); }}>
              <MarkerForm form={form} setForm={setForm} />
              <div className="flex flex-wrap gap-2">
                <button className="btn">{editing === "new" ? "Add marker" : "Save marker"}</button>
                <button type="button" className="btn-ghost" onClick={() => setEditing(null)}>Cancel</button>
                {editing !== "new" && (
                  <button type="button" className="btn-danger" onClick={() => window.confirm(`Delete "${markers[editing].name}"?`) && run(() => adm(`/markers/${markers[editing].id}`, { method: "DELETE" }).then(() => setEditing(null)), "Marker deleted")}>Delete</button>
                )}
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}
