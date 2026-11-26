import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from "react-leaflet";
import type { LatLngBoundsExpression, LatLngExpression } from "leaflet";

export interface MapPoint { lat: number; lng: number; label: string; color?: string; radius?: number }

/** Simple Leaflet map: coloured circle markers (no image assets, so it bundles cleanly) plus an optional route line. */
export default function MapView({ points, route, height = 320 }: { points: MapPoint[]; route?: [number, number][]; height?: number }) {
  const valid = points.filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lng));
  if (valid.length === 0) return <div className="rounded-xl bg-stone-100 p-6 text-center text-sm text-stone-500">No locations to show.</div>;
  const bounds: LatLngBoundsExpression = valid.map((p) => [p.lat, p.lng] as [number, number]);
  const center: LatLngExpression = [valid[0].lat, valid[0].lng];
  return (
    <div style={{ height }} data-testid="map" className="overflow-hidden rounded-xl border border-stone-200">
      <MapContainer center={center} zoom={12} bounds={valid.length > 1 ? bounds : undefined} boundsOptions={{ padding: [30, 30] }} style={{ height: "100%", width: "100%" }} scrollWheelZoom={false}>
        <TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {route && route.length > 1 && <Polyline positions={route} pathOptions={{ color: "#059669", weight: 4, opacity: 0.7, dashArray: "6 6" }} />}
        {valid.map((p, i) => (
          <CircleMarker key={i} center={[p.lat, p.lng]} radius={p.radius ?? 9} pathOptions={{ color: "#fff", weight: 2, fillColor: p.color ?? "#059669", fillOpacity: 0.95 }}>
            <Tooltip direction="top" offset={[0, -6]} permanent={valid.length <= 4}>{p.label}</Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
