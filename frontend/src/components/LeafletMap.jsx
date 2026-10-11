import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";

// Integration point for a different tile provider (MapTiler, Mapbox, your own server): set
// VITE_MAP_TILE_URL to its {z}/{x}/{y} URL, key included. OpenStreetMap's public tiles need no key.
const TILE_URL = import.meta.env.VITE_MAP_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = import.meta.env.VITE_MAP_ATTRIBUTION || "© OpenStreetMap contributors";
const COLORS = { landmark: "#45d6ff", clue: "#3dffb4", final: "#ffc857" };

/** Real-world map for the "osm" provider. Only markers with latitude and longitude are drawn. */
export default function LeafletMap({ center, markers, selected, onSelect }) {
  const node = useRef(null);
  const map = useRef(null);
  const layer = useRef(null);

  useEffect(() => {
    const located = markers.filter((m) => m.lat != null && m.lng != null);
    const start = center.lat != null && center.lng != null ? [center.lat, center.lng] : located[0] ? [located[0].lat, located[0].lng] : [20, 0];
    map.current = L.map(node.current, { zoomControl: true }).setView(start, center.lat != null || located[0] ? center.zoom || 17 : 2);
    L.tileLayer(TILE_URL, { maxZoom: 20, attribution: ATTRIBUTION }).addTo(map.current);
    layer.current = L.layerGroup().addTo(map.current);
    return () => map.current.remove();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    layer.current.clearLayers();
    markers.forEach((m, i) => {
      if (m.lat == null || m.lng == null) return;
      const color = COLORS[m.kind] || COLORS.landmark;
      L.circleMarker([m.lat, m.lng], { radius: selected === i ? 11 : 8, color: "#07090f", weight: 2, fillColor: color, fillOpacity: 1 })
        .bindTooltip(m.name, { permanent: selected === i, direction: "top", offset: [0, -8] })
        .on("click", () => onSelect?.(i))
        .addTo(layer.current);
    });
    const chosen = markers[selected];
    if (chosen?.lat != null && chosen?.lng != null) map.current.panTo([chosen.lat, chosen.lng]);
  }, [markers, selected, onSelect]);

  return <div ref={node} className="aspect-[4/3] w-full overflow-hidden rounded-xl border border-edge" />;
}
