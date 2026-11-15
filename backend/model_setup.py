"""Resumable, verified downloads for the local inference checkpoint."""
import hashlib
import json
import os
import re
from pathlib import Path
from threading import Event, Lock, Thread


CHUNK = 1024 * 1024


class Paused(Exception):
    """Interrupt model setup at a safe cancellation point."""
    pass


class ModelSetup:
    """Manage checkpoint downloads and verification for one local model directory."""
    def __init__(self, repo, directory):
        """Initialize the download state and locate manifest and verification metadata."""
        self.repo = repo
        self.directory = directory
        self.manifest_path = directory / ".studio-manifest.json"
        self.verified_path = directory / ".studio-verified.json"
        self.lock = Lock()
        self.stop = Event()
        self.state = {"phase": "idle", "error": None}

    def read(self, path):
        """Read JSON metadata, returning None if it is missing or unreadable."""
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return None

    def write(self, path, data):
        """Replace JSON metadata atomically using a temporary sibling."""
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data))
        temporary.replace(path)

    def fingerprints(self, files):
        """Collect file metadata used to detect changes after verification."""
        result = {}
        for name, size, _ in files:
            try:
                info = (self.directory / name).stat()
            except OSError:
                return None
            if info.st_size != size:
                return None
            result[name] = [info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino]
        return result

    def status(self):
        """Report checkpoint readiness and progress from current state and disk contents."""
        with self.lock:
            state = dict(self.state)
        manifest = self.read(self.manifest_path)
        files = manifest["files"] if manifest else []
        total = sum(size for _, size, _ in files)
        done = 0
        completed = 0
        for name, size, digest in files:
            path = self.directory / name
            partial = self.partial(name, digest)
            try:
                if path.stat().st_size == size:
                    completed += 1
                    done += size
                    continue
            except FileNotFoundError:
                pass
            try:
                done += min(size, partial.stat().st_size)
            except FileNotFoundError:
                pass
        stamp = self.read(self.verified_path)
        ready = bool(manifest and stamp and stamp["revision"] == manifest["revision"]
                     and stamp["files"] == self.fingerprints(files))
        active = state["phase"] in ("preparing", "downloading", "verifying", "pausing")
        if not active and ready:
            state["phase"] = "ready"
        elif state["phase"] == "ready":
            state["phase"] = "broken"
        elif state["phase"] == "idle" and 0 < done < total:
            state["phase"] = "paused"
        return {**state, "ready": ready and not active, "downloading": active,
                "downloaded_bytes": done, "total_bytes": total,
                "completed_files": completed, "total_files": len(files)}

    def partial(self, name, digest):
        """Return the partial download path for a specific file and digest."""
        return self.directory / f".{name}.{digest}.part"

    def check_stop(self):
        """Raise Paused when the user has requested cancellation."""
        if self.stop.is_set():
            raise Paused()

    def update(self, **changes):
        """Update worker state while preserving an outstanding pause request."""
        with self.lock:
            if self.state["phase"] != "pausing" or changes["phase"] in ("paused", "failed", "ready", "broken"):
                self.state.update(changes)

    def start(self, action):
        """Pause the active operation or schedule a setup worker if none is active."""
        with self.lock:
            if action == "pause":
                if self.state["phase"] in ("preparing", "downloading", "verifying"):
                    self.stop.set()
                    self.state["phase"] = "pausing"
                return
            if self.state["phase"] in ("preparing", "downloading", "verifying", "pausing"):
                return
            self.stop.clear()
            self.state = {"phase": "preparing", "error": None, "file": None}
            Thread(target=self.run, args=(action,), daemon=True).start()

    def manifest(self):
        """Fetch the model revision and expected checkpoint file digests."""
        from huggingface_hub import HfApi

        cached = self.read(self.manifest_path)
        if cached:
            return cached
        info = HfApi().model_info(self.repo, files_metadata=True, timeout=30)
        files = []
        for file in info.siblings:
            name = file.rfilename
            if Path(name).name != name or Path(name).suffix not in (".safetensors", ".json", ".jinja", ".txt", ".model"):
                continue
            digest = file.lfs.sha256 if file.lfs else file.blob_id
            if not digest or file.size is None:
                raise ValueError(f"Missing integrity metadata for {name}.")
            files.append([name, file.size, digest])
        if not info.sha or not any(name.endswith(".safetensors") for name, _, _ in files):
            raise ValueError("Hugging Face did not return the model manifest.")
        manifest = {"revision": info.sha, "files": files}
        self.write(self.manifest_path, manifest)
        return manifest

    def matches(self, path, size, digest):
        """Verify a file size and digest against the manifest."""
        try:
            if path.stat().st_size != size:
                return False
            checksum = hashlib.sha256() if len(digest) == 64 else hashlib.sha1()
            if len(digest) == 40:
                checksum.update(f"blob {size}\0".encode())
            with path.open("rb") as stream:
                while chunk := stream.read(CHUNK * 4):
                    self.check_stop()
                    checksum.update(chunk)
            return checksum.hexdigest() == digest
        except FileNotFoundError:
            return False

    def fetch(self, revision, name, size, digest):
        """Download or resume one checkpoint file and verify it before promotion."""
        from huggingface_hub import hf_hub_url
        from huggingface_hub.utils import get_session

        target = self.directory / name
        partial = self.partial(name, digest)
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > size:
            partial.unlink()
            offset = 0
        if offset < size:
            url = hf_hub_url(self.repo, name, revision=revision)
            headers = {"Accept-Encoding": "identity"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            with get_session().stream("GET", url, headers=headers, timeout=20, follow_redirects=True) as response:
                if response.status_code == 206:
                    match = re.fullmatch(r"bytes (\d+)-\d+/(\d+)", response.headers.get("Content-Range", ""))
                    if not match or (int(match[1]), int(match[2])) != (offset, size):
                        raise ValueError(f"Invalid resume range for {name}.")
                elif response.status_code == 200:
                    offset = 0
                else:
                    raise ValueError(f"Unexpected download response for {name}.")
                with partial.open("ab" if offset else "wb") as output:
                    for chunk in response.iter_bytes(chunk_size=CHUNK):
                        self.check_stop()
                        output.write(chunk)
        if not self.matches(partial, size, digest):
            if partial.stat().st_size >= size:
                partial.unlink()
            raise ValueError(f"{name} failed the integrity check. Resume to retry.")
        partial.replace(target)

    def run(self, action):
        """Run model setup and publish the resulting status."""
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.verified_path.unlink(missing_ok=True)
            manifest = self.manifest()
            files = manifest["files"]
            verified = {}
            for name, size, digest in files:
                self.check_stop()
                path = self.directory / name
                self.update(phase="verifying", file=name)
                if not self.matches(path, size, digest):
                    if action == "verify":
                        self.update(phase="broken", error=f"{name} is missing or damaged.", file=None)
                        return
                    self.update(phase="downloading", file=name)
                    self.fetch(manifest["revision"], name, size, digest)
                info = path.stat()
                verified[name] = [info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino]
            self.check_stop()
            if verified != self.fingerprints(files):
                raise ValueError("Model files changed during verification. Verify again.")
            self.write(self.verified_path, {"revision": manifest["revision"], "files": verified})
            self.update(phase="ready", file=None)
        except Paused:
            self.update(phase="paused", file=None)
        except Exception as error:
            if self.stop.is_set():
                self.update(phase="paused", file=None)
            else:
                self.update(phase="failed", error=str(error), file=None)
