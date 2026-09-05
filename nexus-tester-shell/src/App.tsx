import { useMemo, useState } from 'react';
import { Confirmations, FixtureMode, MockNexusClient, QaResult, ReviewResult, TRAFFICKING_COLUMNS } from './NexusClient';
import './styles.css';

type Stage = 'upload'|'review'|'confirm'|'compile'|'qa';
const initial: Confirmations = {client:'',currency:'GBP',flightStart:'2024-07-01',flightEnd:'2024-09-30',campaignName:'',keepSourceRow:''};

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

  const valid = confirmations.client.trim() && /^[A-Z]{3}$/.test(confirmations.currency) && confirmations.flightStart && confirmations.flightEnd && confirmations.flightStart <= confirmations.flightEnd && confirmations.campaignName && confirmations.keepSourceRow;

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

  return <main className="shell">
    <header><div className="brand">NEXUS</div><div className="tag">Campaign Operations, Compiled.</div></header>
    <nav className="steps">{['Upload','Review','Confirm','Compile','QA','Download'].map((s,i)=><span key={s} className={(stage==='upload'?0:stage==='review'?1:stage==='confirm'?2:stage==='compile'?3:4)>=i?'active':''}>{s}</span>)}</nav>
    <section className="devbar"><strong>DEV FIXTURE</strong><button onClick={()=>setMode('success')} className={mode==='success'?'selected':''}>PASS</button><button onClick={()=>setMode('blocked')} className={mode==='blocked'?'selected':''}>BLOCKED</button></section>

    {stage==='upload' && <section className="panel"><h1>Upload campaign workbook</h1><p>Your workbook stays in review mode. Nexus will not publish or change a live campaign.</p><label className="drop">Choose .xlsx<input type="file" accept=".xlsx" onChange={e=>setFile(e.target.files?.[0]||null)}/></label>{file&&<p className="meta">{file.name} · {(file.size/1024).toFixed(1)} KB</p>}<button disabled={!file||busy} onClick={reviewFile}>{busy?'Reviewing…':'Review campaign'}</button></section>}

    {stage==='review' && review && <section className="panel"><h1>Review extracted campaign</h1><div className="grid">{Object.entries(review.facts).map(([k,v])=><div className="fact" key={k}><span>{k}</span><strong className={String(v)==='Needs confirmation'?'warn':''}>{v}</strong></div>)}</div><h2>Platform groups</h2><div className="cards">{review.platformGroups.map(g=><div className="card" key={g.name}><strong>{g.name}</strong><span>{g.rows} rows</span></div>)}</div><button onClick={()=>setStage('confirm')}>Resolve confirmations</button></section>}

    {stage==='confirm' && review && <section className="panel"><h1>Confirm six decisions</h1><div className="form">
      <label>Client<input value={confirmations.client} onChange={e=>input('client',e.target.value)}/><small>Source: workbook campaign context</small></label>
      <label>Currency<input maxLength={3} value={confirmations.currency} onChange={e=>input('currency',e.target.value.toUpperCase())}/><small>Required: 3-letter code</small></label>
      <label>Flight start<input type="date" value={confirmations.flightStart} onChange={e=>input('flightStart',e.target.value)}/><small>Source evidence requires exact date</small></label>
      <label>Flight end<input type="date" value={confirmations.flightEnd} onChange={e=>input('flightEnd',e.target.value)}/><small>Must be on/after start</small></label>
      <label>Campaign name<select value={confirmations.campaignName} onChange={e=>input('campaignName',e.target.value)}><option value="">Choose source candidate</option>{review.campaignNameCandidates.map(x=><option key={x}>{x}</option>)}</select><small>Source-derived candidates only</small></label>
      <label>Duplicate row to retain<select value={confirmations.keepSourceRow} onChange={e=>input('keepSourceRow',e.target.value)}><option value="">Choose source row</option>{review.duplicateRows.map(x=><option key={x}>{x}</option>)}</select><small>Duplicate evidence: {review.duplicateRows.join(' / ')}</small></label>
    </div><button disabled={!valid||busy} onClick={compile}>Confirm and compile</button></section>}

    {stage==='compile' && <section className="panel"><h1>COMPILING</h1><ol className="progress"><li>Validating confirmations</li><li>Separating platform groups</li><li>Building canonical campaign</li><li>Compiling activations</li><li>Running deterministic QA</li></ol></section>}

    {stage==='qa' && qa && <section className="panel"><h1 className={qa.status==='PASS'?'pass':'blocked'}>{qa.status==='PASS'?'READY FOR APPROVAL':'BLOCKED'}</h1>{qa.status==='PASS'?<><div className="grid"><div className="fact"><span>Build rows</span><strong>{qa.buildRows}</strong></div><div className="fact"><span>QA checks passed</span><strong>{qa.checksPassed}</strong></div><div className="fact"><span>Platform</span><strong>Adobe DSP</strong></div><div className="fact"><span>Source evidence</span><strong>Preserved</strong></div></div><p>Nothing has been published.</p><h2>Frozen export columns</h2><ol className="columns">{TRAFFICKING_COLUMNS.map(x=><li key={x}>{x}</li>)}</ol><button onClick={download}>Download trafficking package</button></>:<><p>Fix or confirm the blocking issue before Nexus can generate a trafficking package.</p>{qa.blockers.map(b=><div className="issue" key={b.field}><strong>{b.field}</strong><span>{b.detail}</span><small>{b.sourceRef}</small></div>)}</>}</section>}
    {error&&<p className="error">{error}</p>}
  </main>;
}
