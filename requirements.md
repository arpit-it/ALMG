# ALMG requirements

ALMG provides one dynamic workbench for designing, generating, testing, and
exporting custom models. The user describes the desired outcome in chat.
Local Qwen gathers missing details and selects registered training,
evaluation, simulation, and export tools at runtime as the task requires.
ALMG executes the approved plan and presents progress, results, and evidence
in the same work pane across model types.

ALMG is a Flutter desktop app with a local Python backend. Its goal is to turn a plain-language request into a dataset, a trained model, and an evaluation report. The current release target is Apple silicon macOS. The initial GitHub commit includes local Qwen chat and text-classifier training. [GitHub repository](https://github.com/arpit-it/ALMG)

## P0 · Validate the first macOS release

- [ ] Run the release workflow from a version tag and verify that GitHub Releases contains the app ZIP and SHA-256 checksum. Download the ZIP, verify the checksum, and confirm that it contains the app and backend source. Keep model weights, chat databases, training output, and credentials out of Git and release assets.
  Local verification: a ZIP assembled with the workflow’s packaging commands
  passed SHA-256 verification and contained the app and backend source. The
  ARM64-only build was confirmed with `lipo`, and the app opened to the
  Dashboard after extraction from the verified ZIP. The GitHub tag-triggered
  workflow still needs verification. The published main-branch prerelease
  `v1.0.0-main.1` contained the ZIP and checksum. The downloaded ZIP passed
  SHA-256 verification, contained the backend source and ARM64 app, and opened
  to Chat on the existing Mac installation. The published main-branch
  prerelease `v1.0.0-main.3` also passed the downloaded SHA-256 check,
  contained the ARM64 app and backend source, and opened to the Dashboard
  on that Mac. GitHub Actions run [43714250108](https://github.com/arpit-it/ALMG/actions/runs/43714250108)
  completed successfully after a push to `main` and published this prerelease.
  A local ARM64 package built with an explicit backend file list passed its
  SHA-256 check, contained exactly the eight expected backend files, and
  opened to the Dashboard after extraction.
- [x] Test a fresh installation on an Apple silicon Mac. Follow the documented Python setup, register the backend, download and verify the checkpoint, send a chat message, and confirm that history survives a relaunch.
  The isolated Mac build reached Chat with setup required and showed a live
  transfer rate of 24.8 MB/s beside checkpoint progress in Settings. In a fresh
  Python environment with a separate macOS service, port, model directory,
  and chat database, ALMG downloaded and verified the 16.07 GB checkpoint.
  Qwen answered `42` in Chat, and the prompt and reply were both visible
  after quitting, relaunching, and reopening the conversation.
- [ ] Document signing and notarization requirements for public distribution. Verify the downloaded app opens on a clean Mac.
- [x] Add automated checks for pull requests. Run Flutter analysis, widget tests, and offline Python tests. Cover the macOS stop and restart flow, interrupted replies, attachment persistence, and checkpoint download recovery.
  Verified in isolated macOS Settings: Stop runtime showed Runtime stopped,
  and Restart backend restored Connected and Verified and ready to use.
  Offline tests now cover acknowledgment before shutdown and rejection of
  stop requests for manually started backends. A socket fixture verifies that
  the replacement backend accepts a connection queued on its inherited
  listener. Flutter tests cover Settings retries until connection and stopping
  when the retry window is exhausted. The rebuilt isolated Mac app again
  showed Runtime stopped, then Connected with the verified model. An offline
  checkpoint test covers resuming a partial file
  after restart and verifying its checksum. In the isolated Mac app, Settings
  resumed the local fixture and reported Verified and ready to use. The Mac
  chat showed the interruption and restored the prompt after a fixture emitted
  a delta and failed. An offline stream test confirms no failed turn is saved.
  In a fail-once fixture in Mac Chat, resending the restored draft produced
  one saved prompt and one reply. The offline stream test now also checks
  that retrying with the same message token saves exactly one turn. Offline
  tests cover attachment persistence, and the isolated Mac app showed the
  attached filename and Qwen’s correct fixture code after relaunch. The pull
  request workflow runs Flutter analysis, Flutter tests, and the offline
  Python suite. All three checks passed locally.

## P1 · Make text-classifier training reliable

- [ ] Let users review and edit labels, dataset requirements, success metrics, and any web queries before training. Require approval before sending queries or fetching source pages, and store approved queries and source URLs with the dataset.
  Verified in the Mac app: saving an edited query updates the visible proposal
  and leaves search awaiting separate approval. In the rebuilt Mac app, replacing
  a proposed classifier label updated the plan while dataset approval remained
  pending. In the isolated Mac build, changing the proposed macro F1 target
  to 0.92 left dataset approval pending. The isolated Mac app also saved a
  change from 40 to 25 local examples per label without approving generation.
  An offline fixture produced 25 examples for each of two labels. The isolated
  Mac app released a web classifier fixture after inference preview. Its export
  contained the approved queries and source URLs, with each row linked to its
  query. The isolated Mac app hid web approval for an empty query list,
  and the backend rejected an empty approval. Offline tests confirm that
  empty and stale approvals leave the job pending and start no worker.
  In the isolated Mac app, approving the displayed fixture query populated
  the dataset preview and left training awaiting separate approval. This test
  used a local search response. The rebuilt Mac app showed the exact query,
  Brave Search as the destination, and how ALMG uses excerpts and records
  source URLs before approval. In the isolated Mac app, approving a search
  without a Brave API key showed the configuration error and kept dataset
  approval pending, with local generation and CSV import still available.
  An offline search failure returned the Mac app to dataset approval with
  the query, error, and local dataset choices visible. An empty offline search
  response also returned to dataset approval and offered query edits and local
  dataset choices. After a backend restart, the isolated Mac app reopened
  an interrupted collection fixture with the original query and required
  fresh approval before retrying. A local collection fixture with billing
  examples only returned to dataset approval and identified shipping as the
  missing class. With an approved offline search fixture, the rebuilt Mac
  app showed the approved query and each example’s source URL before separate
  training approval. In a local search response, two excerpts with the same
  retained text yielded one billing example, while a distinct shipping
  excerpt and both retained source URLs appeared in the Mac preview.
  A mixed offline response skipped malformed entries and showed both valid
  examples and URLs in the Mac app before separate training approval.
  A Mac web fixture preserved both original URLs in the preview while the
  saved dataset grouped hostname variants with different ports together.
  Editing the query after an empty result cleared the previous error in the
  isolated Mac app and required fresh approval. In the rebuilt Mac app,
  typing immediately after opening the query editor updated its first field
  without a click and saving kept approval pending. Clearing the last query
  in the rebuilt Mac app removed web approval and left local generation and
  CSV import available. The rebuilt Mac app also accepted a new query on
  that empty proposal and showed it with web approval still pending.
  Saving the same query twice in the isolated Mac app showed a validation
  message and kept the original proposal pending approval.
  Approving a saved Mac fixture with three entries and two distinct queries
  recorded two search steps and previewed one result from each query.
  Saving the label editor in the isolated Mac app cleared the fixture's
  previous dataset error and left dataset approval pending.
  Live collection remains to be verified.
- [ ] Support importing labeled datasets and previewing examples and class balance. Flag missing labels, ambiguous examples, duplicates, and near duplicates. Keep related examples together when splitting data.
  The isolated Mac app showed one billing example and zero shipping examples
  in the class balance preview. The rebuilt app warned about the missing
  shipping class and left training approval pending. The backend also
  rejected a direct start request. The rebuilt Mac app imported a labeled CSV
  through the file picker and showed both class counts and example texts,
  including a quoted comma, while training approval remained pending.
  The rebuilt app flagged two duplicate rows and one text with conflicting
  labels in a local fixture. The isolated Mac app showed one near-duplicate
  group for two invoice examples differing only in punctuation. An offline
  fixture verified that punctuation variants and related source rows share
  a split group. The isolated Mac app trained a 48-row fixture with 24 such
  groups and reached inference preview with held-out macro F1 of 1.000.
  A regression test checks the recorded train, validation, and test assignments
  for each pair. Ambiguity beyond conflicting labels and near duplicates
  beyond normalized text variants remain open. In the rebuilt isolated app,
  importing a three-row CSV with ASCII and full-width invoice text showed
  one near-duplicate group and left training awaiting approval. The preview
  now labels the count as Unicode and punctuation variants, verified after
  rebuilding and reopening the saved dataset. A local fixture also verified
  that the Unicode variants share a split group and an unrelated row stays separate.
  In the isolated Mac app, importing the variants with different labels
  showed one conflicting-label group and left training awaiting approval.
  A four-row CSV submitted to the isolated backend combined exact repeats
  and punctuation variants with conflicting labels. The running Mac app
  showed two duplicate rows and one conflicting group, with training still
  awaiting approval.
  Reopening this fixture in the rebuilt Mac app showed the instruction to
  review conflicting labels before approving training. A fresh import in the
  rebuilt Mac app marked both conflicting preview rows and left the unrelated
  example unmarked, with training approval still pending. A seven-row CSV
  imported through the isolated Mac app showed its last two rows first in
  the five-row preview because their labels conflicted. A second seven-row
  fixture showed its two same-label Unicode variants first and reported one
  near-duplicate group while training approval remained pending. A separate
  Mac import grouped “Pay invoice” and “Pay invoice!” together and kept
  training approval pending. The isolated Mac app also flagged “Invoice” and
  “Ｉｎｖｏｉｃｅ!” as one group. Single tokens shorter than five characters
  still use exact matching. In the rebuilt
  Mac app, a quoted multiline CSV record showed its ending line as 3 and the
  following record showed line 4 while training awaited approval. The isolated
  Mac app also imported the same fixture with carriage-return line endings
  and showed both records at the same line numbers. An unterminated quoted
  record ending on line 4 produced “Invalid CSV near line 4” in the Mac app
  and left dataset approval pending.
  Importing a CSV with a blank label showed the line number and missing-label
  error in the isolated Mac app and left dataset approval pending. After rebuilding,
  the same import displayed the validation message without the exception prefix.
  Importing an invalid CSV through the native Open panel in the isolated Mac
  app identified the unrecognized label 'biling' on line 2, left dataset
  approval pending, and showed zero examples.
  The rebuilt Mac app rejected a non-UTF-8 CSV selected in the native Open
  panel and asked the user to save it as UTF-8. Dataset approval stayed
  pending with zero examples.
  Two CSVs selected through the isolated Mac app reported missing text
  and text exceeding 3000 characters on line 2, respectively. Both left
  dataset approval pending with zero examples.
  The Mac app imported a CSV with an optional `group` column and showed all
  three examples awaiting training approval. A local split fixture verified
  that differently worded rows sharing a group stay together. The isolated
  Mac app trained a 32-row CSV with a duplicate shared by two source groups
  and reached inference preview with held-out macro F1 of 1.000. The saved
  split assigned both groups to the test set and excluded the duplicate.
  A Mac CSV import grouped a Devanagari punctuation variant while preserving
  a distinct vowel mark and showing no false label conflict.
  The isolated Mac preview showed one duplicate and one conflict for two
  Unicode encodings of café. The unaccented cafe row had neither warning.
  A local split check kept both accented encodings together.
  The isolated Mac app accepted spaces around the text, label, and group
  headers and previewed both rows while training awaited approval.
  A second Mac import read the columns in group, label, text order and
  showed one correctly labeled example per class before training approval.
  A local CSV fixture with whitespace-only and separator-only rows yielded
  two examples. The isolated Mac app displayed the original ending lines
  3 and 5, with training approval still pending.
  The rebuilt Mac app displayed source group A on both related CSV rows and
  group B on the unrelated row before training approval.
  In the rebuilt Mac app, both repeated rows showed Duplicate text and both
  punctuation variants showed Near-duplicate text. Training awaited approval.
  The isolated Mac app reopened a seven-row offline search fixture and
  showed the last two rows first because their labels conflicted. Training
  still awaited approval.
- [ ] Persist jobs and progress across backend restarts. Show logs, metrics, and artifact locations. Add cancellation and resume where the training recipe can restore a checkpoint.
  After a backend restart, the isolated Mac app reopened a saved classifier
  candidate with its activity, held-out score, and folder containing the model
  and dataset. In the rebuilt Mac app, cancelling while waiting for idle
  time stopped a fixture before training. The cancelled state survived a
  backend restart. In the rebuilt Mac app, cancelling a running fixture
  stopped it at a progress boundary and produced no model candidate.
  The isolated Mac app also reopened an interrupted classifier fixture after
  a backend restart. Approving training again reused the saved dataset and
  reached inference preview. An offline regression test confirms recovery
  reloads the saved rows and waits for approval. Fitting restarts from the
  beginning. The rebuilt Mac app retained the saved idle preference and
  evaluated the recovered run against its original 0.92 target. Resuming from
  a training checkpoint remains open.
- [x] Keep validation separate from final testing. Use validation errors to guide a bounded retry, retain the best candidate, and report the final score on a held-out dataset. Test the full path from an approved dataset to a reloadable model and report.
  The rebuilt Mac app ran one opt-in retry from validation errors using a local
  Qwen fixture and reported a separate held-out score. The saved dataset
  included the novel retry example and rejected the punctuation variant. A
  second Mac run reached preview with held-out macro F1 of 0.245 and kept
  the novel example while rejecting a variant of a removed duplicate.
  After restarting the isolated backend, the Mac app ran the saved retry
  candidate on an unseen invoice prompt and predicted billing. Release stayed
  disabled because the candidate missed its evaluation target. With a passing
  local retry fixture, the Mac app approved training, reported validation
  macro F1 of 0.748 and held-out macro F1 of 0.667 against a target of 0.590,
  and released the model, dataset, and evaluation report after preview approval.
  Reloading the exported model reproduced the preview label “shipping” for
  “Silver ticket status,” and the report recorded the second training round.

## P2 · Improve chat and project work

- [ ] Save unsent drafts across app restarts. Test that a backend outage preserves the draft and exposes any partial response without duplicating a saved turn.
- [ ] Expand support for PDF and image attachments. Show which text or image content the model can use, and cite filenames and page numbers when available.
- [ ] Add full-text conversation search, Markdown export, and controls for whether the model can draw on other conversations.
- [ ] Test project instructions, reference files, and chat branches together. Verify that a branch preserves its source conversation and stays in the same project.

## P3 · Extend the dynamic workbench and platform support

- [ ] Define a training recipe interface for dataset format, hardware needs, parameters, metrics, and export format. Validate a small LoRA run on Apple silicon before adding more recipes.
- [ ] Check available memory and disk before training. Verify idle detection, power checks, sleep and wake recovery, and safe resume after the machine becomes busy.
- [ ] Validate the Windows build and a CPU training run on Windows. Evaluate GPU support and decide whether planning runs locally on Windows or uses a paired Mac.

See [PROJECT_TASKS.md](PROJECT_TASKS.md) for the existing implementation baseline and more detailed backlog.

## Model Training workspace design

**Implementation gate.** Finish and verify the P2 chat and project work before
replacing the training form. Launch into the Dashboard. The
Dashboard opens the Training workspace, Model Library, and Chat. Qwen chooses
from the text classifier and experimental text-to-image recipes.

### Desktop layout

```text
┌────────────────────── Model Training ────────────────────────────┐
│ ‹ Chat   Training sessions   ▾   + New task                      │
├──────────────────────────────────┬──────────────────────────────┤
│ Training conversation            │ Model creation               │
│                                  │ Support ticket classifier    │
│ You                              │ Awaiting approval            │
│ Classify support tickets into    │                              │
│ billing, account, and shipping.  │ ● Plan ready                 │
│                                  │ ○ Dataset                    │
│ Qwen                             │ ○ Training                   │
│ Which label should apply when    │ ○ Evaluation                 │
│ a ticket mentions two topics?    │ ○ Artifacts                  │
│                                  │                              │
│ Review dataset plan              │ Current stage · Plan         │
│ [Review proposal]                │ Labels, source, metric        │
│                                  │ [Review proposal]            │
│ [Describe your goal or reply ⬆]  │                              │
└──────────────────────────────────┴──────────────────────────────┘
```

- Give the timeline roughly 60% of the desktop workspace. Keep the composer
  anchored below the timeline and let each pane scroll independently.
- Keep the task name, current status, and next action visible at the top
  of Model creation. Expand the current stage by default and let the user
  open past stages. At narrow widths, switch between **Conversation** and
  **Model creation** using tabs, with an indicator for a pending approval.
- Reuse the chat composer, Markdown rendering, and streaming behavior.
  Keep a distinct session for each training task. Users can return to a
  previous task by name and see its transcript, approvals, and results.
- Make approvals explicit labeled buttons. Permit keyboard navigation and
  announce status changes to assistive technology. Use text with any status color.

### Conversation and approval flow

ALMG's locally configured Qwen model interprets the goal, asks clarifying
questions, and drafts a plan. Conversational drafting is read-only. A chat
message such as “go ahead” keeps the conversation moving. The corresponding
work begins only when the user presses the approval button for the pending
proposal. Show that same proposal in the conversation and the model panel.

| Task | What the approval shows |
| --- | --- |
| Save plan | Model goal, task type, labels, sample inputs and outputs, dataset requirements, and target metric |
| Prepare dataset | Generate synthetic examples or import a named file. Show the format, target count, and planned checks |
| Search the web | Exact queries, provider, domains or scope, and result limit. Request a separate approval before fetching full pages, with URLs and limits shown |
| Finalize dataset | Preview, class balance, duplicates, missing labels, split strategy, and the dataset version that will be used |
| Start training | Recipe, dataset version, parameters, estimated time and resources, and whether the task waits for idle time and AC power |
| Evaluate or improve | Separate validation and held-out test data. Show the proposed metric, retry limit, and any data or parameter changes before a new run |
| Run simulation | Candidate, simulator, scenarios, acceptance criteria, and retry limit |
| Export | Model, dataset, and report files, their formats, and destination |

Each proposal offers **Approve**, **Request changes**, and **Decline**. Editing
the scope creates a new revision that requires approval. Save decisions with
the task, including the scope and timestamp. Enforce the approval in the
backend before starting work. Reopening a task restores the current approval
state, and repeated clicks on Approve must not start duplicate work.

### Model creation panel

- [ ] Use chat as the primary training interface. In the adjacent work pane,
  show what ALMG is doing now, including the current action, its status,
  and progress when measurable. Update the pane as planning, dataset
  preparation, training, and evaluation advance. When work is waiting for an
  answer, approval, or resource, show what it needs.
- **Plan** shows the goal, labels, success criteria, approved scope, and the
  latest plan revision. Unanswered questions link to the conversation.
- **Dataset** shows the source mode, preview rows, example counts by label,
  duplicates, source provenance, and dataset version.
- **Training** shows the selected recipe, hardware checks, current step,
  elapsed time, and recent logs. Offer cancellation while running and show
  pause or resume only when the recipe supports checkpoints. For an idle job,
  explain the condition it is waiting for.
- **Evaluation** shows the target and measured scores, per-label results, and
  representative mistakes. Mark validation and held-out test scores separately.
  Any retry proposal links back to the results that prompted it.
- **Artifacts** lists the exported model, dataset, and report with their paths
  and file sizes. Include a way to open the output folder.

Use the same persisted job state in both panes. Show specific waiting,
running, completed, cancelled, and failed states. If the backend disconnects,
retain the conversation and last known job data and refresh when it reconnects.

### Implementation and acceptance

- [ ] Add the two-pane Flutter workspace and narrow-window tabs. Verify that
  switching panes or returning to Chat preserves the training task.
- [ ] Add persisted training sessions, proposal revisions, and decisions to
  the Python backend. Test declined, edited, stale, and duplicate approvals.
- [ ] Wire up the text-classifier flow from dataset preview through export.
  Verify that web access waits for explicit approval of the exact scope, and
  that an approved training run uses the selected dataset version.
- [ ] Verify onboarding, backend reconnect, cancellation, failure recovery,
  and successful export from the workspace. Test keyboard navigation at
  desktop and narrow widths.

### Using generated models

- [ ] Build the Model Library and **Run Model** screen first. Discover
  previously generated candidates and releases from saved jobs and artifacts.
  Show model name, project, recipe, creation date, and candidate or release
  status. Track the files needed for inference, including diffusion weights
  stored separately from exported metadata.
- [ ] Provide a persistent **Model Library** across projects. Add generated
  models to it when they are ready for inference and group their versions
  under one model entry. Show each version's evaluation and release status.
- [ ] Let users name and tag models, search by name or use case, and filter
  by project, model type, and deployment target. Keep each version linked
  to its training run, evaluation results, and hardware validation status.
- [ ] Let users open a specific version from the library after restarting
  ALMG, run it on fresh inputs, and access its export and usage instructions.
  Show any missing runtime or dependency and what is needed to run it again.

- [ ] Make practical use of the generated model part of completing a project.
  Ask in chat where the user wants to run it and what real inputs and outputs
  they expect. Use those answers to plan inference, testing, and delivery.
- [ ] Let users reopen a saved model and run new inputs in ALMG after
  training. Use input controls and results appropriate to the model. For
  workflows that involve multiple inputs, offer batch inference where supported.
- [ ] For external use, deliver the model in a format supported by the target
  runtime with its dependencies, input and output formats, setup instructions,
  and a runnable inference example. Report which target checks passed and
  which are pending.

- [ ] When the user specifies a deployment target, include hardware
  validation in the testing plan. Run the exported candidate on the target
  or a connected test device with the matching configuration. Check that it
  loads, produces expected outputs on representative inputs, and meets
  agreed latency and memory limits. Record the device, runtime, artifact
  version, and measured results.
- [ ] Show hardware validation status separately from model evaluation and
  simulation. If compatible hardware is unavailable, keep the evaluation
  results visible and mark hardware validation as pending. For physical
  systems, include bench or hardware-in-the-loop tests where the use case
  calls for them.
- [ ] When a trained candidate is ready for inference, open its **Model
  preview** in the work pane. Let the user run the candidate directly in ALMG
  before export. Match the controls and results to the recipe, such as text
  and predicted labels for classification, or a prompt and generated image
  for image generation. Keep the training conversation accessible.
- [x] Add a **Model preview** chat for each trained candidate. The user enters
  representative inputs, and the generated model produces the replies using
  the selected recipe. A classifier shows its predicted label.
- [x] Show the candidate version, evaluation target, measured score, and
  expected inputs alongside the preview. Let users run multiple examples
  and review the results before approving release.
- [x] Enforce the release gate in the backend. A candidate must meet its
  evaluation target, return at least one successful preview result, and
  receive explicit user approval before ALMG exports it as a released model.
  Training a replacement candidate resets its preview and approval.
- [x] Test the gate with an untested candidate, a candidate below its
  evaluation target, and a successful candidate. Verify inference uses the
  trained candidate and that the released model reproduces its predictions.

### Text-to-image recipe

ALMG's first image generator learns from local synthetic prompt and image pairs.
It creates 48 × 48 RGB images of up to three colored circles, squares, or triangles, with
optional left, center, or right placement. ALMG fits the shape and color weights
from scratch. Some shape and color combinations are held out for evaluation.
The preview and approval gate applies before export. The exported JSON weights
are usable by a pure Dart inference class. Android and iOS application
integration and on-device validation are pending.

### Training projects and artifacts

- Training conversations require an existing Chat project. Select a project in
  Model Training, then start a conversation or reopen one from its history.
- ALMG saves training records, dataset rows, completed candidates, and recent
  preview results locally. A saved dataset or candidate can be reopened after
  a backend restart. An interrupted active operation requires a new run.
- After approval, ALMG exports the image model as versioned JSON weights and
  the text classifier as Joblib, alongside JSONL dataset rows and a JSON
  evaluation report. The model path can be copied from Model creation.

### Web datasets for text-to-image training

- [ ] In the Training screen, propose image search queries from the user's goal. Show the provider, source scope, and result limit for approval before searching.
- [ ] Present candidate image URLs for a separate download approval. Show the source, available caption and license information, and collection limits. Collect supported image files relevant to the training goal.
- [ ] Save a local dataset with each image's caption, source URL, license, and checksum. Validate file types and dimensions, deduplicate images, and keep related images together when splitting training and evaluation data.
- [ ] Show collection progress, rejected files, subject coverage, and sample image-caption pairs. Let the user review the dataset before approving training.
- [ ] Train an image generator from scratch on the approved dataset. Evaluate it on unseen captions and subjects in Preview, and verify the exported model on Android and iOS before release.

## Future model generation recipes

Each row describes a planned recipe family and example goals for the Training conversation. Multiple use cases can use the same trainer.

| Recipe family | Example use cases |
| --- | --- |
| Text classification | Route tickets, detect spam, identify intent, tag topics, analyze sentiment, detect language, categorize documents, moderate content |
| Text extraction and matching | Extract entities and dates, redact personal information, extract contract clauses, produce structured JSON, match duplicate records, link mentions to known entities, extract relationships |
| Text and code generation | Draft replies and product descriptions, summarize reports, rewrite in a brand voice, translate, correct grammar, answer questions about supplied passages, generate code or tests, learn tool calls from examples |
| Search and retrieval | Search by meaning, retrieve passages, rerank results, find similar documents, match queries to products, find images by description |
| Document AI | Recognize printed and handwritten text, extract invoice and receipt fields, analyze page layout, extract tables, classify scanned forms, answer questions about document images |
| Image recognition | Classify images, assign multiple tags, detect and count objects, segment regions, estimate pose, detect manufacturing defects, find similar products |
| Image generation and editing | Generate images from prompts, adapt to a visual style, create product scenes, edit from instructions, replace backgrounds, fill missing regions, restore and upscale photos |
| Video understanding | Recognize actions, track objects, detect events, locate relevant clips, caption video, summarize footage, classify events using audio and video |
| Video generation | Generate short clips from prompts, animate still images, interpolate frames, upscale footage |
| Speech and audio | Transcribe or translate speech, identify speaker turns, detect wake words, classify sounds and music, remove noise, separate sources, synthesize narration, generate sound effects |
| Tabular classification and regression | Predict churn or returns, categorize leads and claims, estimate delivery times, predict order value or repair costs, estimate energy use |
| Time-series forecasting | Forecast sales, demand, inventory, staffing, traffic, energy consumption, or equipment readings, including forecasts across related products or locations |
| Anomaly detection and maintenance | Flag unusual transactions, detect sensor faults or unexpected sales changes, identify visual defects and dataset outliers, predict time to equipment failure from maintenance history |
| Recommendations and ranking | Recommend products, articles, courses, music, or jobs, rank items, suggest related items, personalize feeds |
| Clustering and topic discovery | Segment customers, discover feedback themes, group similar images and documents, identify patterns in unlabeled data |
| Graph learning | Classify nodes or graphs, predict missing links, recommend related entities, identify communities |
| Geospatial and remote sensing | Classify land cover, detect changes in satellite imagery, map roads and buildings, identify crop stress, estimate traffic from road sensors |
| 3D and spatial AI | Estimate depth, classify point clouds, segment 3D scenes, reconstruct objects from images, generate 3D assets |
| Multimodal AI | Caption images, answer questions about charts or screenshots, match images and text, classify products from photos and descriptions |
| Decision-making and control | Learn game strategies, adapt simulated robot movements, optimize simulated warehouse routing, learn scheduling policies, choose recommendation strategies from feedback |
| Model adaptation and compression | Adapt to a domain or language, learn from preference pairs, distill a large model, train with quantization for device deployment |
| Data imputation and synthetic data | Fill missing fields or sensor readings, generate synthetic tabular records, augment labeled training examples, generate test data from a schema |
| Event-time prediction | Estimate time until subscription cancellation, equipment failure, or a service milestone using event histories and incomplete observations |
| Scientific and engineering prediction | Estimate material properties, approximate engineering simulations, classify astronomical imagery, predict environmental measurements |

Include **Answer questions from my documents** in the picker. Route goals about
accessing current documents to a retrieval workflow. Offer embedding or reranker
training when users have query and relevance examples, and assistant fine-tuning
when they have examples of the intended response behavior.

### Qwen3.8 recipe selection

- [ ] Make **Automatic (Qwen)** the default when a user describes a model
  in chat. Use the configured local Qwen3.8 planner to infer the task and
  choose a recipe at runtime from ALMG's registry. The user can start with
  any plain-language goal. Keep the planner checkpoint configurable.
- [ ] Drive routing and follow-up questions from the goal, conversation, and
  recipe metadata. Register new recipes with their capabilities and trainer
  entry points so Qwen can consider them without adding intent keywords or
  use-case-specific routing branches. The backend dispatches the validated
  recipe ID to its registered trainer.
- [ ] Give Qwen the user's goal, expected output, available data profile,
  deployment target, and recipe metadata. Each registry entry defines its ID,
  supported tasks, required dataset fields, compatible checkpoints and
  hardware, evaluation metrics, export formats, and availability.
- [ ] Have Qwen return a structured proposal with the recipe ID, why it fits,
  required inputs, unresolved questions, and any viable alternative. If a
  missing detail would change the choice, ask a focused question. For example,
  distinguish assigning one label to an image from locating multiple objects
  in it.
- [ ] For each use case, have local Qwen ask for the details it still needs
  to select or configure the recipe. Ask in chat and show a few selectable
  options relevant to the request. Explain what each requested detail helps
  decide. Reuse answers already given. Accept custom answers and request a
  file, sample input, or desired output when that is the missing detail.
  Record each answer and have Qwen reassess the recipe and its settings.
  For example, an image request could offer **Label the whole
  image**, **Locate objects**, and **Outline regions**.
- [ ] Validate the proposed ID, dataset schema, hardware, and export
  compatibility in the backend. If the recipe is planned or incompatible,
  show its status and explain what is missing. When no registered recipe
  fits, explain the unmet capability and show any viable alternatives.
  Allow the user to review or
  override the proposed recipe before approving the run.
- [ ] Save the selected recipe version, planner checkpoint, selection rationale,
  dataset version, and final settings with the training session. Apply the
  existing approvals for data collection and training.
- [ ] Verify routing with representative requests. Route support ticket labels
  to text classification, next month's sales to forecasting, and a count of
  visible products to object detection. Verify that ambiguous requests prompt
  for the missing detail and unavailable recipes cannot start a run.

### Qwen-led model development

- [ ] Turn the user's goal into concrete input and output examples. Reuse
  confirmed project decisions and ask focused questions with selectable
  answers when a missing detail would change the plan.
- [ ] Inspect shared files locally. Propose column and label mappings and
  show examples of missing labels, conflicting categories, and gaps in
  coverage. Queue ambiguous or underrepresented examples with suggested
  labels the user can correct in place.
- [ ] Draft acceptance criteria and saved Model Preview tests from the user's
  priorities. Recommend a baseline or quick trial and use measured results
  to propose a full run or revise the plan.
- [ ] Build the candidate through ALMG's registered tools and show progress
  in the work pane. Compare candidates on the same tests, show representative
  failures, distinguish measured findings from hypotheses, and propose
  targeted changes. Save confirmed decisions and compare newly supplied data
  with the project's previous dataset when the user returns.

### Worked example · Drone collision avoidance and free roam

This example illustrates how the general workbench adapts to a user request.

- [ ] Ask in chat for the airframe configuration, flight controller and
  firmware, sensor inventory and placement, available compute, and existing
  control logic. Clarify what free roam means, the intended operating
  environment, the expected model inputs and outputs, and the desired
  behavior when a sensor drops out or the operator takes over.
- [ ] Have Qwen select a compatible recipe and simulator from the registry,
  identify missing data, and propose a training and simulation plan based on
  the user's instructions. Present the scenarios and pass criteria for
  review before running the approved plan.
- [ ] Train and simulate the candidate in ALMG. Show progress and replayable
  results for obstacle encounters, free roam boundaries, sensor dropout,
  and operator takeover. Compare recorded outcomes with the agreed criteria
  and show failed scenarios with proposed changes before another run.
- [ ] When the candidate meets the agreed simulation criteria, present it
  in Model Preview alongside the simulation report. Include the compatible
  flight controller or companion runtime, input and output interface,
  integration instructions, and remaining bench and controlled flight
  validation steps. Record simulation and hardware validation separately
  and apply the existing release approval before export.

## Dashboard and project navigation

Implement the Dashboard after Model Library discovery and inference work
for existing models.

- [ ] Show **Training activity**, **Recent models**, and **Recent chats**
  on launch, with a link to the full Model Library. Refresh active training
  status while the Dashboard is visible.
  Verified on macOS: the grid showed the latest model state, and the separate
  chat list reopened the exact saved transcript in its project. Training
  activity and recent model rows with automatic refresh are pending.
- [ ] Open the exact training session from its row with progress and pending
  actions. Open **Run Model** for the selected model version and restore the
  selected chat with its project context.
- [x] Provide **Add Project** on the Dashboard. Collect a project name and a
  local directory, save both, and offer **Open Model Training** with the new
  project selected.
  Verified on macOS: naming a project and choosing a folder saves both values
  and adds the card to the grid. The post-create **Open Model Training**
  action opened a fresh conversation with the new project selected.
- [ ] Validate that the selected directory is writable before training.
  Store datasets, checkpoints, models, and reports for new runs in an
  ALMG-managed subfolder. Resolve existing runs at their recorded locations
  and allow users to reconnect a moved directory in Project Settings.
- [ ] Provide **New Model Training** and **New Chat** on the Dashboard.
  Open a blank training conversation in the selected project, or show the
  project picker when needed. Open a blank chat with the selected project's
  context when available. Provide a way back to the Dashboard and show new
  activity after it is saved.
- [ ] Verify that each Dashboard row restores the exact item after relaunch.
  Create a project with a chosen directory, train a model, and verify that
  the generated assets are stored there and the session can be reopened.

## Future enhancements

### Release milestones

- [ ] **Usable macOS release (6–10 weeks).** Verify the workbench on a clean
  install from data import through training, evaluation, preview, export,
  and hardware validation on one supported target. After relaunching ALMG,
  find a model trained before the library was added and run a fresh input.
  Use the delivered instructions to run the
  exported model on the supported target.
- [ ] **Broader workbench release (4–6 months).** Verify the same workflow
  across substantially different model types and deployment targets.

Estimates are cumulative planning ranges for one full-time developer.

### First priorities

- [ ] **Dataset health checks.** Before training, show missing labels, invalid
  rows, underrepresented classes, and duplicate examples within or across
  splits. Link each finding to the affected examples so users can correct
  them and rerun the checks.
- [ ] **Baseline comparison.** Evaluate the candidate and a recipe-appropriate
  baseline, such as a simple predictor or the original pretrained model, on
  the same held-out data with the same metrics. Show changes in scores and
  examples where the candidate improved or regressed.
- [ ] **Saved test cases in Model Preview.** Let users save a representative
  input and its expected output or acceptance criteria. Keep the cases with
  the project and let users rerun them against each candidate. Show pass,
  fail, or review-needed results and flag regressions from the previous
  candidate in the work pane.

### Additional enhancements

- [ ] **Review and correct predictions.** Let users edit a prediction in
  Model Preview and choose whether to save the correction as a test case or
  include it in the next training dataset.
- [ ] **Run estimates and quick trials.** Before training, estimate memory,
  disk space, and runtime. Offer a short trial to verify that the dataset and
  training setup work before the user starts a full run.
- [ ] **Experiment history.** Compare candidates by dataset version, recipe,
  settings, evaluation results, model size, and inference speed. Let users
  duplicate a run and edit its settings.
- [ ] **Batch inference in ALMG.** Run a trained model on a compatible CSV,
  image folder, or audio collection. Export predictions with enough input
  identifiers to match each result to its source.
- [ ] **Deployment compatibility checks.** Let users specify the target
  platform and runtime, show compatible export formats, and run a sample
  prediction with the exported artifact when the target runtime is available.
