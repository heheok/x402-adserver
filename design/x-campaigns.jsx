// x-campaigns.jsx — Campaigns tab artboards.

const dmaLabel = (ids) => ids.map(id => DMAS.find(d => d.id === id)?.dma).filter(Boolean).join(' · ');

const CampaignCardCollapsed = ({ c }) => {
  const dmaSummary = c.dmas.length ? dmaLabel(c.dmas) : '—';
  const days = c.start && c.end ? Math.ceil((new Date(c.end) - new Date(c.start)) / 86400000) : null;
  const pct = c.budget ? c.spent / c.budget : 0;

  return (
    <div className="x-card" style={{ padding: 18, display: 'grid',
      gridTemplateColumns: '40px 1fr 220px 200px 24px', alignItems: 'center', gap: 16 }}>
      <CreativeThumb brand={c.brand} size={40} />
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>{c.name}</span>
          <StatusBadge status={c.status} />
        </div>
        <div style={{ fontSize: 11, color: 'var(--tx-2)', marginTop: 4, fontFamily: 'var(--font-mono)' }}>
          {dmaSummary}{days ? ` · ${days} days` : ''}
        </div>
      </div>
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 6 }}>
          <span style={{ color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>SPENT</span>
          <span className="x-mono x-tnum" style={{ color: 'var(--tx-1)' }}>
            {c.spent.toFixed(2)} <span style={{ color: 'var(--tx-3)' }}>/ {c.budget.toFixed(2)}</span>
          </span>
        </div>
        <Progress value={pct} color={c.status === 'active' ? 'var(--tint-grad-strong)' : 'var(--tx-3)'} />
      </div>
      <div style={{ textAlign: 'right' }}>
        <div className="x-mono x-tnum" style={{ fontSize: 14, color: 'var(--tx-0)' }}>{c.plays.toLocaleString()}</div>
        <div style={{ fontSize: 10, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>plays</div>
      </div>
      <Icon name="chevron" size={14} />
    </div>
  );
};

const CreativeThumb = ({ brand, size = 40 }) => {
  const palette = {
    Phantom:   ['#534BB1', '#AB9FF2'],
    Jupiter:   ['#F69100', '#FFD089'],
    Helius:    ['#F03A47', '#FF7A45'],
    Backpack:  ['#E33E7F', '#FF8FB3'],
    Drift:     ['#11D5C0', '#9945FF'],
    MagicEden: ['#E42575', '#9945FF'],
    'Liquid Death': ['#0B0D14', '#3D5AFE'],
  };
  const [a, b] = palette[brand] || ['#9945FF', '#14F195'];
  const initial = brand?.[0] || '·';
  return (
    <div style={{ width: size, height: size, borderRadius: 8,
      background: `linear-gradient(135deg, ${a}, ${b})`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: '#fff', fontWeight: 700, fontSize: size * 0.45, fontFamily: 'var(--font-mono)',
      boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.15)' }}>
      {initial}
    </div>
  );
};

const CampaignsList = () => (
  <div style={{ padding: '32px 28px 40px' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 24 }}>
      <div>
        <div className="x-display" style={{ fontSize: 28, letterSpacing: '-0.025em' }}>Campaigns</div>
        <div style={{ fontSize: 13, color: 'var(--tx-2)', marginTop: 4 }}>
          {CAMPAIGNS.length} campaigns · 2 active · 5,464.06 USDC spent of 15,700 funded
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="x-btn x-btn-sm">All <Icon name="chevron" size={11} /></button>
        <button className="x-btn x-btn-sm">Newest <Icon name="chevron" size={11} /></button>
      </div>
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {CAMPAIGNS.map(c => <CampaignCardCollapsed key={c.id} c={c} />)}
    </div>
  </div>
);

const CampaignsEmpty = () => (
  <div style={{ padding: '32px 28px 40px' }}>
    <div className="x-display" style={{ fontSize: 28, letterSpacing: '-0.025em' }}>Campaigns</div>
    <div style={{ fontSize: 13, color: 'var(--tx-2)', marginTop: 4 }}>You haven't shipped a campaign yet.</div>

    <div className="x-card" style={{ marginTop: 24, padding: '56px 32px', textAlign: 'center', position: 'relative', overflow: 'hidden' }}>
      <div style={{ position: 'absolute', inset: 0, background: 'var(--tint-grad)', pointerEvents: 'none' }} />
      <div style={{ position: 'relative' }}>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 6 }}>
          {['draft','active','paused','completed','expired','refunded'].map(s => <StatusBadge key={s} status={s} />)}
        </div>
        <div className="x-display" style={{ fontSize: 20, marginTop: 22, letterSpacing: '-0.02em' }}>No campaigns yet</div>
        <div style={{ fontSize: 13, color: 'var(--tx-1)', marginTop: 6 }}>Click <span style={{ color: 'var(--tx-0)', fontWeight: 600 }}>+ New campaign</span> to get started.</div>
        <button className="x-btn x-btn-primary x-btn-lg" style={{ marginTop: 18 }}>
          <Icon name="plus" size={13} stroke={2} /> New campaign
        </button>
      </div>
    </div>
  </div>
);

const CampaignExpanded = () => {
  const c = CAMPAIGNS[0]; // Phantom — active
  const fee = c.spent * 0.025;
  const daysLeft = 8;
  const lastPlay = SETTLEMENTS[0];
  return (
    <div style={{ padding: '32px 28px 40px' }}>
      <div className="x-display" style={{ fontSize: 28, letterSpacing: '-0.025em' }}>Campaigns</div>
      <div style={{ fontSize: 13, color: 'var(--tx-2)', marginTop: 4 }}>{CAMPAIGNS.length} campaigns · 2 active</div>

      {/* Other rows collapsed-ish, then expanded card */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 24 }}>
        <CampaignCardCollapsed c={CAMPAIGNS[1]} />

        {/* expanded card */}
        <div className="x-card x-ring-grad" style={{ padding: 20, position: 'relative', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', inset: 0, background: 'var(--tint-grad)', pointerEvents: 'none' }} />
          <div style={{ position: 'relative' }}>
            {/* header */}
            <div style={{ display: 'grid', gridTemplateColumns: '64px 1fr auto', alignItems: 'center', gap: 16 }}>
              <CreativeThumb brand={c.brand} size={64} />
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span className="x-display" style={{ fontSize: 18 }}>{c.name}</span>
                  <StatusBadge status={c.status} />
                  <span style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>· {daysLeft}d remaining</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11, color: 'var(--tx-2)', marginTop: 6, fontFamily: 'var(--font-mono)' }}>
                  <span>Wallet {c.wallet}</span><Solscan>View on Solscan</Solscan>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="x-btn x-btn-sm"><Icon name="play" size={11} /> Simulate play</button>
                <button className="x-btn x-btn-sm"><Icon name="pause" size={11} /> Pause</button>
                <button className="x-btn x-btn-sm"><Icon name="chevronUp" size={11} /></button>
              </div>
            </div>

            <hr className="x-hr" style={{ margin: '18px 0' }} />

            {/* stats grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 16 }}>
              <Stat label="Plays" value={c.plays.toLocaleString()} />
              <Stat label="CPM" value={<>{c.cpm.toFixed(2)} <span style={{ fontSize: 10, color: 'var(--tx-2)' }}>USDC</span></>} />
              <Stat label="Spent" value={<>{c.spent.toFixed(2)}</>} />
              <Stat label="Remaining" value={<span style={{ color: 'var(--sol-teal)' }}>{(c.budget - c.spent).toFixed(2)}</span>} />
              <Stat label="Protocol fee" value={`${fee.toFixed(2)}`} />
              <Stat label="Schedule" value={`${c.start.slice(5)} → ${c.end.slice(5)}`} small />
            </div>

            <div style={{ marginTop: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 6 }}>
                <span style={{ color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>BUDGET · {(c.spent/c.budget*100).toFixed(1)}% spent</span>
                <span className="x-mono x-tnum" style={{ color: 'var(--tx-1)' }}>{c.spent.toFixed(2)} / {c.budget.toFixed(2)} USDC</span>
              </div>
              <Progress value={c.spent / c.budget} />
            </div>

            <hr className="x-hr" style={{ margin: '18px 0' }} />

            {/* targeting + last play */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
              <div>
                <div style={{ fontSize: 10, color: 'var(--tx-2)', letterSpacing: '0.08em', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>Target DMAs</div>
                <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                  {c.dmas.map(id => {
                    const d = DMAS.find(x => x.id === id);
                    return (
                      <div key={id} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid var(--line-1)', background: 'var(--bg-2)', fontSize: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span style={{ fontWeight: 500 }}>{d.dma}</span>
                        <span className="x-mono" style={{ color: 'var(--tx-2)', fontSize: 11 }}>{d.screens.toLocaleString()} screens</span>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: 'var(--tx-2)', letterSpacing: '0.08em', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>Last play</div>
                <div style={{ marginTop: 8, padding: '10px 12px', borderRadius: 10, background: 'var(--bg-2)', border: '1px solid var(--line-1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 4, background: 'var(--sol-teal)', boxShadow: '0 0 10px var(--sol-teal)' }} />
                    <div>
                      <div style={{ fontSize: 12 }}>{lastPlay.dma}</div>
                      <div style={{ fontSize: 10, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>{lastPlay.time} · settled on-chain</div>
                    </div>
                  </div>
                  <Solscan>{lastPlay.tx}</Solscan>
                </div>
              </div>
            </div>

            <hr className="x-hr" style={{ margin: '18px 0' }} />

            {/* recent settlements */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>Recent settlements</div>
                <span style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>last 10 · /proof verified</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '70px 1fr 130px 110px 80px', padding: '8px 0', fontSize: 10, color: 'var(--tx-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.08em', borderBottom: '1px solid var(--line-1)' }}>
                <span>When</span><span>Nonce</span><span>Publisher</span><span style={{ textAlign: 'right' }}>Amount</span><span style={{ textAlign: 'right' }}>Tx</span>
              </div>
              {SETTLEMENTS.slice(0, 6).map((s, i) => (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: '70px 1fr 130px 110px 80px', alignItems: 'center', padding: '11px 0', borderTop: i === 0 ? 'none' : '1px solid var(--line-1)', fontSize: 12 }}>
                  <span style={{ color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>{s.time}</span>
                  <span className="x-mono" style={{ color: 'var(--tx-1)', fontSize: 11 }}>0x{(2316 + i).toString(16).padStart(4, '0')}…</span>
                  <span className="x-mono" style={{ color: 'var(--tx-1)', fontSize: 11 }}>Pb{(i*7+13).toString(16)}…s9{i}D</span>
                  <span className="x-mono x-tnum" style={{ color: 'var(--sol-teal)', textAlign: 'right' }}>+{s.amount.toFixed(4)}</span>
                  <span style={{ textAlign: 'right' }}><Solscan>{s.tx}</Solscan></span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <CampaignCardCollapsed c={CAMPAIGNS[2]} />
      </div>
    </div>
  );
};

const Stat = ({ label, value, small }) => (
  <div>
    <div style={{ fontSize: 10, color: 'var(--tx-2)', letterSpacing: '0.08em', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>{label}</div>
    <div className="x-display x-tnum" style={{ fontSize: small ? 14 : 18, marginTop: 6, lineHeight: 1.1 }}>{value}</div>
  </div>
);

Object.assign(window, { CampaignsList, CampaignsEmpty, CampaignExpanded, CreativeThumb });
