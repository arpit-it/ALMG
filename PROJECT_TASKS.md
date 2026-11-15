# ALMG project backlog

ALMG runs a local assistant that helps turn a plain-language goal into a dataset, a trained model, and an evaluation report. The Flutter desktop app uses a local Python backend. The proposed build order is to make the existing classifier workflow reliable on macOS, add language-model fine-tuning, then validate Windows and expand the training recipes.

## Current baseline

- [x] Run Qwen3.8-27B inference locally through MLX on Apple Silicon.
- [x] Manage model download, pause, resume, checksum verification, and repair in Settings.
- [x] Save chats in SQLite, reopen conversations, recall relevant history, and render Markdown replies.
- [x] Use Qwen to propose text-classification labels and search queries. Require user approval before sending queries to Brave Search.
- [x] Generate synthetic examples or label search excerpts. Compare classifier candidates, evaluate the selected model on a separate test split, and export the dataset, model, and report.
- [x] Retry synthetic dataset generation once using validation errors. Gate the start of idle jobs on inactivity and AC power.
- [x] Verify local Qwen chat in the macOS app and verify the classifier pipeline with fixture data.

## Dataset planning and collection

- [ ] Let users edit the proposed task type, labels, data requirements, sources, and success criteria before creating a dataset.
- [ ] Import existing datasets, preview examples and class balance, edit labels, and export a versioned dataset.
- [ ] Verify the live Brave Search workflow from consent through export. Keep the approved queries and source URLs with each dataset version.
- [ ] Add full-page extraction for approved sources. Show the domains and collection limits before fetching, record provenance, and respect source usage and crawl restrictions.
- [ ] Deduplicate near matches and group related examples before splitting to reduce leakage. Flag ambiguous labels, missing classes, and poor source coverage.
- [ ] Accept a separate human-labeled evaluation dataset so users can measure performance on representative examples.

## Training and evaluation

- [ ] Define a training recipe interface covering dataset schema, hardware requirements, parameters, metrics, and export format.
- [ ] Add a small language-model LoRA recipe on Apple Silicon. Support compatible quantized checkpoints for QLoRA and validate with a short run on the M4 Max.
- [ ] Add recipes for tabular classification and regression, then assess demand for image, audio, and forecasting workflows.
- [ ] Check available RAM or VRAM, disk, runtime, and model compatibility before starting. Measure peak use on a short trial and show the estimated job cost in time and storage.
- [ ] Show training logs, metrics, and checkpoints in the app. Support cancellation and resume where the recipe can save and restore state.
- [ ] Extend the improvement loop to other supported recipes. Use validation errors to propose data or parameter changes, bound retries, preserve the best candidate, and reserve the test split for final evaluation.
- [ ] Add a model playground for example predictions and export a report with the dataset version, recipe settings, base checkpoint, metrics, and artifacts.

## Idle scheduling and Windows

- [ ] Store jobs and status on disk so they survive an app or backend restart.
- [ ] Check for competing workloads as well as inactivity and power. Checkpoint at safe boundaries when the user returns and resume once the machine is eligible again.
- [ ] Verify idle detection, sleep and wake behavior, and recovery after power loss on supported platforms.
- [ ] Detect and validate the Windows PC’s GPU, VRAM, and drivers. Test a CPU recipe and enable GPU training for verified runtime combinations.
- [ ] Decide where Windows gets planning inference. Verify a Windows-compatible local runtime or pair the Windows worker with the Mac planner.
- [ ] Add optional Mac-to-Windows job dispatch with device pairing, hardware reporting, and reliable transfer of datasets, checkpoints, and results.

## Chat, packaging, and release checks

- [x] Stream partial replies, stop generation, and indicate when generation reaches its output limit.
- [ ] Test recovery after backend disconnects and add edit and regenerate actions.
- [ ] Validate command examples against the applicable recipe or tool help before presenting them as runnable. Test known errors such as unsupported MLX flags and incorrect dataset paths.
- [x] Add search by conversation title, rename, and copy reply.
- [ ] Add full-text chat search, export, and deletion. Give users a setting for whether other conversations can inform new replies.
- [ ] Add file attachments and optional web search to chat, with source links for retrieved information.
- [ ] Package the desktop app and Python runtime for reproducible installation. Verify a fresh install, model setup, updates, and preservation of chat and training data.
- [ ] Add end-to-end checks for download recovery, chat persistence, web approval, idle interruption, and training export. Build and test the Windows release on Windows hardware.
