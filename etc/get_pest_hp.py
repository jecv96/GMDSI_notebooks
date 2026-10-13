"""Download PEST_HP and the PEST checking utilities into the active python environment.

Used by `pixi run get-exes` (and `pixi run get-pest-hp`). Neither PEST_HP nor
PEST are published on GitHub, so get-modflow/get-pestpp cannot fetch them;
both are distributed as zips of Windows executables on pesthomepage.org:

  - the HP suite (pest_hp, agent_hp, ...): all its executables are installed;
  - the PEST suite: only the checking utilities pestchek, tempchek and inschek
    are installed by default (use --pest-all for every PEST suite program,
    e.g. parrep, svdaprep, predunc, genlinpred, jcoblank).

The executables (and the DLL that the *_mkl.exe programs need) go into the
same folder where get-modflow/get-pestpp put mf6.exe and pestpp-*.exe (the
environment's Scripts folder on Windows), so they are on the PATH of
`pixi run ...` and `pixi shell`. The PDF manuals go to <env>/share/doc/pest_hp.

Usage:
    python etc/get_pest_hp.py                     # pinned versions (see URLs below)
    python etc/get_pest_hp.py --force             # reinstall even if up to date
    python etc/get_pest_hp.py --zip <file>        # HP suite zip you already downloaded
    python etc/get_pest_hp.py --url <url>         # another HP suite release
    python etc/get_pest_hp.py --pest-zip <file>   # PEST suite zip you already downloaded
    python etc/get_pest_hp.py --pest-url <url>    # another PEST suite release
    python etc/get_pest_hp.py --pest-all          # every PEST suite program, not only the checkers
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
# the same build. Change them here to move to newer suites.
PEST_HP_URL = "https://s3.amazonaws.com/docs.pesthomepage.org/software/hp_suite_18.7.zip"
PEST_URL = "https://s3.amazonaws.com/docs.pesthomepage.org/software/pest18.zip"

# PEST suite programs installed by default: the control/template/instruction file checkers.
PEST_CHECKERS = ["pestchek.exe", "tempchek.exe", "inschek.exe"]
# PEST suite manuals worth keeping next to the PEST_HP ones.
PEST_DOCS = ["pestman1.pdf", "pestman2.pdf"]


def _download(url, dest):
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=300) as response, open(dest, "wb") as f:
        shutil.copyfileobj(response, f)


def install_zip(label, url, zip_file, exes, docs, required, marker_name, bin_dir, doc_dir, force):
    """Install the executables/DLLs (`exes`, None = all) and PDFs (`docs`, None = all) of one zip.

    Returns 0 on success, 1 on failure.
    """
    source = zip_file if zip_file is not None else url
    marker = os.path.join(bin_dir, marker_name)
    # what this install was asked for, so changing --pest-all reinstalls
    request = f"{source} {'all' if exes is None else ','.join(exes)}"

    # skip the download when this exact request is already installed
    if not force and os.path.exists(marker) and all(os.path.exists(os.path.join(bin_dir, f)) for f in required):
        with open(marker) as f:
            if f.read().strip() == request:
                print(f"{label} already installed in {bin_dir} (use --force to reinstall)")
                return 0

    wanted_exes = None if exes is None else {e.lower() for e in exes}
    wanted_docs = None if docs is None else {d.lower() for d in docs}
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = zip_file
        if zip_path is None:
            zip_path = os.path.join(tmp, "suite.zip")
            try:
                _download(url, zip_path)
            except Exception as e:
                print(
                    f"could not download the {label} from {url}:\n  {e}\n"
                    "download the zip from https://pesthomepage.org and install it with\n"
                    "  pixi run get-pest-hp --zip <HP suite zip>   or   --pest-zip <PEST suite zip>",
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
                if ext in (".exe", ".dll") and (wanted_exes is None or name.lower() in wanted_exes):
                    dest = os.path.join(bin_dir, name)
                elif ext == ".pdf" and (wanted_docs is None or name.lower() in wanted_docs):
                    os.makedirs(doc_dir, exist_ok=True)
                    dest = os.path.join(doc_dir, name)
                else:
                    continue
                with zf.open(info) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                installed.append(name.lower())

    missing = [f for f in required if f.lower() not in installed]
    if missing:
        print(f"the {label} zip did not contain {', '.join(missing)}", file=sys.stderr)
        return 1

    with open(marker, "w") as f:
        f.write(request + "\n")
    names = sorted(n for n in installed if n.endswith(".exe"))
    print(f"installed {len(names)} {label} executables in {bin_dir}:")
    print("  " + ", ".join(names))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=PEST_HP_URL, help="URL of the HP suite zip")
    parser.add_argument("--zip", default=None, help="local HP suite zip (no download)")
    parser.add_argument("--pest-url", default=PEST_URL, help="URL of the PEST suite zip")
    parser.add_argument("--pest-zip", default=None, help="local PEST suite zip (no download)")
    parser.add_argument("--pest-all", action="store_true", help="install every PEST suite program, not only the checkers")
    parser.add_argument("--force", action="store_true", help="reinstall even if already installed")
    args = parser.parse_args()

    # PEST and PEST_HP are only distributed as Windows executables: do nothing
    # elsewhere, so `pixi run get-exes` keeps working on Linux and macOS.
    if not sys.platform.startswith("win"):
        print("PEST_HP and the PEST utilities are distributed for Windows only - skipping them on this platform")
        return 0

    # the folder get-modflow/get-pestpp use for ":python" (Scripts on Windows)
    bin_dir = sysconfig.get_path("scripts")
    doc_dir = os.path.join(sys.prefix, "share", "doc", "pest_hp")

    ret = install_zip(
        "PEST_HP suite", args.url, args.zip,
        exes=None, docs=None, required=["pest_hp.exe", "agent_hp.exe"],
        marker_name="pest_hp_version.txt", bin_dir=bin_dir, doc_dir=doc_dir, force=args.force,
    )
    ret = max(ret, install_zip(
        "PEST suite", args.pest_url, args.pest_zip,
        exes=None if args.pest_all else PEST_CHECKERS, docs=PEST_DOCS, required=PEST_CHECKERS,
        marker_name="pest_version.txt", bin_dir=bin_dir, doc_dir=doc_dir, force=args.force,
    ))
    if os.path.isdir(doc_dir):
        print(f"manuals in {doc_dir}")
    return ret


if __name__ == "__main__":
    sys.exit(main())
