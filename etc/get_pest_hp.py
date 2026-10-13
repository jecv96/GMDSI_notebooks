"""Download the PEST_HP suite and install it into the active python environment.

Used by `pixi run get-exes` (and `pixi run get-pest-hp`). PEST_HP is not
published on GitHub, so get-modflow/get-pestpp cannot fetch it; it is
distributed as a zip of Windows executables on pesthomepage.org.

The executables (and the DLL that pest_hp_mkl.exe needs) go into the same
folder where get-modflow/get-pestpp put mf6.exe and pestpp-*.exe (the
environment's Scripts folder on Windows), so they are on the PATH of
`pixi run ...` and `pixi shell`. The PDF manuals go to <env>/share/doc/pest_hp.

Usage:
    python etc/get_pest_hp.py                 # pinned version (see URL below)
    python etc/get_pest_hp.py --url <url>     # another release
    python etc/get_pest_hp.py --zip <file>    # a zip you already downloaded
    python etc/get_pest_hp.py --force         # reinstall even if up to date
"""
import argparse
import os
import shutil
import sys
import sysconfig
import tempfile
import urllib.request
import zipfile

# Pinned like the MODFLOW and PEST++ releases in pixi.toml, so everyone gets
# the same build. Change it here to move to a newer HP suite.
PEST_HP_URL = "https://s3.amazonaws.com/docs.pesthomepage.org/software/hp_suite_18.7.zip"

# Files that mark a complete install.
REQUIRED = ["pest_hp.exe", "agent_hp.exe"]
# Name of the file that records which zip was installed.
MARKER = "pest_hp_version.txt"


def _download(url, dest):
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as response, open(dest, "wb") as f:
        shutil.copyfileobj(response, f)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=PEST_HP_URL, help="URL of the HP suite zip")
    parser.add_argument("--zip", default=None, help="local HP suite zip (no download)")
    parser.add_argument("--force", action="store_true", help="reinstall even if already installed")
    args = parser.parse_args()

    # PEST_HP is only distributed as Windows executables: do nothing elsewhere,
    # so `pixi run get-exes` keeps working on Linux and macOS.
    if not sys.platform.startswith("win"):
        print("PEST_HP is distributed for Windows only - skipping its installation on this platform")
        return 0

    # the folder get-modflow/get-pestpp use for ":python" (Scripts on Windows)
    bin_dir = sysconfig.get_path("scripts")
    doc_dir = os.path.join(sys.prefix, "share", "doc", "pest_hp")
    source = args.zip if args.zip is not None else args.url
    marker = os.path.join(bin_dir, MARKER)

    # skip the download when this exact zip is already installed
    if not args.force and os.path.exists(marker) and all(os.path.exists(os.path.join(bin_dir, f)) for f in REQUIRED):
        with open(marker) as f:
            if f.read().strip() == source:
                print(f"PEST_HP already installed in {bin_dir} (use --force to reinstall)")
                return 0

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = args.zip
        if zip_path is None:
            zip_path = os.path.join(tmp, "hp_suite.zip")
            try:
                _download(args.url, zip_path)
            except Exception as e:
                print(
                    f"could not download PEST_HP from {args.url}:\n  {e}\n"
                    "download the HP suite zip from https://pesthomepage.org and install it with:\n"
                    "  pixi run python etc/get_pest_hp.py --zip <path to the zip>",
                    file=sys.stderr,
                )
                return 1
        if not zipfile.is_zipfile(zip_path):
            print(f"{zip_path} is not a zip file", file=sys.stderr)
            return 1

        installed = []
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = os.path.basename(info.filename)
                ext = os.path.splitext(name)[1].lower()
                if ext in (".exe", ".dll"):
                    dest = os.path.join(bin_dir, name)
                elif ext == ".pdf":
                    os.makedirs(doc_dir, exist_ok=True)
                    dest = os.path.join(doc_dir, name)
                else:
                    continue
                with zf.open(info) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                installed.append(name)

    missing = [f for f in REQUIRED if f not in installed]
    if missing:
        print(f"the zip did not contain {', '.join(missing)}", file=sys.stderr)
        return 1

    with open(marker, "w") as f:
        f.write(source + "\n")
    exes = sorted(n for n in installed if n.lower().endswith(".exe"))
    print(f"installed {len(exes)} PEST_HP suite executables in {bin_dir}:")
    print("  " + ", ".join(exes))
    if os.path.isdir(doc_dir):
        print(f"manuals in {doc_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
