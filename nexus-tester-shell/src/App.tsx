import { useMemo, useState } from 'react';
import { Confirmations, FixtureMode, MockNexusClient, QaResult, ReviewResult, TRAFFICKING_COLUMNS } from './NexusClient';
import './styles.css';

type Stage = 'upload'|'review'|'confirm'|'compile'|'qa';
const initial: Confirmations = {client:'',currency:'',flightStart:'',flightEnd:'',campaignName:'',keepSourceRow:''};

const origins = {
  source: 'SOURCE',
  deterministic: 'DETERMINISTIC',
  human: 'HUMAN CONFIRMATION',
} as const;

export default function App() {
  const [mode,setMode] = useState<FixtureMode>('success');
  const client = useMemo(() => new MockNexusClient(mode), [mode]);
  const [stage,setStage] = useState<Stage>('upload');
  const [file,setFile] = useState<File|null>(null);
  const [review,setReview] = useState<ReviewResult|null>(null);
  const [confirmations,setConfirmations] = useState<Confirmations>(initial);
  const [qa,setQa] = useState<QaResult|null>(null);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const [showPackage,setShowPackage] = useState(false);

  const valid = Boolean(confirmations.client.trim() && /^[A-Z]{3}$/.test(confirmations.currency) && confirmations.flightStart && confirmations.flightEnd && confirmations.flightStart <= confirmations.flightEnd && confirmations.campaignName && confirmations.keepSourceRow);
  const confirmationCount = [confirmations.client,confirmations.currency,confirmations.flightStart,confirmations.flightEnd,confirmations.campaignName,confirmations.keepSourceRow].filter(Boolean).length;

  const runStatus = stage === 'upload' ? (busy ? 'UNDERSTANDING' : 'READY')
    : stage === 'review' || stage === 'confirm' ? 'NEEDS YOU'
    : stage === 'compile' ? 'BUILDING'
    : qa?.status === 'PASS' ? 'READY FOR APPROVAL'
    : 'BLOCKED';

  async function reviewFile() {
    if (!file) return;
    setBusy(true); setError('');
    try { setReview(await client.reviewWorkbook(file)); setStage('review'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Review failed.'); }
    finally { setBusy(false); }
  }

  async function compile() {
    if (!review || !valid) return;
    setBusy(true); setError(''); setStage('compile');
    try {
      await client.submitConfirmations(review.runId, confirmations);
      await client.compileCampaign(review.runId);
      setQa(await client.getQaResult(review.runId));
      setStage('qa');
    } catch (e) { setError(e instanceof Error ? e.message : 'Compile failed.'); setStage('confirm'); }
    finally { setBusy(false); }
  }

  async function download() {
    if (!review || qa?.status !== 'PASS') return;
    const blob = await client.downloadPackage(review.runId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'nexus_trafficking.csv'; a.click(); URL.revokeObjectURL(url);
  }

  const input = (key:keyof Confirmations, value:string) => setConfirmations(v => ({...v,[key]:value}));
  const sectionState = (name:'understand'|'ask'|'act'|'verify'|'approve') => {
    if (name === 'understand') return stage === 'upload' ? 'current' : 'complete';
    if (name === 'ask') return stage === 'review' || stage === 'confirm' ? 'current' : stage === 'upload' ? 'locked' : 'complete';
    if (name === 'act') return stage === 'compile' ? 'current' : stage === 'qa' ? 'complete' : 'locked';
    if (name === 'verify') return stage === 'qa' ? 'current' : 'locked';
    if (name === 'approve') return stage === 'qa' && qa?.status === 'PASS' ? 'current' : 'locked';
    return 'locked';
  };

  return <main className="agent-shell">
    <header className="agent-header">
      <div><div className="brand">NEXUS</div><div className="tag">Campaign Operations, Compiled.</div></div>
      <div className={`run-status ${runStatus.toLowerCase().replaceAll(' ','-')}`}>{runStatus}</div>
    </header>

    <section className="trustbar">
      <span className="pulse-dot" />
      <strong>NEXUS AGENT RUN</strong>
      <span>Nothing publishes without approval.</span>
    </section>

    <section className="devbar"><strong>DEV FIXTURE</strong><button onClick={()=>setMode('success')} className={mode==='success'?'selected':''}>PASS</button><button onClick={()=>setMode('blocked')} className={mode==='blocked'?'selected':''}>BLOCKED</button></section>

    <div className="timeline">
      <section className={`run-step ${sectionState('understand')}`}>
        <div className="step-rail"><span>01</span></div>
        <div className="step-body">
          <div className="step-head"><div><p className="eyebrow">UNDERSTAND</p><h1>{review ? 'Campaign understood' : 'Give Nexus the campaign'}</h1></div><span className="state-chip">{review ? 'COMPLETE' : busy ? 'READING' : 'READY'}</span></div>

          {!review && <>
            <p className="lede">Drop in one approved or historical campaign workbook. Nexus will inspect the structure, preserve source evidence and stop where facts are ambiguous.</p>
            <label className="drop"><span>{file ? file.name : 'Choose .xlsx workbook'}</span><input type="file" accept=".xlsx" onChange={e=>setFile(e.target.files?.[0]||null)}/></label>
            {file&&<p className="meta">{(file.size/1024).toFixed(1)} KB · review mode only</p>}
            <button disabled={!file||busy} onClick={reviewFile}>{busy?'Understanding campaign…':'Start agent run'}</button>
          </>}

          {review && <>
            <div className="signal-grid">
              <Metric value={review.facts['Source rows']} label="source rows" />
              <Metric value={review.platformGroups.length} label="platforms" />
              <Metric value={review.facts.Creatives} label="creatives" />
              <Metric value={review.facts.Activations} label="activations" />
            </div>
            <div className="event-list">
              <Event text={`${review.facts['Source rows']} source rows read`} origin={origins.source} done />
              <Event text={`${review.platformGroups.length} platforms identified`} origin={origins.deterministic} done />
              <Event text={`${review.facts.Creatives} creatives mapped`} origin={origins.deterministic} done />
              <Event text={`${review.facts.Activations} activation candidates found`} origin={origins.deterministic} done />
              <Event text={`1 duplicate activation candidate · ${review.duplicateRows.join(' / ')}`} origin={origins.source} warning />
            </div>
            <div className="platform-row">{review.platformGroups.map(g=><div className="platform-pill" key={g.name}><strong>{g.name}</strong><span>{g.rows}</span></div>)}</div>
            <div className="known-unknown">
              <div><p className="mini-title">Known from source</p><Fact label="Objective" value={String(review.facts.Objective)} origin={origins.source}/><Fact label="Market" value={String(review.facts.Market)} origin={origins.source}/></div>
              <div><p className="mini-title">Nexus will not guess</p><Fact label="Client" value="Needs confirmation" warning/><Fact label="Currency / flight" value="Needs confirmation" warning/></div>
            </div>
            {stage==='review' && <button onClick={()=>setStage('confirm')}>Resolve 6 decisions</button>}
          </>}
        </div>
      </section>

      <section className={`run-step ${sectionState('ask')}`}>
        <div className="step-rail"><span>02</span></div>
        <div className="step-body">
          <div className="step-head"><div><p className="eyebrow">ASK</p><h2>Nexus needs 6 decisions</h2><p className="subcopy">Everything else can continue without you.</p></div><span className="state-chip">{stage==='confirm'?`${confirmationCount}/6`:sectionState('ask')==='complete'?'COMPLETE':'LOCKED'}</span></div>

          {stage==='confirm' && review && <>
            <div className="decision-stack">
              <Decision label="Client" complete={Boolean(confirmations.client)} evidence="Workbook campaign context"><input value={confirmations.client} onChange={e=>input('client',e.target.value)} placeholder="Enter client"/></Decision>
              <Decision label="Currency" complete={/^[A-Z]{3}$/.test(confirmations.currency)} evidence="3-letter currency code"><input maxLength={3} value={confirmations.currency} onChange={e=>input('currency',e.target.value.toUpperCase())} placeholder="GBP"/></Decision>
              <Decision label="Flight start" complete={Boolean(confirmations.flightStart)} evidence="Exact date required"><input type="date" value={confirmations.flightStart} onChange={e=>input('flightStart',e.target.value)}/></Decision>
              <Decision label="Flight end" complete={Boolean(confirmations.flightEnd) && confirmations.flightStart <= confirmations.flightEnd} evidence="Must be on or after start"><input type="date" value={confirmations.flightEnd} onChange={e=>input('flightEnd',e.target.value)}/></Decision>
              <Decision label="Campaign name" complete={Boolean(confirmations.campaignName)} evidence="Source-derived candidates only"><select value={confirmations.campaignName} onChange={e=>input('campaignName',e.target.value)}><option value="">Choose source candidate</option>{review.campaignNameCandidates.map(x=><option key={x}>{x}</option>)}</select></Decision>
              <Decision label="Duplicate row to retain" complete={Boolean(confirmations.keepSourceRow)} evidence={`Source evidence: ${review.duplicateRows.join(' / ')}`}><select value={confirmations.keepSourceRow} onChange={e=>input('keepSourceRow',e.target.value)}><option value="">Choose source row</option>{review.duplicateRows.map(x=><option key={x}>{x}</option>)}</select></Decision>
            </div>
            <button className="sticky-action" disabled={!valid||busy} onClick={compile}>Let Nexus continue</button>
          </>}

          {sectionState('ask')==='complete' && <div className="compact-summary"><span className="checkmark">✓</span><div><strong>6 decisions confirmed</strong><small>{origins.human}</small></div></div>}
        </div>
      </section>

      <section className={`run-step ${sectionState('act')}`}>
        <div className="step-rail"><span>03</span></div>
        <div className="step-body">
          <div className="step-head"><div><p className="eyebrow">ACT</p><h2>{stage==='compile'?'Nexus is building the campaign':'Campaign build'}</h2></div><span className="state-chip">{stage==='compile'?'WORKING':stage==='qa'?'COMPLETE':'LOCKED'}</span></div>
          {(stage==='compile'||stage==='qa') && <div className="event-list run-events">
            <Event text="Confirmations validated" origin={origins.deterministic} done />
            <Event text="Platforms separated safely" origin={origins.deterministic} done />
            <Event text="Adobe DSP selected" origin={origins.deterministic} done />
            <Event text="Canonical campaign built" origin={origins.deterministic} done={stage==='qa'} active={stage==='compile'} />
            <Event text="8 activation identities preserved" origin={origins.deterministic} done={stage==='qa'} active={stage==='compile'} />
            <Event text="8 build rows compiled" origin={origins.deterministic} done={stage==='qa'} active={stage==='compile'} />
            <Event text="Sending build to deterministic QA" origin={origins.deterministic} done={stage==='qa'} active={stage==='compile'} />
          </div>}
        </div>
      </section>

      <section className={`run-step ${sectionState('verify')}`}>
        <div className="step-rail"><span>04</span></div>
        <div className="step-body">
          <div className="step-head"><div><p className="eyebrow">VERIFY</p><h2>Verify the build</h2></div><span className="state-chip">{stage==='qa'?(qa?.status==='PASS'?'QA PASS':'BLOCKED'):'LOCKED'}</span></div>
          {stage==='qa' && qa && <>
            {qa.status==='PASS' ? <>
              <div className="qa-hero pass"><strong>QA PASS</strong><span>The AI does not grade its own homework. Deterministic checks do.</span></div>
              <div className="verify-grid"><Metric value={`${qa.checksPassed}/${qa.checksPassed}`} label="checks passed"/><Metric value={`${qa.buildRows}/${qa.buildRows}`} label="build rows valid"/><Metric value="0" label="blocking failures"/><Metric value="14" label="export columns"/></div>
              <div className="event-list"><Event text="Source evidence preserved" origin={origins.deterministic} done/><Event text="Stable identities preserved" origin={origins.deterministic} done/><Event text="Frozen trafficking contract valid" origin={origins.deterministic} done/></div>
            </> : <>
              <div className="qa-hero fail"><strong>BLOCKED</strong><span>Package generation stopped before approval.</span></div>
              {qa.blockers.map(b=><div className="issue" key={b.field}><div><strong>{b.field}</strong><span>{b.detail}</span></div><small>{b.sourceRef}</small></div>)}
              <p className="blocked-copy">Fix or confirm the blocking issue before Nexus can generate a trafficking package.</p>
            </>}
          </>}
        </div>
      </section>

      <section className={`run-step ${sectionState('approve')}`}>
        <div className="step-rail"><span>05</span></div>
        <div className="step-body">
          <div className="step-head"><div><p className="eyebrow">APPROVE</p><h2>{qa?.status==='PASS'?'READY FOR APPROVAL':'Approval'}</h2></div><span className="state-chip">{qa?.status==='PASS'?'READY':'LOCKED'}</span></div>
          {qa?.status==='PASS' && <>
            <div className="approval-hero"><span className="hero-number">8</span><div><strong>Adobe DSP activations built</strong><p>6 decisions from you · 8 build rows from Nexus · {qa.checksPassed} deterministic QA checks passed · 0 blockers</p></div></div>
            <div className="approval-actions"><button className="secondary" onClick={()=>setShowPackage(v=>!v)}>{showPackage?'Hide package contract':'Review trafficking package'}</button><button onClick={download}>Download nexus_trafficking.csv</button></div>
            {showPackage && <ol className="columns">{TRAFFICKING_COLUMNS.map(x=><li key={x}>{x}</li>)}</ol>}
            <p className="nothing-published">Nothing has been published.</p>
          </>}
        </div>
      </section>
    </div>

    {error&&<p className="error">{error}</p>}
  </main>;
}

function Metric({value,label}:{value:React.ReactNode;label:string}) {
  return <div className="metric"><strong>{value}</strong><span>{label}</span></div>;
}

function Event({text,origin,done=false,warning=false,active=false}:{text:string;origin:string;done?:boolean;warning?:boolean;active?:boolean}) {
  return <div className={`event ${warning?'warning':''} ${active?'active-event':''}`}><span className="event-icon">{warning?'!':done?'✓':'→'}</span><div><strong>{text}</strong><small>{origin}</small></div></div>;
}

function Fact({label,value,origin,warning=false}:{label:string;value:string;origin?:string;warning?:boolean}) {
  return <div className="mini-fact"><div><span>{label}</span><strong className={warning?'warn':''}>{value}</strong></div>{origin&&<small>{origin}</small>}</div>;
}

function Decision({label,complete,evidence,children}:{label:string;complete:boolean;evidence:string;children:React.ReactNode}) {
  return <label className={`decision ${complete?'confirmed':''}`}><div className="decision-head"><strong>{label}</strong><span>{complete?'CONFIRMED ✓':'REQUIRED'}</span></div>{children}<small>{evidence}</small></label>;
}
