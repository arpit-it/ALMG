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
