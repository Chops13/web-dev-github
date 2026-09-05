export const TRAFFICKING_COLUMNS = [
  'Campaign_Key','Plan_Row_ID','Platform','Campaign_Name','Placement_Name','Ad_Format','Flight_Dates',
  'Audience_Targeting','Creative_ID','Landing_Page_URL','Final_Tracking_URL','Activation_ID','Audience_Row_ID','Creative_Row_ID'
] as const;

export type FixtureMode = 'success' | 'blocked';
export type Confirmations = {
  client: string;
  currency: string;
  flightStart: string;
  flightEnd: string;
  campaignName: string;
  keepSourceRow: string;
};

export type ReviewResult = {
  runId: string;
  facts: Record<string, string | number>;
  platformGroups: Array<{name:string; rows:number}>;
  campaignNameCandidates: string[];
  duplicateRows: string[];
};

export type QaResult = {
  status: 'PASS' | 'BLOCKED';
  buildRows: number;
  checksPassed: number;
  blockers: Array<{field:string; detail:string; sourceRef?:string}>;
};

export interface NexusClient {
  reviewWorkbook(file: File): Promise<ReviewResult>;
  submitConfirmations(runId: string, confirmations: Confirmations): Promise<void>;
  compileCampaign(runId: string): Promise<void>;
  getQaResult(runId: string): Promise<QaResult>;
  downloadPackage(runId: string): Promise<Blob>;
}

const wait = (ms:number) => new Promise(resolve => setTimeout(resolve, ms));

export class MockNexusClient implements NexusClient {
  // Development-only visual/state fixture. Never publishes or writes to ad platforms.
  constructor(private mode: FixtureMode = 'success') {}

  async reviewWorkbook(file: File): Promise<ReviewResult> {
    if (!file.name.toLowerCase().endsWith('.xlsx')) throw new Error('Upload one .xlsx workbook.');
    if (file.size > 5 * 1024 * 1024) throw new Error('Workbook must be 5 MB or smaller.');
    await wait(450);
    return {
      runId: 'benchmark-adobe-v0',
      facts: {
        Client: 'Needs confirmation',
        'Campaign name': 'Needs confirmation',
        Objective: 'Traffic',
        Market: 'UK',
        Currency: 'Needs confirmation',
        Flight: 'Needs confirmation',
        Platforms: 'Adobe DSP, Facebook, LinkedIn',
        'Source rows': 13,
        Audiences: 1,
        Creatives: 12,
        Activations: 13,
      },
      platformGroups: [
        {name:'Adobe DSP', rows:8},
        {name:'Facebook', rows:3},
        {name:'LinkedIn', rows:2},
      ],
      campaignNameCandidates: ['Tech Innovation 2024', 'Campaign Innovators 2024'],
      duplicateRows: ['tracking code generator!14', 'tracking code generator!15'],
    };
  }

  async submitConfirmations(_runId: string, _confirmations: Confirmations): Promise<void> { await wait(180); }
  async compileCampaign(_runId: string): Promise<void> { await wait(900); }

  async getQaResult(_runId: string): Promise<QaResult> {
    await wait(250);
    if (this.mode === 'blocked') {
      return {
        status: 'BLOCKED', buildRows: 8, checksPassed: 6,
        blockers: [{field:'Final_Tracking_URL', detail:'Required final tracking URL is missing.', sourceRef:'tracking code generator!3'}],
      };
    }
    return {status:'PASS', buildRows:8, checksPassed:7, blockers:[]};
  }

  async downloadPackage(_runId: string): Promise<Blob> {
    if (this.mode === 'blocked') throw new Error('Package is unavailable while QA is blocked.');
    const rows = Array.from({length:8}, (_,i) => [
      'CMP-BENCHMARK','tracking code generator!'+(i+3),'Adobe DSP','Tech Innovation 2024','display ad',
      'Standard Display','2024-07-01 to 2024-09-30','Bespoke Tech Audience','Display '+(i+1),
      'https://example.test/landing','https://example.test/landing?utm_source=test','ACT-'+(i+1),'AUD-BENCH','CRE-'+(i+1)
    ]);
    const csv = [TRAFFICKING_COLUMNS.join(','), ...rows.map(row => row.map(v => `"${String(v).replaceAll('"','""')}"`).join(','))].join('\n');
    return new Blob([csv], {type:'text/csv'});
  }
}
