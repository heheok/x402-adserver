import { useEffect, useMemo, useRef } from "react";
import { MapContainer, Marker, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { DMA_CENTROIDS } from "../lib/dmaCentroids";
import { useCountUp } from "../lib/useCountUp";

// Min ms between consecutive punch animations on the same pin. Auto-play
// can fire 10-20 plays per tick distributed across DMAs; we still want a
// crisp single punch per DMA per server delta, not a stutter.
const PUNCH_DURATION_MS = 550;

// Per-campaign live activity map. DMA-level pins (not venue-precise: venue
// identity is publisher-private — see Session 14 findings). Map is fully
// non-interactive: fitBounds runs once at mount, then the view is frozen so
// it reads as a status display rather than something to click on.
//
// Tile provider: Carto Dark Matter (free, no API key). OSM + CARTO attribution
// is required by their tile-usage terms and stays on.

type Props = {
  targetDmas: string[];
  playsByDma: Record<string, number>;
};

const TILE_URL =
  "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const TILE_ATTR =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

function FitOnMount({ centers }: { centers: [number, number][] }) {
  const map = useMap();
  const didFit = useRef(false);
  useEffect(() => {
    if (didFit.current || centers.length === 0) return;
    didFit.current = true;
    if (centers.length === 1) {
      map.setView(centers[0], 6);
    } else {
      map.fitBounds(L.latLngBounds(centers), { padding: [60, 60] });
    }
  }, [centers, map]);
  return null;
}

function DmaPin({ dma, count }: { dma: string; count: number }) {
  const center = DMA_CENTROIDS[dma];
  const display = useCountUp(count);
  const markerRef = useRef<L.Marker | null>(null);
  const prevCountRef = useRef<number>(count);

  // Build the divIcon once per DMA. Updating the count text and triggering
  // the punch animation are both done imperatively below — without this,
  // every useCountUp frame would recreate the DOM and reset the animation.
  const icon = useMemo(() => {
    return L.divIcon({
      className: "x-map-pin",
      html: `<div class="x-map-pin__inner"><div class="x-map-pin__count">${count.toLocaleString()}</div><div class="x-map-pin__label">${dma}</div></div>`,
      iconSize: [0, 0],
      iconAnchor: [0, 0],
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dma]);

  // Tick the count text on every tween frame.
  useEffect(() => {
    const el = markerRef.current?.getElement();
    if (!el) return;
    const countEl = el.querySelector<HTMLElement>(".x-map-pin__count");
    if (countEl) countEl.textContent = display.toLocaleString();
  }, [display]);

  // Punch the pin when the *server* count changes (not on every tween frame).
  // Toggle a class via remove → reflow → add so the animation restarts even
  // if a previous punch hasn't finished.
  useEffect(() => {
    if (prevCountRef.current === count) return;
    prevCountRef.current = count;
    const el = markerRef.current?.getElement();
    if (!el) return;
    const inner = el.querySelector<HTMLElement>(".x-map-pin__inner");
    if (!inner) return;
    inner.classList.remove("x-map-pin__inner--punch");
    void inner.offsetWidth; // force reflow so the animation can restart
    inner.classList.add("x-map-pin__inner--punch");
    const t = window.setTimeout(() => {
      inner.classList.remove("x-map-pin__inner--punch");
    }, PUNCH_DURATION_MS);
    return () => window.clearTimeout(t);
  }, [count]);

  if (!center) return null;
  return <Marker ref={markerRef} position={center} icon={icon} interactive={false} />;
}

export function LiveActivityMap({ targetDmas, playsByDma }: Props) {
  const centers = useMemo(
    () =>
      targetDmas
        .map((d) => DMA_CENTROIDS[d])
        .filter((c): c is [number, number] => Array.isArray(c)),
    [targetDmas],
  );

  if (centers.length === 0) return null;

  // Initial center/zoom is a continental-US default; FitOnMount overrides
  // immediately to fit the actual targeted DMAs with padding.
  const initialCenter: [number, number] = [39.5, -98.35];
  const initialZoom = 3;

  return (
    <div className="x-map">
      <MapContainer
        center={initialCenter}
        zoom={initialZoom}
        style={{ height: "100%", width: "100%" }}
        dragging={false}
        scrollWheelZoom={false}
        doubleClickZoom={false}
        touchZoom={false}
        boxZoom={false}
        keyboard={false}
        zoomControl={false}
        attributionControl={true}
        // Default zoomSnap=1 forces fitBounds to integer zoom levels — for a
        // wide DOOH map that's the difference between zoom 4 (lots of empty
        // ocean) and zoom 5 (pins clipped). 0.25 lets it pick fractional
        // levels and tighten the bounds. maxZoom prevents 1-DMA campaigns
        // from auto-zooming to street level.
        zoomSnap={0.25}
        maxZoom={7}
      >
        <TileLayer url={TILE_URL} attribution={TILE_ATTR} />
        <FitOnMount centers={centers} />
        {targetDmas.map((dma) => (
          <DmaPin key={dma} dma={dma} count={playsByDma[dma] ?? 0} />
        ))}
      </MapContainer>
    </div>
  );
}
