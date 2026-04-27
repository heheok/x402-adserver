// x-primitives.jsx
// Shared atoms used across artboards: icons, header, wallet chip,
// status badge, sparkline, progress bar, segmented tabs.

const X402Mark = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <defs>
      <linearGradient id="x402-grad" x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#9945FF"/>
        <stop offset="100%" stopColor="#14F195"/>
      </linearGradient>
    </defs>
    <rect x="1.5" y="1.5" width="21" height="21" rx="6.5" stroke="url(#x402-grad)" strokeWidth="1.5"/>
    <path d="M7.5 7.5 L16.5 16.5 M16.5 7.5 L7.5 16.5" stroke="url(#x402-grad)" strokeWidth="1.6" strokeLinecap="round"/>
    <circle cx="12" cy="12" r="2" fill="url(#x402-grad)"/>
  </svg>
);

const Icon = ({ name, size = 16, stroke = 1.6 }) => {
  const paths = {
    chevron:    <path d="M3 6l5 5 5-5" />,
    chevronUp:  <path d="M3 10l5-5 5 5" />,
    copy:       <><rect x="5" y="5" width="9" height="9" rx="1.5"/><path d="M3 11V3.5A1.5 1.5 0 0 1 4.5 2H10"/></>,
    external:   <><path d="M9 3h4v4"/><path d="M13 3l-7 7"/><path d="M11 8.5V13H3V5h4.5"/></>,
    plus:       <><path d="M8 3v10"/><path d="M3 8h10"/></>,
    check:      <path d="M3 8.5L6.5 12 13 4.5"/>,
    close:      <><path d="M4 4l8 8"/><path d="M12 4l-8 8"/></>,
    pause:      <><rect x="5" y="3" width="2.2" height="10" rx="0.6"/><rect x="9" y="3" width="2.2" height="10" rx="0.6"/></>,
    play:       <path d="M5 3.5v9l8-4.5z"/>,
    upload:     <><path d="M8 12V3.5"/><path d="M4 7l4-4 4 4"/><path d="M2.5 13h11"/></>,
    calendar:   <><rect x="2.5" y="3.5" width="11" height="10" rx="1.5"/><path d="M5 2v3M11 2v3M2.5 7h11"/></>,
    map:        <><path d="M2 4l4-1.5L10 4l4-1.5V12l-4 1.5L6 12 2 13.5z"/><path d="M6 2.5V12M10 4v9.5"/></>,
    wallet:     <><rect x="2" y="4" width="12" height="9" rx="1.5"/><path d="M11 8.5h2"/><path d="M2 6.5h10"/></>,
    activity:   <path d="M1.5 8h3l2-5 3 10 2-5h3"/>,
    refund:     <><path d="M3 8a5 5 0 1 0 1.5-3.5"/><path d="M3 3v3.5h3.5"/></>,
    sparkle:    <path d="M8 2v4M8 10v4M2 8h4M10 8h4"/>,
    info:       <><circle cx="8" cy="8" r="6"/><path d="M8 11V7M8 5v.01"/></>,
    arrowRight: <path d="M3 8h10M9 4l4 4-4 4"/>,
    drag:       <><circle cx="6" cy="4" r="0.9"/><circle cx="10" cy="4" r="0.9"/><circle cx="6" cy="8" r="0.9"/><circle cx="10" cy="8" r="0.9"/><circle cx="6" cy="12" r="0.9"/><circle cx="10" cy="12" r="0.9"/></>,
    file:       <><path d="M4 2h5l3 3v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"/><path d="M9 2v3h3"/></>,
    image:      <><rect x="2" y="3" width="12" height="10" rx="1.5"/><circle cx="6" cy="7" r="1.2"/><path d="M3 11l3-3 3 3 2-2 3 3"/></>,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none"
      stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
};

const Solscan = ({ children = "Solscan" }) => (
  <a href="#" onClick={(e) => e.preventDefault()}
     style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--tx-2)', textDecoration: 'none', fontFamily: 'var(--font-mono)' }}>
    {children}<Icon name="external" size={11} stroke={1.4} />
  </a>
);

// ── Status badge ────────────────────────────────────────────────────────────
const StatusBadge = ({ status }) => {
  const labels = {
    draft: 'Draft', active: 'Active', paused: 'Paused',
    completed: 'Completed', expired: 'Expired', refunded: 'Refunded',
  };
  return (
    <span className={`x-badge x-badge-${status}`}>
      <span className="dot" />{labels[status] || status}
    </span>
  );
};

