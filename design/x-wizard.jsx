// x-wizard.jsx — Create Campaign wizard (5 steps + funding + success)

const STEPS = [
  { id: 1, label: 'Creative' },
  { id: 2, label: 'Targeting' },
  { id: 3, label: 'Schedule' },
  { id: 4, label: 'Budget' },
  { id: 5, label: 'Review' },
];

const StepDots = ({ current = 1 }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 0, padding: '0 4px' }}>
    {STEPS.map((s, i) => {
      const done = current > s.id;
      const active = current === s.id;
      return (
        <React.Fragment key={s.id}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 22, height: 22, borderRadius: 11, fontSize: 11, fontWeight: 600,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: 'var(--font-mono)',
              background: done ? 'var(--tint-grad-strong)' : active ? 'var(--bg-3)' : 'transparent',
              color: done ? '#08070A' : active ? 'var(--tx-0)' : 'var(--tx-3)',
              border: active ? '1px solid var(--line-3)' : done ? 'none' : '1px solid var(--line-1)',
            }}>
              {done ? <Icon name="check" size={11} stroke={2.4} /> : s.id}
            </div>
            <span style={{ fontSize: 11, color: active ? 'var(--tx-0)' : 'var(--tx-2)', fontWeight: active ? 600 : 500, letterSpacing: '-0.005em' }}>{s.label}</span>
          </div>
          {i < STEPS.length - 1 && <div style={{ flex: 1, height: 1, background: done ? 'var(--tint-grad-strong)' : 'var(--line-1)', margin: '0 12px' }} />}
        </React.Fragment>
      );
    })}
  </div>
);

