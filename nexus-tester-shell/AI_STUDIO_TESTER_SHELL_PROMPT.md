# Nexus AI Studio Tester Shell — Frozen Build Prompt

## Purpose
Build only the tester-facing shell for Nexus. Do not change Nexus backend logic.

## Frozen product promise
Upload an approved or historical campaign workbook. Nexus reviews what it understood, asks only for unresolved confirmations, compiles deterministically, runs QA, and returns a trafficking package ready for human approval.

## Frozen benchmark evidence
Controlled historical benchmark:
- 13 source rows preserved
- 8 Adobe DSP rows selected
- 6 explicit human confirmations
- 8/8 Adobe activations compiled
- 72/72 operator-facing fields matched in controlled parity replay
- deterministic QA: PASS
- final package: 8 rows using the frozen 14-column trafficking contract
- final state: READY_FOR_APPROVAL
- do not display the 757x mechanical compute comparison as a user-facing claim
- do not claim human operator time savings yet

## Hard scope
Create a new frontend shell only inside `nexus-tester-shell/`.
Do not edit anything inside `nexus-mcp/`.
Do not modify Hermes, MCP, compiler, canonical IDs, QA rules, package generation, CSV ordering, or historical mapper logic.
Do not add Gemini runtime reasoning, chat UI, autonomous actions, browser automation, platform publishing, DV360/CM360 writes, authentication, billing, databases, campaign history, notifications, or analytics.
Do not invent campaign facts.
Do not silently auto-confirm anything.

## Required tester flow
Exactly this primary flow:

`Upload → Review → Confirm → Compile → QA → Download`

### 1. Upload
- One `.xlsx` file only.
- Maximum file size: 5 MB.
- Drag/drop and standard file picker.
- Show filename and size after selection.
- Primary CTA: `Review campaign`.
- Copy: `Your workbook stays in review mode. Nexus will not publish or change a live campaign.`

### 2. Review
Show what Nexus extracted in a simple campaign summary:
- Client
- Campaign name
- Objective
- Market
- Currency
- Flight
- Platforms
- Source row count
- Audience count
- Creative count
- Activation count

Below the summary, show platform groups as compact cards with row counts.
Show blockers/ambiguities separately from confirmed source-backed facts.
Never present ambiguous values as resolved facts.

### 3. Confirm
For the historical benchmark shape, support exactly these six operator decisions:
- Client
- Currency
- Flight start
- Flight end
- Campaign name choice
- Duplicate source-row decision: choose which row to retain

Rules:
- campaign name must be selected from source-derived candidates, not free-typed
- currency is a 3-letter uppercase code
- dates must be valid ISO dates with start <= end
- duplicate retention must choose one of the candidate source rows
- show the source evidence next to every confirmation where available
- CTA disabled until all required confirmations are valid
- CTA: `Confirm and compile`

### 4. Compile
Display a deterministic progress sequence, not fake AI prose:
- `Validating confirmations`
- `Separating platform groups`
- `Building canonical campaign`
- `Compiling activations`
- `Running deterministic QA`

Do not show a chatbot, agent thoughts, chain-of-thought, or invented model explanations.

### 5. QA
Two possible states only:

PASS state:
- large status: `READY FOR APPROVAL`
- show build row count
- show QA checks passed
- show platform
- show source evidence preserved
- show `Nothing has been published.`

BLOCKED state:
- large status: `BLOCKED`
- show each blocking issue with field/entity/source row where available
- no download CTA
- clear copy: `Fix or confirm the blocking issue before Nexus can generate a trafficking package.`

### 6. Download
Only show after QA PASS.
Primary CTA: `Download trafficking package`
Filename: `nexus_trafficking.csv`

The frozen exact column order is:
1. Campaign_Key
2. Plan_Row_ID
3. Platform
4. Campaign_Name
5. Placement_Name
6. Ad_Format
7. Flight_Dates
8. Audience_Targeting
9. Creative_ID
10. Landing_Page_URL
11. Final_Tracking_URL
12. Activation_ID
13. Audience_Row_ID
14. Creative_Row_ID

Do not reorder, rename, hide, or add columns.

## Frontend architecture
Create a small React + TypeScript app in `nexus-tester-shell/`.
Keep the UI layer independent from the backend through one adapter interface called `NexusClient`.

Required methods:
- `reviewWorkbook(file)`
- `submitConfirmations(runId, confirmations)`
- `compileCampaign(runId)`
- `getQaResult(runId)`
- `downloadPackage(runId)`

For this shell build, implement a `MockNexusClient` only for visual/state testing. Clearly label it development-only in code. Do not create or alter Nexus backend APIs in this task.

Mock states must cover:
1. upload idle
2. reviewing
3. needs confirmation
4. compiling
5. blocked
6. ready for approval
7. download available

Use the benchmark shape for the success fixture:
- 13 source rows
- platform groups: Adobe DSP, Facebook, LinkedIn
- Adobe DSP selected
- 8 Adobe activations
- 6 confirmations
- QA PASS
- 8 output rows

Use one blocked fixture where `Final_Tracking_URL` is missing and package download is unavailable.

## Visual direction
- Mobile-first, especially 390×844.
- Desktop responsive, max readable content width around 1100px.
- Serious campaign-operations product, not generic AI SaaS.
- High contrast, restrained typography, dense but readable operational data.
- Avoid gradients, glowing AI effects, robot icons, sparkles, chat bubbles, and marketing illustrations.
- Brand: `NEXUS`
- Supporting line: `Campaign Operations, Compiled.`
- Use status language consistently: `NEEDS CONFIRMATION`, `COMPILING`, `BLOCKED`, `READY FOR APPROVAL`.

## Acceptance checks
The shell is acceptable only if all are true:
- user can select one XLSX and move through all six states using the mock client
- all six confirmations are visible and validated
- ambiguous values never appear as confirmed automatically
- blocked fixture cannot download
- pass fixture shows READY FOR APPROVAL
- pass fixture exposes the download action
- visible export preview uses exactly the frozen 14 columns and exact order
- no file outside `nexus-tester-shell/` is modified
- no Gemini runtime API call exists
- no Nexus backend code is changed
- 390×844 requires no horizontal scroll

## Final instruction
Implement only this tester shell. Do not redesign Nexus architecture and do not add adjacent features. After implementation, report only:
1. files created/changed inside `nexus-tester-shell/`
2. whether each acceptance check passes
3. any blocker preventing the shell from running
