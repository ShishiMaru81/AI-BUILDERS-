"""Retrieve tomato and potato entries from the authors' public Kaggle ZIP."""

import argparse
import hashlib
import io
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen
from zipfile import ZipFile


URL = "https://www.kaggle.com/api/v1/datasets/download/muhriddinmuxiddinov/fruits-and-vegetables-dataset"
BLOCK_SIZE = 4 * 1024 * 1024


class RangeFile(io.RawIOBase):
    def __init__(self, url):
        self.position = 0
        with urlopen(Request(url, headers={"Range": "bytes=0-0"}), timeout=30) as response:
            if response.status != 206:
                raise ValueError("The public archive does not provide HTTP byte ranges")
            self.url = response.url
            self.size = int(response.headers["Content-Range"].split("/")[-1])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = {0: 0, 1: self.position, 2: self.size}[whence] + offset
        if self.position < 0:
            raise OSError("Cannot seek before start of the public archive")
        return self.position

    @lru_cache(maxsize=5)
    def block(self, offset):
        end = min(offset + BLOCK_SIZE, self.size) - 1
        # The range-specific URL prevents intermediary caches from replaying a different byte range.
        for request_url in (self.url, URL + f"?rangeBlock={offset}"):
            request = Request(request_url, headers={"Range": f"bytes={offset}-{end}"})
            with urlopen(request, timeout=50) as response:
                if response.status != 206 or response.headers.get("Content-Range") != f"bytes {offset}-{end}/{self.size}":
                    continue
                data = response.read()
            if len(data) == end - offset + 1:
                return data
        raise ValueError(f"Archive returned the wrong range at offset {offset}")

    def read(self, size=-1):
        end = self.size if size < 0 else min(self.position + size, self.size)
        result = bytearray()
        while self.position < end:
            offset = self.position // BLOCK_SIZE * BLOCK_SIZE
            within = self.position - offset
            limit = min(end - self.position, BLOCK_SIZE - within)
            result.extend(self.block(offset)[within:within + limit])
            self.position += limit
        return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save the targeted image subset, or omit to list entries")
    args = parser.parse_args()
    with RangeFile(URL) as stream, ZipFile(stream) as archive:
        eligible = []
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            folders = " ".join(path.parts[:-1]).casefold()
            crop = re.search(r"potato|tomato", folders)
            state = re.search(r"fresh|rotten", folders)
            if crop and state and path.suffix.casefold() in (".jpg", ".jpeg", ".png", ".webp"):
                eligible.append((entry, crop.group(), state.group()))
        counts = Counter(f"{crop}/{state}" for _, crop, state in eligible)
        print(json.dumps({"archive_bytes": stream.size, "images": dict(counts),
                          "examples": [entry.filename for entry, _, _ in eligible[:5]]}), flush=True)
        if args.output is None:
            return
        if len(counts) != 4:
            raise ValueError("The archive did not expose all four requested crop and condition pairs")
        args.output.mkdir(parents=True, exist_ok=True)
        provenance = []
        for entry, crop, state in sorted(eligible, key=lambda item: item[0].header_offset):
            filename = hashlib.sha256(entry.filename.encode()).hexdigest()[:24] + PurePosixPath(entry.filename).suffix.lower()
            target = args.output / crop / state / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.is_file():
                target.write_bytes(archive.read(entry))
            provenance.append({"path": target.relative_to(args.output).as_posix(), "original": entry.filename})
        (args.output / "archive-members.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
