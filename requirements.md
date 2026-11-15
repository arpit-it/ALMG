# ALMG requirements

ALMG is a Flutter desktop app with a local Python backend. Its goal is to turn a plain-language request into a dataset, a trained model, and an evaluation report. The current release target is Apple silicon macOS. The initial GitHub commit includes local Qwen chat and text-classifier training. [GitHub repository](https://github.com/arpit-it/ALMG)

## P0 · Validate the first macOS release

- [ ] Run the release workflow from a version tag and verify that GitHub Releases contains the app ZIP and SHA-256 checksum. Download the ZIP, verify the checksum, and confirm that it contains the app and backend source. Keep model weights, chat databases, training output, and credentials out of Git and release assets.
- [ ] Test a fresh installation on an Apple silicon Mac. Follow the documented Python setup, register the backend, download and verify the checkpoint, send a chat message, and confirm that history survives a relaunch.
- [ ] Document signing and notarization requirements for public distribution. Verify the downloaded app opens on a clean Mac.
- [ ] Add automated checks for pull requests. Run Flutter analysis, widget tests, and offline Python tests. Cover the macOS stop and restart flow, interrupted replies, attachment persistence, and checkpoint download recovery.

## P1 · Make text-classifier training reliable

- [ ] Let users review and edit labels, dataset requirements, success metrics, and any web queries before training. Require approval before sending queries or fetching source pages, and store approved queries and source URLs with the dataset.
- [ ] Support importing labeled datasets and previewing examples and class balance. Flag missing labels, ambiguous examples, duplicates, and near duplicates. Keep related examples together when splitting data.
- [ ] Persist jobs and progress across backend restarts. Show logs, metrics, and artifact locations. Add cancellation and resume where the training recipe can restore a checkpoint.
- [ ] Keep validation separate from final testing. Use validation errors to guide a bounded retry, retain the best candidate, and report the final score on a held-out dataset. Test the full path from an approved dataset to a reloadable model and report.

## P2 · Improve chat and project work

- [ ] Save unsent drafts across app restarts. Test that a backend outage preserves the draft and exposes any partial response without duplicating a saved turn.
- [ ] Expand support for PDF and image attachments. Show which text or image content the model can use, and cite filenames and page numbers when available.
- [ ] Add full-text conversation search, Markdown export, and controls for whether the model can draw on other conversations.
- [ ] Test project instructions, reference files, and chat branches together. Verify that a branch preserves its source conversation and stays in the same project.

## P3 · Expand training and platform support

- [ ] Define a training recipe interface for dataset format, hardware needs, parameters, metrics, and export format. Validate a small LoRA run on Apple silicon before adding more recipes.
- [ ] Check available memory and disk before training. Verify idle detection, power checks, sleep and wake recovery, and safe resume after the machine becomes busy.
- [ ] Validate the Windows build and a CPU training run on Windows. Evaluate GPU support and decide whether planning runs locally on Windows or uses a paired Mac.

See [PROJECT_TASKS.md](PROJECT_TASKS.md) for the existing implementation baseline and more detailed backlog.

## Model Training workspace design

**Implementation gate.** Finish and verify the P2 chat and project work before
replacing the training form. Keep Chat as the launch screen. The existing
Training action opens the workspace, and Back returns to the active chat.
The first implementation uses the existing text-classifier recipe.

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

Qwen uses the locally configured model to interpret the goal, ask clarifying
questions, and draft a plan. Conversational drafting is read-only. A chat
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
| Export | Model, dataset, and report files, their formats, and destination |

Each proposal offers **Approve**, **Request changes**, and **Decline**. Editing
the scope creates a new revision that requires approval. Save decisions with
the task, including the scope and timestamp. Enforce the approval in the
backend before starting work. Reopening a task restores the current approval
state, and repeated clicks on Approve must not start duplicate work.

### Model creation panel

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

### Inference preview and model release

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
It creates 48 × 48 RGB images of one colored circle, square, or triangle, with
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
