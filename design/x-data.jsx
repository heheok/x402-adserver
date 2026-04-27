// x-data.jsx
// Realistic mock data — DMAs, campaigns, settlements.

const DMAS = [
  { id: 'nyc', dma: 'New York',     screens: 1842, lat: 40.7,  lng: -74.0 },
  { id: 'la',  dma: 'Los Angeles',  screens: 1216, lat: 34.05, lng: -118.2 },
  { id: 'sf',  dma: 'San Francisco',screens: 487,  lat: 37.77, lng: -122.4 },
  { id: 'mia', dma: 'Miami',        screens: 612,  lat: 25.76, lng: -80.19 },
  { id: 'bos', dma: 'Boston',       screens: 384,  lat: 42.36, lng: -71.05 },
  { id: 'aus', dma: 'Austin',       screens: 271,  lat: 30.27, lng: -97.74 },
];

const CAMPAIGNS = [
  {
    id: 'c1', name: 'Phantom · Mobile push',   brand: 'Phantom',
    status: 'active',  budget: 4800, spent: 2964.50, plays: 2316,
    cpm: 1.28, dmas: ['nyc','la','sf'], start: '2026-04-21', end: '2026-05-05',
    wallet: 'F8q2…7cN1',
  },
  {
    id: 'c2', name: 'Jupiter · Perps launch',  brand: 'Jupiter',
    status: 'active',  budget: 3200, spent: 1890.00, plays: 1476,
    cpm: 1.28, dmas: ['nyc','mia'], start: '2026-04-23', end: '2026-04-29',
    wallet: '2vRb…h9aQ',
  },
  {
    id: 'c3', name: 'Helius · RPC for builders', brand: 'Helius',
    status: 'paused', budget: 1500, spent: 412.16, plays: 322,
    cpm: 1.28, dmas: ['sf','aus'], start: '2026-04-24', end: '2026-05-01',
    wallet: 'Lk4n…p2Wq',
  },
  {
    id: 'c4', name: 'Liquid Death · Murder Your Thirst', brand: 'Liquid Death',
    status: 'expired', budget: 2400, spent: 2400.00, plays: 1875,
    cpm: 1.28, dmas: ['la','bos'], start: '2026-04-08', end: '2026-04-22',
    wallet: 'Hk7c…q9F2',
  },
  {
    id: 'c5', name: 'Backpack · Wallet 2.0',   brand: 'Backpack',
    status: 'completed', budget: 1800, spent: 1800.00, plays: 1406,
    cpm: 1.28, dmas: ['nyc'], start: '2026-04-12', end: '2026-04-19',
    wallet: 'Bp4u…v8eR',
  },
  {
    id: 'c6', name: 'Drift · Trade smarter',   brand: 'Drift',
    status: 'refunded',  budget: 2000, spent: 318.40, plays: 248,
    cpm: 1.28, dmas: ['sf'], start: '2026-04-15', end: '2026-04-20',
    wallet: 'Dr3f…tW2y',
  },
  {
    id: 'c7', name: 'MagicEden · Drop calendar', brand: 'MagicEden',
    status: 'draft', budget: 0, spent: 0, plays: 0, cpm: 1.28,
    dmas: [], start: null, end: null, wallet: null,
  },
];

const SETTLEMENTS = [
  { time: '2m ago',  campaign: 'Phantom · Mobile push',     dma: 'NYC · Times Sq.',     amount: 0.0064, tx: '5gT2…aQ9F' },
  { time: '4m ago',  campaign: 'Jupiter · Perps launch',     dma: 'NYC · Penn Plaza',    amount: 0.0064, tx: 'B2p7…kL1c' },
  { time: '7m ago',  campaign: 'Phantom · Mobile push',     dma: 'LA · Sunset Blvd',    amount: 0.0064, tx: 'Qm4d…s8eR' },
  { time: '9m ago',  campaign: 'Phantom · Mobile push',     dma: 'SF · Market St.',     amount: 0.0064, tx: '7Yh1…wN3x' },
  { time: '12m ago', campaign: 'Jupiter · Perps launch',     dma: 'MIA · Brickell',      amount: 0.0064, tx: 'Pq9k…dV4t' },
  { time: '14m ago', campaign: 'Phantom · Mobile push',     dma: 'NYC · 5th Ave',       amount: 0.0064, tx: 'X3n6…oC8m' },
  { time: '17m ago', campaign: 'Jupiter · Perps launch',     dma: 'NYC · Hudson Yards',  amount: 0.0064, tx: '2sR8…fJ7q' },
  { time: '19m ago', campaign: 'Phantom · Mobile push',     dma: 'LA · Hollywood',      amount: 0.0064, tx: 'Wt5y…hB6n' },
  { time: '22m ago', campaign: 'Phantom · Mobile push',     dma: 'SF · Embarcadero',    amount: 0.0064, tx: '9Fk3…lP2v' },
  { time: '25m ago', campaign: 'Jupiter · Perps launch',     dma: 'NYC · SoHo',          amount: 0.0064, tx: 'Em8c…iU4z' },
];

const STATUS_COUNTS = { active: 2, paused: 1, completed: 1, expired: 1, refunded: 1, expiringSoon: 1 };

Object.assign(window, { DMAS, CAMPAIGNS, SETTLEMENTS, STATUS_COUNTS });
