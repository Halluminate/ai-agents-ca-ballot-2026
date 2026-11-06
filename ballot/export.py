"""Publish runs: a cleaned copy into results/, and the heavy logs into a tar for a release.

Usage: python3 -m ballot export [runs folder] [--logs <archive.tar>]
The runs folder defaults to runs/; the archive to runs/logs.tar, written in parts below
GitHub's 2 GB limit per release file: logs-part1.tar, logs-part2.tar and so on.

results/rollouts/<setup>/<question>__prop-<NN>/ gets each rollout's full event log
(trajectory.jsonl), its result (result.json) and the URLs its searches returned
(search_results.json); its other/ subfolder gets the prompt, final reply, billed cost,
stderr, network summary and any failed attempt's event log. The archive keeps the same paths
for the heavy files: each rollout's complete network log, the recording proxy's log and the
archive of its throwaway folders, failed attempts' included, plus any runs set aside from the
runs folder (set-aside/<folder>-collisions/). results/ also gets the runs folder's manifest
and data/excluded.json. Nothing that holds a secret is copied: not .env, not the proxy's CA
key, not node_modules or the venv.

Compressed files carry no timestamp, so exporting the same runs again gives the same bytes.

Everything copied is cleaned on the way: any 12-character piece of any of the keys
(Grok Build logs the key's last 12 characters), this machine's public IP addresses
(websites echo them back), its name, and the project and home folder paths (Gemini CLI's
error traces and the runner's log print them) are replaced. Node's compile cache is left
out because it holds the home folder path, and archive entries carry no owner name.
"""

import argparse
import gzip
import io
import ipaddress
import json
import re
import socket
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path
from urllib.parse import quote

from ballot.analysis.load import OTHER
from ballot.analysis.sites import result_urls
from ballot.config import load_keys
from ballot.meta import rollout_slug, setup_slug
from ballot.netlog import secret_variants
from ballot.paths import DATA, RESULTS, ROOT, RUNS

ECHO_HEADERS = ("x-client-ip", "x-forwarded-for", "x-real-ip", "true-client-ip", "cf-connecting-ip", "client-ip")
ROOM_SKIP = ("tmp/node-compile-cache",)
LOCATION_HEADER = re.compile(rb'(\["x-client-location",\s*")[^"]*(")', re.I)
PART_LIMIT = 1_900_000_000  # GitHub takes release files up to 2 GiB


def owner_addresses(folders: list[Path]) -> set[str]:
    """This machine's public IP addresses: the ones websites echoed back, plus its current ones."""
    found: set[str] = set()

    def keep(value: str) -> None:
        for part in value.split(","):
            candidate = part.strip().split("%")[0]
            try:
                if ipaddress.ip_address(candidate).is_global:
                    found.add(candidate)
            except ValueError:
                pass

    for folder in folders:
        for log in folder.glob("*/network*.jsonl.gz"):
            for line in gzip.decompress(log.read_bytes()).splitlines():
                record = json.loads(line)
                for name, value in ((record.get("response") or {}).get("headers") or []) if record.get("type") == "http" else []:
                    if name.lower() in ECHO_HEADERS:
                        keep(value)
    interfaces = subprocess.run(["ifconfig"], capture_output=True, text=True).stdout
    for address in re.findall(r"\binet6? ([0-9a-fA-F:.]+)", interfaces):
        keep(address)
    for service in ("https://api.ipify.org", "https://api64.ipify.org"):
        try:
            with urllib.request.urlopen(service, timeout=10) as response:
                keep(response.read().decode().strip())
        except OSError:
            pass  # best effort; the echoed and interface addresses already cover the logs
    return found


def private_names() -> dict[str, str]:
    """The folders the runs were made in and this machine's name, each with what replaces it.

    The runs folder can be a link to where the runs were made, so both that place and this
    repository count as the project folder.
    """
    names = {}
    for path, label in ((str(RUNS.resolve().parent), "<project>"), (str(ROOT), "<project>"), (str(Path.home()), "~")):
        names[path] = names[quote(path)] = label  # file:// URLs in stack traces escape the spaces
    host = socket.gethostname()
    names[host] = names[host.split(".")[0]] = "<host>"
    return names


