# ALMG - Automated Language Model Generator

Flutter desktop client and local Python training backend. This first version
takes a natural-language goal and builds a supervised text classifier.

See the [project backlog](PROJECT_TASKS.md) for planned work and verification tasks.

## Run locally

Install Flutter with desktop support and Python 3.12. Qwen chat uses MLX on
an Apple silicon Mac. Start the local backend from the project root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python backend/studio.py
```

On macOS, you can register the backend for on-demand startup for the current login.
With the manually started backend stopped, run:

```sh
.venv/bin/python backend/register-macos-service.py
```

ALMG starts the registered backend over localhost when it connects. **Restart backend**
retries that connection. Run the registration command again after logging out or rebooting.

In another terminal run `flutter run -d macos`. The app opens to Qwen chat.
Open **Settings**, then click **Download local model** to fetch the 4-bit checkpoint from Hugging Face.
The app shows bytes received and the current file. **Pause** keeps partial
files and **Resume download** continues them, including after a backend restart.
**Verify files** checks each file against the Hugging Face revision manifest.
**Repair / resume** downloads only missing or damaged files. Chat is enabled
after verification. Once the model is ready,
enter a message. The first reply includes model loading time. Subsequent
replies reuse the loaded model. ALMG saves conversations in
`backend/runs/chat.sqlite3`. Open a conversation from the sidebar to continue it.
Qwen receives recent turns from that conversation and may receive matching
excerpts from your other local chats when the prompt shares keywords.

If you already have the same MLX checkpoint, set `STUDIO_MODEL_DIR` to its
directory before starting the backend, then click **Check setup**. You can
also download it manually with the Hugging Face CLI:

```sh
hf download mlx-community/Qwen3.8-27B-4bit --local-dir backend/models/qwen3.8-27b
```

Chat and the dataset planner run directly in Python with local model files.
Select **Training** to open the existing classifier workflow on the Mac.

## Train a classifier

1. Describe the text and labels, such as classifying customer support messages
   into billing, shipping, and returns.
2. Review Qwen's labels and exact proposed search queries. Choose synthetic
   examples for a local run, or approve the queries to use Brave Search excerpts.
   For web mode, set `BRAVE_SEARCH_API_KEY` in the backend environment before
   starting it. Use sources and an API plan that permit your intended data use.
3. Review the dataset preview, set the macro F1 target, and approve training
   and evaluation. By default the job waits for AC power and 10 minutes
   without input. Leave the computer awake and keep the backend running.
4. Enter representative examples in **Model preview** and review the labels
   from the trained classifier. A candidate must meet the evaluation target and
   return a preview prediction before you can approve release.
5. Find the released dataset, report, and joblib model under `backend/runs`.
   The report includes validation trials, held-out test results, and per-class
   scores. Only load joblib files you trust.

Qwen drafts the collection plan and labels snippets or writes synthetic
examples. Python compares a majority baseline with word and character TF-IDF
classifiers on validation data, then evaluates the selected model on a separate
test split. Web examples use hostname groups to limit overlap between splits.
Synthetic or AI-labeled test data measures agreement with those labels.
Test on representative, human-labeled examples before relying on the result.

This prototype searches indexed excerpts. Full-page crawling, additional model
types, checkpoint and resume, and remote Mac-to-Windows job dispatch are outside
this build. The idle setting gates the start; running jobs continue if you return.

## GitHub releases

Each push to `main` triggers a macOS build and publishes a prerelease such as
`v1.0.0-main.12` if checks pass. The workflow attaches the app ZIP and SHA-256
checksum to the repository's GitHub Release. Push a version tag such as `v1.0.0`
to publish a stable release. The workflow uses a macOS ARM64 runner. [GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

Extract the ZIP and use the Python setup instructions above from the extracted
folder. Open the included ALMG app bundle in Finder. The archive includes the
backend source and requires Python 3.12 and a separate model download. It uses
local signing and does not include Apple notarization.