// ── Header bar ──────────────────────────────────────────────────────────────
const AppHeader = ({ tab = 'overview', onTabChange, walletState = 'normal', balance = 1240.50, address = "Hk7c…q9F2", showNew = true, onOpenWallet, walletOpen = false }) => (
  <header style={{ height: 64, padding: '0 28px', display: 'flex', alignItems: 'center',
    borderBottom: '1px solid var(--line-1)', background: 'var(--bg-0)', position: 'relative', zIndex: 5 }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <X402Mark size={22} />
      <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1 }}>
        <span className="x-display" style={{ fontSize: 18, letterSpacing: '-0.02em' }}>x402</span>
        <span style={{ fontSize: 10, color: 'var(--tx-2)', marginTop: 2, letterSpacing: '0.06em', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>DOOH ad protocol</span>
      </div>
      <span style={{ marginLeft: 14, padding: '3px 7px', borderRadius: 6, fontSize: 10,
        fontFamily: 'var(--font-mono)', color: 'var(--sol-teal)',
        background: 'rgba(20,241,149,0.08)', border: '1px solid rgba(20,241,149,0.20)',
        textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        Solana · devnet
      </span>
    </div>

    <div style={{ flex: 1 }} />

    <WalletChip state={walletState} balance={balance} address={address} expanded={walletOpen} onClick={onOpenWallet} />
  </header>
);

// ── Tab row ─────────────────────────────────────────────────────────────────
const TabRow = ({ tab = 'overview', onTabChange, showNew = true, onNew }) => (
  <div style={{ height: 56, padding: '0 28px', display: 'flex', alignItems: 'center', gap: 4,
    borderBottom: '1px solid var(--line-1)', background: 'var(--bg-0)' }}>
    {[
      { id: 'overview', label: 'Overview' },
      { id: 'campaigns', label: 'Campaigns' },
    ].map(t => (
      <button key={t.id} onClick={() => onTabChange?.(t.id)}
        style={{
          height: 56, padding: '0 14px', border: 0, background: 'transparent',
          color: tab === t.id ? 'var(--tx-0)' : 'var(--tx-2)',
          fontWeight: tab === t.id ? 600 : 500, fontSize: 14, cursor: 'pointer',
          borderBottom: '2px solid', borderBottomColor: tab === t.id ? 'var(--tx-0)' : 'transparent',
          marginBottom: -1, letterSpacing: '-0.005em',
        }}>
        {t.label}
      </button>
    ))}
    <div style={{ flex: 1 }} />
    {showNew && (
      <button className="x-btn x-btn-primary x-btn-sm" onClick={onNew}>
        <Icon name="plus" size={12} stroke={2} /> New campaign
      </button>
    )}
  </div>
);

// ── Wallet chip ─────────────────────────────────────────────────────────────
const WalletChip = ({ state = 'normal', balance = 1240.50, address = "Hk7c…q9F2", expanded = false }) => {
  const isLow = state === 'low';
  const isPending = state === 'pending';
  const isNoWallet = state === 'no-wallet';

  if (isNoWallet) {
    return (
      <button className="x-btn x-btn-sm" style={{ borderColor: 'var(--line-2)' }}>
        <Icon name="wallet" size={13} /> Create Solana wallet
      </button>
    );
  }

  const accent = isLow ? 'var(--st-paused)' : 'var(--line-2)';
  return (
    <button
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 8,
        height: 36, padding: '0 12px',
        background: 'var(--bg-2)', color: 'var(--tx-0)',
        border: `1px solid ${accent}`, borderRadius: 10,
        fontSize: 13, fontWeight: 500, cursor: 'pointer',
        boxShadow: isLow ? '0 0 0 3px rgba(255,181,71,0.12)' : 'none',
      }}
    >
      <span style={{ width: 18, height: 18, borderRadius: 5, background: 'var(--tint-grad-strong)',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, color: '#08070A', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>$</span>
      <span style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>Wallet</span>
      <span style={{ width: 1, height: 14, background: 'var(--line-1)' }} />
      {isPending ? (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-mono)' }}>
          <span style={{ width: 6, height: 6, borderRadius: 3, background: 'var(--sol-teal)', boxShadow: '0 0 8px var(--sol-teal)' }} />
          <span className="x-tnum">+100.00</span>
          <span style={{ color: 'var(--tx-2)', fontSize: 11 }}>USDC</span>
        </span>
      ) : (
        <span className="x-mono x-tnum" style={{ fontWeight: 500 }}>
          {balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          <span style={{ color: 'var(--tx-2)', marginLeft: 4, fontSize: 11 }}>USDC</span>
        </span>
      )}
      <Icon name={expanded ? 'chevronUp' : 'chevron'} size={11} stroke={2} />
    </button>
  );
};

// ── Wallet dropdown ─────────────────────────────────────────────────────────
const WalletDropdown = ({ state = 'normal', balance = 1240.50, address = "Hk7c8sP9aN3fM2vR5tQpL4qWzX1bD8eY9F2", showFallback = false, anchor = 'header' }) => (
  <div className="x-card" style={{
    width: 320, padding: 16,
    position: anchor === 'header' ? 'absolute' : 'static',
    top: anchor === 'header' ? 56 : undefined,
    right: anchor === 'header' ? 28 : undefined,
    boxShadow: 'var(--shadow-card)', zIndex: 10, background: 'var(--bg-1)',
  }}>
    <div style={{ fontSize: 10, color: 'var(--tx-2)', letterSpacing: '0.08em', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>Wallet address</div>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
      <span className="x-mono" style={{ fontSize: 12, color: 'var(--tx-1)' }}>
        {address.slice(0,4)}…{address.slice(-4)}
      </span>
      <button style={{ width: 22, height: 22, border: 0, borderRadius: 5, background: 'var(--bg-3)', color: 'var(--tx-2)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
        <Icon name="copy" size={11} stroke={1.6} />
      </button>
      <Solscan>View on Solscan</Solscan>
    </div>

    <div style={{
      marginTop: 14, padding: 14, borderRadius: 10,
      background: 'linear-gradient(135deg, rgba(153,69,255,0.10), rgba(20,241,149,0.06))',
      border: '1px solid var(--line-1)',
    }}>
      <div style={{ fontSize: 10, color: 'var(--tx-2)', letterSpacing: '0.08em', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>Balance</div>
      <div className="x-mono x-tnum" style={{ fontSize: 24, fontWeight: 500, marginTop: 4, letterSpacing: '-0.02em' }}>
        {balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}
        <span style={{ fontSize: 12, color: 'var(--tx-2)', marginLeft: 6, fontWeight: 500 }}>USDC</span>
      </div>
      {state === 'low' && (
        <div style={{ marginTop: 8, fontSize: 11, color: 'var(--st-paused)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icon name="info" size={12} /> Low balance — fund or use the faucet to start a campaign.
        </div>
      )}
      {state === 'pending' && (
        <div style={{ marginTop: 8, fontSize: 11, color: 'var(--sol-teal)', display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-mono)' }}>
          <span style={{ width: 6, height: 6, borderRadius: 3, background: 'var(--sol-teal)', boxShadow: '0 0 8px var(--sol-teal)' }} />
          inbound +100.00 USDC · confirming…
        </div>
      )}
    </div>

    <button className="x-btn x-btn-grad" style={{ width: '100%', marginTop: 12, height: 40 }}>
      <Icon name="plus" size={13} stroke={2} /> Get test USDC
    </button>

    {showFallback && (
      <button className="x-btn x-btn-sm" style={{ width: '100%', marginTop: 8 }}>
        <Icon name="wallet" size={12} /> Create Solana wallet
      </button>
    )}

    <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--line-1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>Privy embedded · devnet</span>
      <button style={{ background: 'transparent', border: 0, color: 'var(--tx-2)', fontSize: 11, cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>Disconnect</button>
    </div>
  </div>
);

// ── Sparkline ──────────────────────────────────────────────────────────────
const Sparkline = ({ data = [3,5,4,7,8,6,9,11,10,13,12,16], width = 80, height = 24, color = "var(--sol-teal)" }) => {
  const max = Math.max(...data), min = Math.min(...data);
  const range = max - min || 1;
  const pts = data.map((v,i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 2) - 1;
    return `${x},${y}`;
  }).join(' ');
  const area = `0,${height} ${pts} ${width},${height}`;
  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <defs>
        <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      <polygon points={area} fill="url(#spark-fill)" />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
};

// ── Progress bar ───────────────────────────────────────────────────────────
const Progress = ({ value = 0.5, color = "var(--tint-grad-strong)", height = 4 }) => (
  <div style={{ width: '100%', height, background: 'var(--bg-3)', borderRadius: 999, overflow: 'hidden' }}>
    <div style={{ width: `${Math.min(100, value*100)}%`, height: '100%', background: color, borderRadius: 999 }} />
  </div>
);

// ── Stat card ──────────────────────────────────────────────────────────────
const StatCard = ({ label, value, sub, sparkData, sparkColor, accent }) => (
  <div className="x-card" style={{ padding: 16, position: 'relative', overflow: 'hidden' }}>
    {accent && (
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 1, background: accent }} />
    )}
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
      <div style={{ fontSize: 11, color: 'var(--tx-2)', letterSpacing: '0.06em', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>{label}</div>
      {sparkData && <Sparkline data={sparkData} color={sparkColor || 'var(--sol-teal)'} />}
    </div>
    <div className="x-display x-tnum" style={{ fontSize: 30, marginTop: 10, lineHeight: 1.05 }}>{value}</div>
    {sub && <div style={{ fontSize: 11, color: 'var(--tx-2)', marginTop: 6, fontFamily: 'var(--font-mono)' }}>{sub}</div>}
  </div>
);

// Export to window so other scripts pick them up.
Object.assign(window, {
  X402Mark, Icon, Solscan, StatusBadge, AppHeader, TabRow, WalletChip, WalletDropdown,
  Sparkline, Progress, StatCard,
});