const Modal = ({ children, step, title = 'New campaign', onBack }) => (
  <div style={{ position: 'absolute', inset: 0, background: 'rgba(4,5,9,0.66)', backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '60px 0' }}>
    <div className="x-card" style={{ width: 640, background: 'var(--bg-1)', boxShadow: 'var(--shadow-card)', overflow: 'hidden' }}>
      <div style={{ padding: '20px 22px 16px', borderBottom: '1px solid var(--line-1)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {onBack && <button className="x-btn x-btn-sm" style={{ width: 28, padding: 0 }}><Icon name="chevron" size={11} stroke={2} /></button>}
            <div>
              <div className="x-display" style={{ fontSize: 16 }}>{title}</div>
              <div style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>step {step} of 5</div>
            </div>
          </div>
          <button style={{ width: 28, height: 28, border: 0, background: 'transparent', color: 'var(--tx-2)', cursor: 'pointer', borderRadius: 6 }}>
            <Icon name="close" size={14} stroke={1.8} />
          </button>
        </div>
        <div style={{ marginTop: 18 }}><StepDots current={step} /></div>
      </div>
      {children}
    </div>
  </div>
);

const Footer = ({ left, right }) => (
  <div style={{ padding: '16px 22px', borderTop: '1px solid var(--line-1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-1)' }}>
    <div>{left}</div>
    <div style={{ display: 'flex', gap: 8 }}>{right}</div>
  </div>
);

// ── STEP 1 — Creative ──────────────────────────────────────────────────────
const WizStep1 = () => (
  <Modal step={1}>
    <div style={{ padding: 22 }}>
      <Lbl>Upload creative</Lbl>
      <div style={{ marginTop: 6, fontSize: 12, color: 'var(--tx-2)' }}>MP4 or PNG/JPG · 1920×1080 · max 10 MB · 6–15 sec for video.</div>

      <div style={{ marginTop: 14, padding: 14, borderRadius: 12, border: '1px solid var(--line-1)', background: 'var(--bg-2)', display: 'flex', gap: 14, alignItems: 'center' }}>
        <div style={{ width: 96, height: 54, borderRadius: 8, background: 'linear-gradient(135deg,#534BB1,#AB9FF2)', position: 'relative', overflow: 'hidden', flexShrink: 0 }}>
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>Phantom</div>
          <div style={{ position: 'absolute', bottom: 4, right: 4, fontSize: 9, color: 'rgba(255,255,255,0.8)', fontFamily: 'var(--font-mono)' }}>1920×1080</div>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 500 }}>phantom-mobile-push-v3.mp4</div>
          <div style={{ fontSize: 11, color: 'var(--tx-2)', marginTop: 2, fontFamily: 'var(--font-mono)' }}>4.2 MB · 12s · ✓ format ok</div>
          <div style={{ marginTop: 8 }}><Progress value={1} color="var(--sol-teal)" /></div>
        </div>
        <button style={{ width: 28, height: 28, border: 0, background: 'transparent', color: 'var(--tx-2)', cursor: 'pointer', borderRadius: 6 }}>
          <Icon name="close" size={13} />
        </button>
      </div>

      <div style={{ marginTop: 14, height: 96, borderRadius: 12, border: '1.5px dashed var(--line-2)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 6, color: 'var(--tx-2)' }}>
        <Icon name="upload" size={18} />
        <div style={{ fontSize: 12 }}>Drop a file, or <span style={{ color: 'var(--x402-blue-hi)', fontWeight: 500 }}>browse</span> to swap</div>
      </div>
    </div>
    <Footer
      left={<span style={{ fontSize: 11, color: 'var(--sol-teal)', fontFamily: 'var(--font-mono)' }}><Icon name="check" size={11} stroke={2}/> Creative validated</span>}
      right={<button className="x-btn x-btn-primary">Next <Icon name="arrowRight" size={12} stroke={2} /></button>}
    />
  </Modal>
);

const Lbl = ({ children }) => (
  <div style={{ fontSize: 11, color: 'var(--tx-2)', letterSpacing: '0.08em', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>{children}</div>
);

// ── STEP 2 — Targeting ─────────────────────────────────────────────────────
const WizStep2 = () => {
  const selected = ['nyc','la','sf'];
  const total = DMAS.filter(d => selected.includes(d.id)).reduce((s,d)=>s+d.screens, 0);
  return (
    <Modal step={2} onBack>
      <div style={{ padding: 22 }}>
        <Lbl>Pick markets (DMAs)</Lbl>
        <div style={{ marginTop: 6, fontSize: 12, color: 'var(--tx-2)' }}>Each DMA includes its full screen network.</div>

        <div style={{ marginTop: 14, display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
          {DMAS.map(d => {
            const sel = selected.includes(d.id);
            return (
              <div key={d.id} style={{
                padding: 14, borderRadius: 12,
                background: sel ? 'rgba(20,241,149,0.06)' : 'var(--bg-2)',
                border: `1px solid ${sel ? 'rgba(20,241,149,0.30)' : 'var(--line-1)'}`,
                position: 'relative',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{d.dma}</div>
                  <div style={{ width: 16, height: 16, borderRadius: 4, border: `1px solid ${sel ? 'var(--sol-teal)' : 'var(--line-2)'}`, background: sel ? 'var(--sol-teal)' : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {sel && <Icon name="check" size={10} stroke={3} />}
                  </div>
                </div>
                <div className="x-mono x-tnum" style={{ fontSize: 16, marginTop: 6, color: sel ? 'var(--tx-0)' : 'var(--tx-1)' }}>{d.screens.toLocaleString()}</div>
                <div style={{ fontSize: 10, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>screens</div>
              </div>
            );
          })}
        </div>

        <div style={{ marginTop: 16, padding: '12px 14px', borderRadius: 10, background: 'var(--bg-2)', border: '1px solid var(--line-1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>REACH</div>
            <div className="x-display x-tnum" style={{ fontSize: 22, marginTop: 2 }}>
              {total.toLocaleString()} <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>screens</span>
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>FREQUENCY</div>
            <div style={{ fontSize: 13, marginTop: 4, fontFamily: 'var(--font-mono)' }}>1 play every 5 min</div>
          </div>
        </div>
      </div>
      <Footer
        left={<span style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>{selected.length} of 6 markets selected</span>}
        right={<><button className="x-btn">Back</button><button className="x-btn x-btn-primary">Next <Icon name="arrowRight" size={12} stroke={2} /></button></>}
      />
    </Modal>
  );
};

// ── STEP 3 — Schedule ──────────────────────────────────────────────────────
const WizStep3 = () => (
  <Modal step={3} onBack>
    <div style={{ padding: 22 }}>
      <Lbl>Schedule</Lbl>
      <div style={{ marginTop: 6, fontSize: 12, color: 'var(--tx-2)' }}>Plays start at 00:00 UTC on the start date.</div>

      <div style={{ marginTop: 14, display: 'grid', gridTemplateColumns: '1fr 24px 1fr', alignItems: 'center', gap: 14 }}>
        <DateField label="Start date" value="Apr 28, 2026" weekday="Tue" />
        <Icon name="arrowRight" size={14} />
        <DateField label="End date" value="May 12, 2026" weekday="Tue" />
      </div>

      <div style={{ marginTop: 14, padding: '12px 14px', borderRadius: 10, background: 'var(--bg-2)', border: '1px solid var(--line-1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: 12, color: 'var(--tx-1)' }}>Duration</div>
        <div className="x-mono" style={{ fontSize: 13, fontWeight: 500 }}>14 days</div>
      </div>

      <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: 'var(--sol-teal)', fontFamily: 'var(--font-mono)' }}>
        <Icon name="check" size={11} stroke={2.4} /> Schedule valid · 4,032 plays projected
      </div>
    </div>
    <Footer
      left={null}
      right={<><button className="x-btn">Back</button><button className="x-btn x-btn-primary">Next <Icon name="arrowRight" size={12} stroke={2} /></button></>}
    />
  </Modal>
);

const DateField = ({ label, value, weekday }) => (
  <div>
    <Lbl>{label}</Lbl>
    <div style={{ marginTop: 6, padding: '12px 14px', borderRadius: 10, border: '1px solid var(--line-2)', background: 'var(--bg-2)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <span style={{ fontSize: 14, fontWeight: 500 }}>{value}</span>
        <span style={{ fontSize: 10, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>{weekday}</span>
      </div>
      <Icon name="calendar" size={14} stroke={1.6} />
    </div>
  </div>
);

// ── STEP 4 — Budget ────────────────────────────────────────────────────────
const WizStep4 = ({ insufficient = false }) => {
  const screens = 3545;
  const playsPerScreenPerDay = 96;
  const days = 14;
  const totalPlays = 49630; // capped
  const cpm = 1.28;
  const total = (totalPlays / 1000) * cpm;
  const fee = total * 0.025;
  const escrow = total + fee;
  const balance = insufficient ? 4200 : 7500;

  return (
    <Modal step={4} onBack>
      <div style={{ padding: 22 }}>
        <Lbl>Budget · auto-derived</Lbl>
        <div style={{ marginTop: 6, fontSize: 12, color: 'var(--tx-2)' }}>CPM is locked at 1.28 USDC during devnet.</div>

        <div className="x-card" style={{ marginTop: 14, background: 'var(--bg-2)' }}>
          <Calc label="Screens" value={screens.toLocaleString()} mono />
          <Calc label="Plays / screen / day" value={playsPerScreenPerDay} mono />
          <Calc label="Days" value={days} mono />
          <Calc label="Total plays" value={totalPlays.toLocaleString()} bold mono />
          <Calc label={<span>CPM <span style={{ color: 'var(--tx-3)' }}>(locked)</span></span>} value={`${cpm.toFixed(2)} USDC`} mono />
          <Calc label="Total" value={`${total.toFixed(2)} USDC`} mono bold />
          <Calc label="Protocol fee · 2.5%" value={`${fee.toFixed(2)} USDC`} mono muted />
          <Calc label="Total to escrow" value={`${escrow.toFixed(2)} USDC`} highlight />
        </div>

        <div style={{ marginTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', borderRadius: 10, background: insufficient ? 'rgba(255,122,69,0.06)' : 'var(--bg-2)', border: `1px solid ${insufficient ? 'rgba(255,122,69,0.30)' : 'var(--line-1)'}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon name="wallet" size={14} />
            <span style={{ fontSize: 12, color: 'var(--tx-1)' }}>Wallet balance</span>
          </div>
          <span className="x-mono x-tnum" style={{ fontWeight: 500, color: insufficient ? 'var(--st-expired)' : 'var(--tx-0)' }}>
            {balance.toLocaleString('en-US',{minimumFractionDigits:2})} USDC
          </span>
        </div>

        {insufficient && (
          <div style={{ marginTop: 8, fontSize: 11, color: 'var(--st-expired)', fontFamily: 'var(--font-mono)' }}>
            Insufficient balance · need {(escrow - balance).toFixed(2)} more USDC. Use the faucet from the wallet menu.
          </div>
        )}
      </div>
      <Footer
        left={<span style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>x402 quote · valid 2 min</span>}
        right={<><button className="x-btn">Back</button><button className="x-btn x-btn-primary" disabled={insufficient} style={insufficient ? { opacity: 0.5, pointerEvents: 'none' } : {}}>Next <Icon name="arrowRight" size={12} stroke={2} /></button></>}
      />
    </Modal>
  );
};

const Calc = ({ label, value, bold, mono, muted, highlight }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '10px 14px', borderTop: '1px solid var(--line-1)',
    background: highlight ? 'linear-gradient(135deg, rgba(153,69,255,0.08), rgba(20,241,149,0.04))' : 'transparent' }}>
    <span style={{ fontSize: 12, color: muted ? 'var(--tx-2)' : 'var(--tx-1)' }}>{label}</span>
    <span className={mono ? 'x-mono x-tnum' : 'x-tnum'} style={{ fontSize: highlight ? 15 : 13, fontWeight: bold || highlight ? 600 : 500, color: highlight ? 'var(--tx-0)' : muted ? 'var(--tx-2)' : 'var(--tx-0)' }}>{value}</span>
  </div>
);

// ── STEP 5 — Review ────────────────────────────────────────────────────────
const WizStep5 = () => (
  <Modal step={5} onBack>
    <div style={{ padding: 22 }}>
      <Lbl>Campaign name</Lbl>
      <input className="x-input" defaultValue="Phantom · Mobile push" style={{ marginTop: 6 }} />

      <div className="x-card" style={{ marginTop: 16, background: 'var(--bg-2)', overflow: 'hidden' }}>
        <ReviewRow label="Creative" value={
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 36, height: 20, borderRadius: 4, background: 'linear-gradient(135deg,#534BB1,#AB9FF2)' }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>phantom-mobile-push-v3.mp4</span>
          </div>
        } />
        <ReviewRow label="Markets" value="New York · Los Angeles · San Francisco" sub="3,545 screens" />
        <ReviewRow label="Schedule" value="Apr 28 → May 12, 2026" sub="14 days" />
        <ReviewRow label="Plays projected" value="49,630" mono />
        <ReviewRow label="CPM" value="1.28 USDC" mono />
        <ReviewRow label="Protocol fee · 2.5%" value="1.59 USDC" mono muted />
        <ReviewRow label="Total to escrow" value="65.13 USDC" highlight />
      </div>

      <div style={{ marginTop: 12, display: 'flex', alignItems: 'flex-start', gap: 10, padding: 12, borderRadius: 10, background: 'rgba(61,90,254,0.06)', border: '1px solid rgba(61,90,254,0.20)' }}>
        <Icon name="info" size={14} stroke={1.8} />
        <div style={{ fontSize: 11, color: 'var(--tx-1)', lineHeight: 1.5 }}>
          We'll spin up a <span style={{ fontFamily: 'var(--font-mono)' }}>fresh per-campaign Privy server wallet</span>, transfer escrow via x402, and skim the 2.5% protocol fee in the same flow.
        </div>
      </div>
    </div>
    <Footer
      left={null}
      right={<>
        <button className="x-btn">Back</button>
        <button className="x-btn x-btn-grad x-btn-lg" style={{ height: 40 }}>
          <Icon name="check" size={12} stroke={2.4} /> Confirm &amp; Fund
        </button>
      </>}
    />
  </Modal>
);

const ReviewRow = ({ label, value, sub, mono, muted, highlight }) => (
  <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: 16, padding: '12px 14px',
    borderTop: '1px solid var(--line-1)',
    background: highlight ? 'linear-gradient(135deg, rgba(153,69,255,0.08), rgba(20,241,149,0.04))' : 'transparent' }}>
    <span style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</span>
    <div style={{ textAlign: 'right' }}>
      <div className={mono ? 'x-mono x-tnum' : 'x-tnum'} style={{ fontSize: highlight ? 16 : 13, fontWeight: highlight ? 600 : 500, color: muted ? 'var(--tx-2)' : 'var(--tx-0)' }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>{sub}</div>}
    </div>
  </div>
);

// ── Funding (in-progress) ──────────────────────────────────────────────────
const WizFunding = ({ stage = 1 }) => (
  <Modal step={5}>
    <div style={{ padding: '40px 22px 28px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
        <div style={{ position: 'relative', width: 64, height: 64 }}>
          <div style={{ position: 'absolute', inset: 0, borderRadius: 32, background: 'var(--tint-grad-strong)', filter: 'blur(20px)', opacity: 0.6 }} />
          <div style={{ position: 'relative', width: 64, height: 64, borderRadius: 32, border: '2px solid transparent', background: 'conic-gradient(from 0deg, var(--sol-purple), var(--sol-teal), var(--sol-purple))', maskImage: 'radial-gradient(circle, transparent 26px, #000 27px)', WebkitMaskImage: 'radial-gradient(circle, transparent 26px, #000 27px)', animation: 'fund-spin 1.4s linear infinite' }} />
          <style>{`@keyframes fund-spin{ to{ transform: rotate(360deg) } }`}</style>
        </div>
        <div className="x-display" style={{ fontSize: 18, marginTop: 6 }}>Funding campaign</div>
      </div>

      <div style={{ marginTop: 24, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {[
          { id: 1, label: 'Creating campaign wallet', detail: 'Privy · server-side' },
          { id: 2, label: 'Sign x402 transfer', detail: 'in popup · 65.13 USDC' },
          { id: 3, label: 'Settling on Solana', detail: 'devnet RPC · 2 confirmations' },
        ].map(s => {
          const done = stage > s.id, cur = stage === s.id;
          return (
            <div key={s.id} style={{ padding: '12px 14px', borderRadius: 10, display: 'flex', alignItems: 'center', gap: 12,
              background: cur ? 'var(--bg-2)' : 'transparent', border: `1px solid ${cur ? 'var(--line-2)' : 'transparent'}` }}>
              <div style={{ width: 22, height: 22, borderRadius: 11, display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: done ? 'var(--sol-teal)' : cur ? 'transparent' : 'var(--bg-3)',
                border: cur ? '2px solid var(--sol-purple)' : 'none', color: '#08070A' }}>
                {done ? <Icon name="check" size={12} stroke={3} /> : cur ? <span style={{ width: 6, height: 6, borderRadius: 3, background: 'var(--sol-purple)' }} /> : null}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, color: cur ? 'var(--tx-0)' : done ? 'var(--tx-1)' : 'var(--tx-3)', fontWeight: cur ? 600 : 500 }}>{s.label}</div>
                <div style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>{s.detail}</div>
              </div>
              {done && <Solscan>view tx</Solscan>}
              {cur && <span style={{ fontSize: 11, color: 'var(--sol-teal)', fontFamily: 'var(--font-mono)' }}>pending…</span>}
            </div>
          );
        })}
      </div>
    </div>
    <Footer left={<span style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>do not close this window</span>} right={<button className="x-btn" disabled style={{ opacity: 0.5, pointerEvents: 'none' }}>Cancel</button>} />
  </Modal>
);

// ── Success ────────────────────────────────────────────────────────────────
const WizSuccess = () => (
  <Modal step={5} title="Campaign live">
    <div style={{ padding: '40px 22px 24px', textAlign: 'center' }}>
      <div style={{ width: 64, height: 64, margin: '0 auto', borderRadius: 32, background: 'rgba(20,241,149,0.12)', border: '1px solid rgba(20,241,149,0.40)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 12px 40px rgba(20,241,149,0.25)' }}>
        <Icon name="check" size={26} stroke={2.4} />
      </div>
      <div className="x-display" style={{ fontSize: 22, marginTop: 18, letterSpacing: '-0.02em' }}>
        <span className="x-grad-text">Phantom · Mobile push</span> is live
      </div>
      <div style={{ fontSize: 12, color: 'var(--tx-2)', marginTop: 8, fontFamily: 'var(--font-mono)' }}>
        65.13 USDC escrowed · campaign wallet F8q2…7cN1
      </div>

      <div style={{ marginTop: 22, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <SuccessTx label="Funding tx" tx="5gT2p9aQF8Nx…" />
        <SuccessTx label="Protocol fee tx" tx="B2p7kL1c4dRm…" />
      </div>
    </div>
    <Footer
      left={<span style={{ fontSize: 11, color: 'var(--tx-2)', fontFamily: 'var(--font-mono)' }}>publishers will start bidding within ~30s</span>}
      right={<><button className="x-btn">View campaign</button><button className="x-btn x-btn-primary">Done</button></>}
    />
  </Modal>
);

const SuccessTx = ({ label, tx }) => (
  <div className="x-card" style={{ padding: '12px 14px', textAlign: 'left', background: 'var(--bg-2)' }}>
    <Lbl>{label}</Lbl>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6 }}>
      <span className="x-mono" style={{ fontSize: 12 }}>{tx}</span>
      <Solscan />
    </div>
  </div>
);

Object.assign(window, { WizStep1, WizStep2, WizStep3, WizStep4, WizStep5, WizFunding, WizSuccess });
