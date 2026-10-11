import { useRef, useState } from "react";

export const MARKER_STYLES = {
  landmark: { dot: "bg-cyan", ring: "ring-cyan/40", text: "text-cyan", label: "Landmark" },
  clue: { dot: "bg-neon", ring: "ring-neon/40", text: "text-neon", label: "Checkpoint" },
  final: { dot: "bg-amber", ring: "ring-amber/40", text: "text-amber", label: "Final" },
};

function PlaceholderArt() {
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden>
      <defs>
        <pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse">
          <path d="M10 0H0V10" fill="none" stroke="#232d40" strokeWidth="0.3" />
        </pattern>
      </defs>
      <rect width="100" height="100" fill="#0a0e17" />
      <rect width="100" height="100" fill="url(#grid)" />
      <path d="M0 62 H100 M38 0 V100 M38 30 H100" stroke="#1b2434" strokeWidth="2.4" fill="none" />
      {[[6, 8, 26, 16], [46, 8, 22, 14], [76, 8, 18, 14], [46, 38, 18, 16], [72, 38, 22, 16], [6, 34, 26, 20], [6, 70, 26, 22], [46, 70, 48, 22]].map(([x, y, w, h]) => (
        <rect key={`${x}-${y}`} x={x} y={y} width={w} height={h} rx="1.5" fill="#111827" stroke="#232d40" strokeWidth="0.4" />
      ))}
    </svg>
  );
}

/**
 * A pan-and-zoom canvas for the placeholder schematic or an uploaded campus image. Markers are placed
 * by percentage (x across, y down), so they stay put whatever size the map is drawn at.
 * `onPick(x, y)` makes the canvas clickable, which the admin page uses to position a marker.
 */
export default function SchematicMap({ imageUrl, markers, selected, onSelect, onPick }) {
  const [view, setView] = useState({ zoom: 1, x: 0, y: 0 });
  const frame = useRef(null);
  const drag = useRef(null);

  const clamp = (v) => {
    const limit = ((v.zoom - 1) / 2) * 100; // percent of the frame the canvas may shift
    const hold = (n) => Math.max(-limit, Math.min(limit, n));
    return { zoom: v.zoom, x: hold(v.x), y: hold(v.y) };
  };
  const zoomBy = (factor) => setView((v) => clamp({ ...v, zoom: Math.max(1, Math.min(5, +(v.zoom * factor).toFixed(2))) }));

  function pointerDown(e) {
    drag.current = { startX: e.clientX, startY: e.clientY, x: view.x, y: view.y, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function pointerMove(e) {
    const d = drag.current;
    if (!d) return;
    const box = frame.current.getBoundingClientRect();
    const dx = ((e.clientX - d.startX) / box.width) * 100;
    const dy = ((e.clientY - d.startY) / box.height) * 100;
    if (Math.abs(dx) + Math.abs(dy) > 1) d.moved = true;
    setView((v) => clamp({ zoom: v.zoom, x: d.x + dx, y: d.y + dy }));
  }
  function pointerUp(e) {
    const d = drag.current;
    drag.current = null;
    if (!d || d.moved || !onPick || e.target.closest("button")) return;
    // Convert the tap from screen space back to map percentages, undoing the pan and zoom.
    const box = frame.current.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * 100;
    const py = ((e.clientY - box.top) / box.height) * 100;
    const x = (px - 50 - view.x) / view.zoom + 50;
    const y = (py - 50 - view.y) / view.zoom + 50;
    if (x >= 0 && x <= 100 && y >= 0 && y <= 100) onPick(+x.toFixed(1), +y.toFixed(1));
  }

  return (
    <div className="relative">
      <div
        ref={frame}
        className={`relative aspect-[4/3] w-full touch-none select-none overflow-hidden rounded-xl border border-edge bg-ink ${onPick ? "cursor-crosshair" : "cursor-grab active:cursor-grabbing"}`}
        onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={() => (drag.current = null)}
        onWheel={(e) => zoomBy(e.deltaY < 0 ? 1.15 : 1 / 1.15)}
      >
        <div className="absolute inset-0 origin-center" style={{ transform: `translate(${view.x}%, ${view.y}%) scale(${view.zoom})` }}>
          {imageUrl ? (
            <img src={imageUrl} alt="Campus map" draggable={false} className="absolute inset-0 h-full w-full object-fill" />
          ) : (
            <PlaceholderArt />
          )}
          {markers.map((m, i) => {
            const style = MARKER_STYLES[m.kind] || MARKER_STYLES.landmark;
            const active = selected === i;
            return (
              <button
                key={i} type="button" onClick={() => onSelect?.(i)} aria-label={m.name} aria-pressed={active}
                className="absolute -translate-x-1/2 -translate-y-1/2"
                style={{ left: `${m.x}%`, top: `${m.y}%`, transform: `translate(-50%, -50%) scale(${1 / view.zoom})`, zIndex: active ? 2 : 1 }}
              >
                <span className={`block h-4 w-4 rounded-full border-2 border-ink ring-4 ${style.dot} ${active ? "ring-white/70" : style.ring}`} />
                {active && (
                  <span className={`absolute left-1/2 top-6 -translate-x-1/2 whitespace-nowrap rounded-md border border-edge bg-panel px-2 py-1 font-mono text-[11px] ${style.text}`}>
                    {m.name}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        {!imageUrl && (
          <p className="pointer-events-none absolute bottom-2 left-2 rounded bg-ink/80 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-dim">
            Placeholder map · not to scale
          </p>
        )}
      </div>
      <div className="absolute right-2 top-2 flex flex-col gap-1">
        <button type="button" className="btn-ghost !px-2.5 !py-1.5 !text-base" onClick={() => zoomBy(1.4)} aria-label="Zoom in">+</button>
        <button type="button" className="btn-ghost !px-2.5 !py-1.5 !text-base" onClick={() => zoomBy(1 / 1.4)} aria-label="Zoom out">−</button>
        <button type="button" className="btn-ghost !px-2 !py-1.5" onClick={() => setView({ zoom: 1, x: 0, y: 0 })} aria-label="Reset view">⟲</button>
      </div>
    </div>
  );
}
