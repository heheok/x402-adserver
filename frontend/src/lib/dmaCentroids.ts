// Hardcoded centroid lat/lon for the 6 demo DMAs. Keep in sync with the
// `DMA_LABELS` map in `backend/app/services/venues.py`. Used by the
// per-campaign live activity map (Session 16.7); we use city-level centroids
// (not venue-precise) because venue identity is publisher-private — see
// Session 14 findings in PLAN.md.
export const DMA_CENTROIDS: Record<string, [number, number]> = {
  "New York": [40.7128, -74.006],
  "Los Angeles": [34.0522, -118.2437],
  "San Francisco": [37.7749, -122.4194],
  Miami: [25.7617, -80.1918],
  Boston: [42.3601, -71.0589],
  Austin: [30.2672, -97.7431],
};
