// x-overview.jsx — Overview tab artboards (empty, normal, loading)

const ActivityRow = ({ s, idx }) => (
  <div style={{ display: 'grid', gridTemplateColumns: '70px 1fr 130px 110px 80px',
    alignItems: 'center', padding: '12px 0',
    borderTop: idx === 0 ? 'none' : '1px solid var(--line-1)',
    fontSize: 12 }}>
    <span style={{ color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>{s.time}</span>
    <span style={{ color: 'var(--tx-0)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.campaign}</span>
    <span style={{ color: 'var(--tx-1)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>{s.dma}</span>
    <span className="x-mono x-tnum" style={{ color: 'var(--sol-teal)', textAlign: 'right' }}>+{s.amount.toFixed(4)} <span style={{ color: 'var(--tx-2)', fontSize: 10 }}>USDC</span></span>
    <span style={{ textAlign: 'right' }}><Solscan>{s.tx}</Solscan></span>
  </div>
);

const StatusChip = ({ status, count, label }) => (
  <div style={{ flex: 1, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 4,
    borderRight: '1px solid var(--line-1)' }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <StatusBadge status={status} />
    </div>
    <div className="x-display x-tnum" style={{ fontSize: 22, marginTop: 4 }}>{count}</div>
    {label && <div style={{ fontSize: 10, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>{label}</div>}
  </div>
);

const OverviewNormal = () => (
  <div style={{ padding: '32px 28px 40px', display: 'flex', flexDirection: 'column', gap: 24 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
      <div>
        <div className="x-display" style={{ fontSize: 28, letterSpacing: '-0.025em' }}>Overview</div>
        <div style={{ fontSize: 13, color: 'var(--tx-2)', marginTop: 4 }}>Real-time campaign performance across the x402 network.</div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>
        <span style={{ width: 6, height: 6, borderRadius: 3, background: 'var(--sol-teal)', boxShadow: '0 0 8px var(--sol-teal)' }} />
        Live · 6,427 screens online
      </div>
    </div>

    {/* Stat grid */}
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
      <StatCard label="Active campaigns" value="2" sub="across 4 DMAs" sparkData={[1,1,2,2,2,2,3,2,2,2,2,2]} sparkColor="var(--sol-teal)" accent="var(--tint-grad-strong)" />
      <StatCard label="Total spent" value={<>5,464.06 <span style={{ fontSize: 14, color: 'var(--tx-2)' }}>USDC</span></>} sub="incl. 136.60 protocol fee" sparkData={[80,120,200,260,310,360,420,490,560,640,720,820]} sparkColor="var(--x402-blue)" accent="var(--x402-blue)" />
      <StatCard label="Total plays" value="4,267" sub="↑ 18% vs. last week" sparkData={[120,140,180,220,200,260,280,310,340,360,400,440]} sparkColor="var(--sol-purple)" accent="var(--sol-purple)" />
      <StatCard label="Last 24h plays" value="1,142" sub="across 4 active DMAs" sparkData={[8,12,18,30,42,48,56,72,80,68,74,90]} sparkColor="var(--sol-teal)" accent="var(--sol-teal)" />
    </div>

    {/* Status breakdown */}
    <div className="x-card" style={{ display: 'flex', overflow: 'hidden' }}>
      <StatusChip status="active" count={2} label="2 funded" />
      <StatusChip status="paused" count={1} />
      <StatusChip status="completed" count={1} />
      <StatusChip status="expired" count={1} label="auto-refundable" />
      <div style={{ flex: 1, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="x-badge" style={{ color: 'var(--st-paused)', background: 'rgba(255,181,71,0.10)', border: '1px solid rgba(255,181,71,0.25)' }}>
            <span className="dot" />Expiring soon
          </span>
        </div>
        <div className="x-display x-tnum" style={{ fontSize: 22, marginTop: 4 }}>1</div>
        <div style={{ fontSize: 10, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>≤ 3 days left</div>
      </div>
    </div>

    {/* Activity feed */}
    <div className="x-card" style={{ padding: '18px 20px 8px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Recent activity</div>
          <div style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>last 10 settlements · all campaigns</div>
        </div>
        <button className="x-btn x-btn-sm x-btn-ghost" style={{ background: 'transparent', borderColor: 'transparent', color: 'var(--tx-2)' }}>
          View all <Icon name="arrowRight" size={11} />
        </button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '70px 1fr 130px 110px 80px',
        padding: '8px 0', fontSize: 10, color: 'var(--tx-3)', fontFamily: 'var(--font-mono)',
        textTransform: 'uppercase', letterSpacing: '0.08em', borderBottom: '1px solid var(--line-1)' }}>
        <span>When</span><span>Campaign</span><span>Venue</span><span style={{ textAlign: 'right' }}>Amount</span><span style={{ textAlign: 'right' }}>Tx</span>
      </div>
      <div>{SETTLEMENTS.map((s, i) => <ActivityRow key={i} s={s} idx={i} />)}</div>
    </div>
  </div>
);

const OverviewEmpty = () => (
  <div style={{ padding: '32px 28px 40px' }}>
    <div className="x-display" style={{ fontSize: 28, letterSpacing: '-0.025em' }}>Overview</div>
    <div style={{ fontSize: 13, color: 'var(--tx-2)', marginTop: 4 }}>Real-time campaign performance across the x402 network.</div>

    <div className="x-card" style={{
      marginTop: 28, padding: '64px 32px', textAlign: 'center', position: 'relative', overflow: 'hidden',
    }}>
      <div style={{ position: 'absolute', inset: 0, background: 'var(--tint-grad)', pointerEvents: 'none' }} />
      <div style={{ position: 'relative' }}>
        <div style={{ width: 56, height: 56, margin: '0 auto', borderRadius: 14,
          background: 'var(--tint-grad-strong)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 12px 40px rgba(153,69,255,0.3)' }}>
          <Icon name="plus" size={22} stroke={2.4} />
        </div>
        <div className="x-display" style={{ fontSize: 22, marginTop: 18, letterSpacing: '-0.02em' }}>
          Run your first <span className="x-grad-text">on-chain</span> ad campaign
        </div>
        <div style={{ fontSize: 13, color: 'var(--tx-1)', marginTop: 8, maxWidth: 420, marginInline: 'auto', lineHeight: 1.55 }}>
          Upload a creative, pick markets, fund in USDC. Publishers serve your ad and settle every play on Solana.
        </div>
        <button className="x-btn x-btn-primary x-btn-lg" style={{ marginTop: 22 }}>
          <Icon name="plus" size={13} stroke={2} /> New campaign
        </button>
        <div style={{ marginTop: 14, fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>
          devnet · CPM locked at 1.28 USDC · 2.5% protocol fee
        </div>
      </div>
    </div>

    {/* trio of how-it-works tiles */}
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginTop: 16 }}>
      {[
        { n: '01', t: 'Build', d: 'Upload creative, pick DMAs, set dates.' },
        { n: '02', t: 'Fund', d: 'Sign one x402 transfer. We provision a campaign wallet on Solana.' },
        { n: '03', t: 'Settle', d: 'Devices call /bid + /proof. Publishers get paid per play, on-chain.' },
      ].map(s => (
        <div key={s.n} className="x-card" style={{ padding: 18 }}>
          <div className="x-mono" style={{ fontSize: 11, color: 'var(--tx-2)' }}>{s.n}</div>
          <div className="x-display" style={{ fontSize: 16, marginTop: 8 }}>{s.t}</div>
          <div style={{ fontSize: 12, color: 'var(--tx-1)', marginTop: 6, lineHeight: 1.5 }}>{s.d}</div>
        </div>
      ))}
    </div>
  </div>
);

const Sk = ({ w, h = 12, r = 4 }) => (
  <span style={{ display: 'inline-block', width: w, height: h, borderRadius: r,
    background: 'linear-gradient(90deg, var(--bg-2) 0%, var(--bg-3) 50%, var(--bg-2) 100%)',
    backgroundSize: '200% 100%', animation: 'sk-shimmer 1.5s ease-in-out infinite' }} />
);

const OverviewLoading = () => (
  <div style={{ padding: '32px 28px 40px', display: 'flex', flexDirection: 'column', gap: 24 }}>
    <style>{`@keyframes sk-shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`}</style>
    <div>
      <Sk w={140} h={28} r={6} />
      <div style={{ marginTop: 8 }}><Sk w={300} h={12} /></div>
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
      {[1,2,3,4].map(i => (
        <div key={i} className="x-card" style={{ padding: 16, height: 110, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <Sk w={90} h={10} />
          <Sk w={120} h={26} r={6} />
          <Sk w={70} h={10} />
        </div>
      ))}
    </div>
    <div className="x-card" style={{ display: 'flex', overflow: 'hidden' }}>
      {[1,2,3,4,5].map(i => (
        <div key={i} style={{ flex: 1, padding: '14px 16px', borderRight: i < 5 ? '1px solid var(--line-1)' : 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <Sk w={70} h={18} r={9} />
          <Sk w={40} h={20} r={5} />
        </div>
      ))}
    </div>
    <div className="x-card" style={{ padding: '18px 20px' }}>
      <Sk w={120} h={14} />
      <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {[1,2,3,4,5,6].map(i => (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: '70px 1fr 130px 110px 80px', gap: 12, alignItems: 'center' }}>
            <Sk w={50} h={10} /><Sk w={'80%'} h={12} /><Sk w={100} h={10} /><Sk w={70} h={12} /><Sk w={60} h={10} />
          </div>
        ))}
      </div>
    </div>
  </div>
);

Object.assign(window, { OverviewNormal, OverviewEmpty, OverviewLoading });