class Cleaner:
    """Replaces key pieces, the machine's IP addresses and its private names in anything being shared."""

    def __init__(self, keys: list[str], addresses: set[str], private: dict[str, str]):
        pieces: set[str] = set()
        for key in keys:
            body = key.removeprefix("sk-or-v1-")
            pieces |= {body[i:i + 12] for i in range(len(body) - 11)} | secret_variants(key)
        self.ips = set()
        for address in addresses:
            self.ips |= {address, address.replace(":", "%3A"), address.replace(":", "%3a")}
        self.private = {name: label.encode() for name, label in private.items() if name}
        self.needles = sorted({p.encode() for p in pieces | self.ips | set(self.private) if p}, key=len, reverse=True)
        self.pattern = re.compile(b"|".join(re.escape(n) for n in self.needles))
        self.hits = 0

    def found(self, data: bytes) -> bool:
        """Whether there's anything to replace. Plain substring checks are about six times faster than the regex,
        and most files hold nothing, so the regex only runs where it will replace something."""
        return any(needle in data for needle in self.needles)

    def text(self, data: bytes) -> bytes:
        if not self.found(data):
            return LOCATION_HEADER.sub(rb"\1<redacted>\2", data)

        def replace(match: re.Match) -> bytes:
            self.hits += 1
            found = match.group(0).decode()
            if found in self.private:
                return self.private[found]
            return b"<redacted-ip>" if found in self.ips else b"<redacted>"

        return LOCATION_HEADER.sub(rb"\1<redacted>\2", self.pattern.sub(replace, data))

    def binary(self, data: bytes) -> bytes:
        """Same-length masks, so databases and other binary files stay readable."""
        if not self.found(data):
            return data

        def replace(match: re.Match) -> bytes:
            self.hits += 1
            return b"*" * len(match.group(0))

        return self.pattern.sub(replace, data)

    def any(self, data: bytes) -> bytes:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return self.binary(data)
        return self.text(data)


def anonymous(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uname = info.gname = ""
    info.uid = info.gid = 0
    return info


def clean_room(path: Path, cleaner: Cleaner) -> bytes:
    """Rebuild a room archive without Node's compile cache, with owners blanked and contents cleaned."""
    out = io.BytesIO()
    with tarfile.open(path) as source, tarfile.open(fileobj=out, mode="w:gz") as target:
        for member in source.getmembers():
            if any(member.name == skip or member.name.startswith(skip + "/") for skip in ROOM_SKIP):
                continue
            if member.isfile():
                data = cleaner.any(source.extractfile(member).read())
                member.size = len(data)
                target.addfile(anonymous(member), io.BytesIO(data))
            else:
                target.addfile(anonymous(member))
    return out.getvalue()


class SplitTar:
    """A tar archive written in numbered parts, each kept below PART_LIMIT bytes."""

    def __init__(self, archive: Path):
        self.archive, self.parts, self.tar = archive, [], None

    def add(self, name: str, data: bytes, like: Path) -> None:
        if self.tar is None or self.tar.fileobj.tell() + len(data) + 20480 > PART_LIMIT:
            self.close()
            self.parts.append(self.archive.with_name(f"{self.archive.stem}-part{len(self.parts) + 1}{self.archive.suffix}"))
            self.tar = tarfile.open(self.parts[-1], "w")
        info = anonymous(tarfile.TarInfo(name))
        info.size, info.mtime, info.mode = len(data), int(like.stat().st_mtime), 0o644
        self.tar.addfile(info, io.BytesIO(data))

    def close(self) -> None:
        if self.tar is not None:
            self.tar.close()
            self.tar = None


def copy_rollout(run_dir: Path, rel: str, out: Path, tar: SplitTar, cleaner: Cleaner, harness: str) -> int:
    """One rollout's light files into out/rel, its heavy ones into the archive. Returns how many went to the archive."""
    target = out / rel
    (target / OTHER).mkdir(parents=True)
    heavy = 0
    for path in sorted(run_dir.iterdir()):
        name, member = path.name, f"{rel}/{path.name}"
        # result.json, search_results.json and trajectory.jsonl sit at the top; every other light file goes in other/
        light = target if name in ("result.json", "events.jsonl") else target / OTHER
        if name.endswith("room.tar.gz"):
            tar.add(member, clean_room(path, cleaner), path)
            heavy += 1
        elif name.endswith(".jsonl.gz"):  # full network logs
            tar.add(member, gzip.compress(cleaner.text(gzip.decompress(path.read_bytes())), 6, mtime=0), path)
            heavy += 1
        elif name.startswith("proxy"):  # the recording proxy's logs
            tar.add(member, cleaner.text(path.read_bytes()), path)
            heavy += 1
        elif name.endswith("events.jsonl"):  # the trajectory, as the harness saved it (failed attempts go in other/)
            (light / name.replace("events.jsonl", "trajectory.jsonl")).write_bytes(cleaner.text(path.read_bytes()))
        elif name.endswith(("stderr.log", ".json", ".txt")):
            # result, prompt, reply, stderr, network summary and billed cost
            (light / name).write_bytes(cleaner.text(path.read_bytes()))
    urls = json.dumps(result_urls(run_dir, harness), indent=0).encode()
    (target / "search_results.json").write_bytes(cleaner.text(urls))
    return heavy


def set_aside(source: Path, tar: SplitTar, cleaner: Cleaner) -> int:
    """Runs set aside from the runs folder (<folder>-collisions/, next to it) into the archive."""
    heavy = 0
    aside = source.parent / f"{source.name}-collisions"
    for path in sorted(p for p in aside.rglob("*") if p.is_file()) if aside.is_dir() else []:
        if path.name.endswith("room.tar.gz"):
            data = clean_room(path, cleaner)
        elif path.name.endswith(".gz"):
            data = gzip.compress(cleaner.text(gzip.decompress(path.read_bytes())), 6, mtime=0)
        else:
            data = cleaner.text(path.read_bytes())
        tar.add(f"set-aside/{aside.name}/{path.relative_to(aside)}", data, path)
        heavy += 1
    return heavy


def main() -> None:
    parser = argparse.ArgumentParser(prog=sys.argv[0], description="Cleaned copy of the runs into results/.")
    parser.add_argument("runs", nargs="?", type=Path, default=RUNS)
    parser.add_argument("--logs", type=Path, default=RUNS / "logs.tar", help="archive for the heavy logs")
    parser.add_argument("--out", type=Path, default=RESULTS)
    args = parser.parse_args()
    if (args.out / "rollouts").exists():
        sys.exit(f"{args.out / 'rollouts'} already exists. Remove it to export again.")

    keys = load_keys()
    if not keys:
        # Without the keys there is nothing to look for, and Grok Build's own logs hold a piece of the key.
        sys.exit("No API keys in .env or the environment, so key pieces couldn't be removed. Add the keys the runs used "
                 "(python3 -m ballot keys) and export again.")
    cleaner = Cleaner(list(keys.values()), owner_addresses([args.runs]), private_names())
    runs = [p.resolve() for p in sorted(args.runs.iterdir()) if p.is_dir() and (p / "result.json").exists()]
    results = [json.loads((p / "result.json").read_text()) for p in runs]
    repeats = max(r["repeat"] for r in results)

    args.out.mkdir(parents=True, exist_ok=True)
    tar = SplitTar(args.logs)
    heavy = 0
    for run_dir, result in zip(runs, results):
        rel = f"rollouts/{setup_slug(result['model'], result['harness'])}/" \
              f"{rollout_slug(result['prompt'], result['prop'], result['repeat'], repeats)}"
        heavy += copy_rollout(run_dir, rel, args.out, tar, cleaner, result["harness"])
    heavy += set_aside(args.runs, tar, cleaner)
    tar.close()
    (args.out / "manifest.json").write_bytes(cleaner.text((args.runs / "manifest.json").read_bytes()))
    (args.out / "excluded.json").write_bytes(cleaner.text((DATA / "excluded.json").read_bytes()))
    print(f"Copied {len(runs)} rollouts to {args.out / 'rollouts'}. {heavy} heavy log files went to "
          f"{', '.join(p.name for p in tar.parts)}. Replaced {cleaner.hits} key pieces, IP addresses or private names, "
          f"and checked {len(cleaner.ips)} address forms.")


if __name__ == "__main__":
    main()
