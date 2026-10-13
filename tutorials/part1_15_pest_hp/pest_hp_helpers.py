"""Helpers to run PEST_HP on a PEST interface built with pyEMU.

The tutorials in this repo drive PEST++ (pestpp-glm, pestpp-ies, ...). PEST_HP
reads the same (version 1) control file, but it is stricter: names have length
limits, PEST++ "++" options are not part of its input, its parallel agents are
a different executable (agent_hp) and its outputs (.rec, .rei, .jco, ...) are
not the PEST++ csv files. These functions cover those differences so the rest
of the pyEMU workflow can stay as it is in the other notebooks.

See docs/guia_pest_hp.md for the step-by-step guide that uses this module.
"""
import os
import re
import shutil
import socket
import subprocess as sp
import sys
import time

import numpy as np
import pandas as pd
import pyemu

# Name length limits for a PEST / PEST_HP control file (see the PEST manual,
# "Control file" chapter). Run pestchek to confirm them for your PEST version.
MAX_PAR_NAME = 12
MAX_OBS_NAME = 20
MAX_PI_NAME = 20
MAX_GROUP_NAME = 12

# PEST_HP executables: the manager and the parallel agent.
PEST_HP_EXES = ["pest_hp", "agent_hp"]
# Optional PEST checking utilities shipped with the standard PEST suite.
PEST_CHECK_EXES = ["pestchek", "tempchek", "inschek"]


def find_exe(name, exe_dir=None):
    """Return the full path to an executable, or None if it is not found.

    Looks in `exe_dir` first (e.g. the folder where you unzipped PEST_HP) and
    then on the PATH. Handles the '.exe' suffix on Windows.
    """
    candidates = [name]
    if sys.platform.startswith("win") and not name.lower().endswith(".exe"):
        candidates.insert(0, name + ".exe")
    if exe_dir is not None:
        for c in candidates:
            path = os.path.join(exe_dir, c)
            if os.path.isfile(path):
                return os.path.abspath(path)
    for c in candidates:
        path = shutil.which(c)
        if path is not None:
            return path
    return None


def prep_pest_hp_bins(dest_path, exe_dir=None, include_check_utils=True):
    """Copy pest_hp/agent_hp (and pestchek, tempchek, inschek if present) into `dest_path`.

    Like herebedragons.prep_bins does for PEST++, the executables are copied
    into the template folder so every agent folder made from it is complete.
    Raises FileNotFoundError if pest_hp or agent_hp cannot be found.
    """
    missing = []
    names = PEST_HP_EXES + (PEST_CHECK_EXES if include_check_utils else [])
    for name in names:
        src = find_exe(name, exe_dir)
        if src is None:
            # the checking utilities are optional; PEST_HP itself is not
            if name in PEST_HP_EXES:
                missing.append(name)
            continue
        dest = os.path.join(dest_path, os.path.basename(src))
        if os.path.abspath(src) != os.path.abspath(dest):
            shutil.copy2(src, dest)
    if missing:
        raise FileNotFoundError(
            "PEST_HP executables not found: {0}\n"
            "install them into the pixi environment with:\n"
            "    pixi run get-pest-hp\n"
            "or put the PEST_HP folder on the PATH, or pass it as `exe_dir`.".format(", ".join(missing))
        )


def check_pest_hp_compat(pst, verbose=True):
    """Report everything in `pst` that PEST_HP (PEST version 1 control file) will reject.

    Returns a dict {problem description: list of offending names}. An empty
    dict means no problem was found by these checks; still run pestchek.
    """
    problems = {}

    def _check(label, names, max_len):
        names = list(names)
        too_long = [n for n in names if len(n) > max_len]
        if too_long:
            problems[f"{label} longer than {max_len} chars"] = too_long
        with_space = [n for n in names if " " in n]
        if with_space:
            problems[f"{label} containing spaces"] = with_space

    _check("parameter names", pst.par_names, MAX_PAR_NAME)
    _check("observation names", pst.obs_names, MAX_OBS_NAME)
    _check("parameter group names", pst.par_groups, MAX_GROUP_NAME)
    _check("observation group names", pst.obs_groups, MAX_GROUP_NAME)
    if pst.nprior > 0:
        _check("prior information names", pst.prior_names, MAX_PI_NAME)
        # in regularization mode PEST only treats groups starting with "regul"
        # as regularization
        if pst.control_data.pestmode == "regularization":
            pi_groups = pst.prior_information.obgnme.unique()
            if not any(g.lower().startswith("regul") for g in pi_groups):
                problems["no prior information group starts with 'regul'"] = list(pi_groups)

    if pst.pestpp_options:
        problems["PEST++ '++' options (ignored by PEST_HP)"] = list(pst.pestpp_options.keys())

    if verbose:
        if problems:
            for k, v in problems.items():
                print(f"{k}: {len(v)} -> {v[:5]}{' ...' if len(v) > 5 else ''}")
        else:
            print("no PEST_HP compatibility problems found (run pestchek too)")
    return problems


def shorten_par_names(pst, template_dir, max_len=MAX_PAR_NAME, map_file="par_name_map.csv"):
    """Rename parameters longer than `max_len` in `pst` AND in every template file.

    New names are built from the parameter group plus a counter (e.g.
    "hk1_0001"), which keeps them short and still tells you what they are.
    The old->new map is written to `template_dir/map_file` so results can be
    related back to the original (long) names.

    Run this BEFORE adding prior information (regularization), because prior
    information equations refer to parameter names.

    Returns the old->new map as a dict (empty if nothing had to be renamed).
    """
    if pst.nprior > 0:
        raise Exception("shorten_par_names(): rename parameters before adding prior information")

    par = pst.parameter_data
    long_names = [n for n in pst.par_names if len(n) > max_len]
    if len(long_names) == 0:
        return {}

    existing = set(pst.par_names)
    name_map = {}
    counters = {}
    for old in long_names:
        stem = re.sub(r"[^a-z0-9_]", "", par.loc[old, "pargp"].lower())[: max_len - 5]
        while True:
            counters[stem] = counters.get(stem, 0) + 1
            new = f"{stem}_{counters[stem]:04d}"
            if new not in existing:
                break
        existing.add(new)
        name_map[old] = new

    # rename inside the template files: only the text between the markers
    for tpl_file in pst.model_input_data.pest_file:
        tpl_path = os.path.join(template_dir, tpl_file)
        with open(tpl_path, "r") as f:
            lines = f.readlines()
        marker = lines[0].strip().split()[1]
        # e.g. "~    hk_i:2_j:2_zone:1    ~" -> "~    hk1_0001    ~"
        pattern = re.compile(re.escape(marker) + r"([^" + re.escape(marker) + r"]*)" + re.escape(marker))

        def _sub(m):
            token = m.group(1)
            name = token.strip().lower()
            if name not in name_map:
                return m.group(0)
            # keep the field width so the model input file keeps its layout
            new = name_map[name]
            width = len(token)
            return marker + new.center(width) + marker if width >= len(new) else marker + new + marker

        new_lines = [lines[0]] + [pattern.sub(_sub, line) for line in lines[1:]]
        with open(tpl_path, "w") as f:
            f.writelines(new_lines)

    # rename in the control file
    par.rename(index=name_map, inplace=True)
    par["parnme"] = par.index.values
    # tied parameters refer to the name of their parent
    if "partied" in par.columns:
        par["partied"] = par["partied"].apply(lambda x: name_map.get(x, x) if isinstance(x, str) else x)

    pd.DataFrame({"old_name": list(name_map.keys()), "new_name": list(name_map.values())}).to_csv(
        os.path.join(template_dir, map_file), index=False
    )
    print(f"renamed {len(name_map)} parameters; map written to {os.path.join(template_dir, map_file)}")
    return name_map


def prepare_pst_for_pest_hp(pst):
    """Remove the PEST++-only content from `pst` so the control file is plain PEST.

    PEST++ options are written as "++" lines at the end of the control file.
    They are of no use to PEST_HP, so they are dropped (the forecasts are still
    zero-weighted observations and will be in the .jco for FOSM with pyEMU).
    """
    if pst.pestpp_options:
        print("dropping PEST++ options:", list(pst.pestpp_options.keys()))
    pst.pestpp_options = {}
    return pst


def write_pst_for_pest_hp(pst, filename):
    """Write `pst` as a version 1 control file (the only version PEST_HP reads).

    Also makes the "control data" section acceptable to PEST/pestchek:
      - the 4th line (NTPLFLE NINSFLE PRECIS DPOINT ...) must hold 4 or 7
        values; pyEMU writes NUMCOM without JACFILE and MESSFILE (5 values,
        fine for PEST++), so these two are set to their default of 0;
      - a negative NUMLAM (pyEMU's default, a BEOPEST convention) is made
        positive. PEST_HP ignores NUMLAM, but pestchek warns about it.
    """
    cd = pst.control_data
    # assigning them makes pyEMU write them
    cd.jacfile = 0
    cd.messfile = 0
    if int(cd.numlam) < 0:
        cd.numlam = abs(int(cd.numlam))
    pst.write(filename, version=1)


def run_pestchek(case, cwd, exe_dir=None):
    """Run pestchek on `case` (control file name without or with .pst) in `cwd`.

    Returns pestchek's text output, or None if pestchek is not available.
    """
    exe = find_exe("pestchek", exe_dir) or find_exe("pestchek", cwd)
    if exe is None:
        print("pestchek not found - install it into the pixi environment with: pixi run get-pest-hp")
        return None
    case = case.replace(".pst", "")
    out = sp.run([exe, case], cwd=cwd, capture_output=True, text=True)
    print(out.stdout)
    return out.stdout


def _copy_dir(src, dest):
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def start_pest_hp(
    template_dir,
    pst_name,
    num_agents,
    master_dir="master_hp",
    agent_root=".",
    port=4004,
    pest_hp_exe="pest_hp",
    agent_exe="agent_hp",
    agent_takes_case=True,
    restart_flag=None,
    hostname="localhost",
    cleanup=True,
):
    """Run PEST_HP on this machine: one manager (pest_hp) plus `num_agents` agents (agent_hp).

    It does what pyemu.os_utils.start_workers does for PEST++, but with the
    PEST_HP commands:

        manager (in master_dir):   pest_hp case /h :port
        agent i (in worker_i):     agent_hp case /h hostname:port

    Args:
        template_dir: complete folder with the model, tpl/ins files, the control
            file and (ideally) the executables. It is copied to make the manager
            and agent folders, so it is never modified.
        pst_name: control file name inside `template_dir` (e.g. "freyberg_hp.pst").
        num_agents: number of agent_hp processes (one per physical core is a good start).
        master_dir: folder for the manager. It is DELETED and re-made from the template,
            unless `restart_flag` is given (then it is reused as it is).
        agent_root: where the "worker_i" folders are made.
        port: TCP port the manager listens on.
        pest_hp_exe / agent_exe: executable names or full paths.
        agent_takes_case: True -> "agent_hp case /h host:port"; set False if your
            agent_hp version only takes "/h host:port" (check the PEST_HP manual).
        restart_flag: None for a fresh run, or "/s" to resume an interrupted run
            in `master_dir` (PEST_HP manual, section 8). Agents need no switch.
        hostname: name/IP the agents use to reach the manager.
        cleanup: remove the agent folders when PEST_HP finishes.

    Returns the manager's exit code.
    """
    case = pst_name.replace(".pst", "")
    if not os.path.exists(os.path.join(template_dir, pst_name)):
        raise FileNotFoundError(os.path.join(template_dir, pst_name))

    def _resolve(exe, folder):
        # prefer a copy inside the folder (prep_pest_hp_bins), else the PATH
        local = find_exe(exe, folder)
        if local is not None:
            return local
        found = find_exe(exe)
        if found is None:
            raise FileNotFoundError(f"{exe} not found in {folder} or on the PATH")
        return found

    # manager folder
    if restart_flag is None:
        _copy_dir(template_dir, master_dir)
    elif not os.path.exists(master_dir):
        raise FileNotFoundError(f"cannot restart: {master_dir} does not exist")

    manager_cmd = [_resolve(pest_hp_exe, master_dir), case]
    if restart_flag is not None:
        manager_cmd.append(restart_flag)
    manager_cmd += ["/h", f":{port}"]
    print("manager:", " ".join(manager_cmd), "  in", master_dir)
    manager = sp.Popen(manager_cmd, cwd=master_dir)
    # give the manager a moment to open the port
    time.sleep(2)

    # agent folders
    agents, agent_dirs = [], []
    for i in range(num_agents):
        a_dir = os.path.join(agent_root, f"worker_{i}")
        _copy_dir(template_dir, a_dir)
        agent_cmd = [_resolve(agent_exe, a_dir)]
        if agent_takes_case:
            agent_cmd.append(case)
        agent_cmd += ["/h", f"{hostname}:{port}"]
        if i == 0:
            print("agent:  ", " ".join(agent_cmd), "  in", a_dir, f"(x{num_agents})")
        with open(os.devnull, "w") as devnull:
            agents.append(sp.Popen(agent_cmd, cwd=a_dir, stdout=devnull, stderr=devnull))
        agent_dirs.append(a_dir)

    ret = manager.wait()
    # PEST_HP tells the agents to stop when it finishes; make sure none is left
    time.sleep(2)
    for p in agents:
        if p.poll() is None:
            p.kill()
    if cleanup:
        for a_dir in agent_dirs:
            shutil.rmtree(a_dir, ignore_errors=True)
    print("PEST_HP finished with return code", ret)
    return ret


_FLOAT = r"([-+]?\d*\.?\d+(?:[eEdD][-+]?\d+)?)"


def read_ofr(ofr_file):
    """Read the objective function record file (case.ofr) written by PEST_HP.

    PEST_HP updates this table at the start of each iteration: phi (or, in
    regularization mode, the measurement and regularization phi) and the phi
    of each observation group, per iteration. It plays the role of PEST++'s
    case.iobj. The table is parsed leniently (whitespace or comma separated,
    header line starting with "iter"); an empty DataFrame is returned if no
    table is found, in which case use read_rec_phi() instead.
    """
    if not os.path.exists(ofr_file):
        print(f"{ofr_file} not found")
        return pd.DataFrame()

    def _split(line):
        return [t for t in re.split(r"[,\s]+", line.strip()) if t]

    def _is_number(t):
        try:
            float(t.replace("D", "E").replace("d", "e"))
            return True
        except ValueError:
            return False

    header, rows = None, []
    with open(ofr_file, "r", errors="ignore") as f:
        for line in f:
            tokens = _split(line)
            if not tokens:
                continue
            if header is None and tokens[0].lower().startswith("iter"):
                header = [t.lower() for t in tokens]
                continue
            if all(_is_number(t) for t in tokens):
                rows.append([float(t.replace("D", "E").replace("d", "e")) for t in tokens])
    if not rows:
        print(f"no table found in {ofr_file}; open it, or use read_rec_phi() on the .rec file")
        return pd.DataFrame()
    ncol = max(len(r) for r in rows)
    rows = [r for r in rows if len(r) == ncol]
    if header is None or len(header) != ncol:
        header = ["iteration"] + [f"col_{i}" for i in range(1, ncol)]
    df = pd.DataFrame(rows, columns=header)
    df[header[0]] = df[header[0]].astype(int)
    return df.set_index(header[0])


def read_rec_phi(rec_file):
    """Read the objective function history from a PEST/PEST_HP run record (.rec) file.

    A fallback for read_ofr(): it searches the "Starting phi ..." lines of the
    run record, whose wording can differ between PEST versions. Returns a
    DataFrame indexed by iteration with the columns that were found: "phi"
    (estimation mode), "measurement_phi" and "regularization_phi"
    (regularization mode).
    """
    patterns = {
        "phi": re.compile(r"starting phi for this iteration.*?:\s*" + _FLOAT, re.I),
        "measurement_phi": re.compile(r"starting measurement objective function.*?:\s*" + _FLOAT, re.I),
        "regularization_phi": re.compile(r"starting regulari[sz]ation objective function.*?:\s*" + _FLOAT, re.I),
    }
    iter_pat = re.compile(r"OPTIMI[SZ]ATION ITERATION NO\.\s*:\s*(\d+)", re.I)
    final_pat = re.compile(r"(?:lowest|final) phi.*?:\s*" + _FLOAT, re.I)
    rows, current, final_phi = {}, None, None
    with open(rec_file, "r", errors="ignore") as f:
        for line in f:
            m = iter_pat.search(line)
            if m:
                current = int(m.group(1))
                rows.setdefault(current, {})
                continue
            if current is not None:
                for col, pat in patterns.items():
                    m = pat.search(line)
                    if m and col not in rows[current]:
                        rows[current][col] = float(m.group(1).replace("D", "E").replace("d", "e"))
            m = final_pat.search(line)
            if m:
                final_phi = float(m.group(1).replace("D", "E").replace("d", "e"))
    df = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    df.index.name = "iteration"
    if df.empty:
        print(f"no phi history found in {rec_file}; open it and check the wording of the 'Starting phi' lines")
    if final_phi is not None:
        df.attrs["final_phi"] = final_phi
    return df


def load_results(master_dir, pst_name):
    """Load the PEST_HP results in `master_dir` into pyEMU objects.

    Returns (pst, par_df, jco): the control file with the final residuals
    (case.rei, or case.res after a NOPTMAX=0 run) attached, the estimated parameters (case.par, or None if the
    run did not get that far) and the Jacobian (case.jco, or None).
    """
    case = pst_name.replace(".pst", "")
    pst = pyemu.Pst(os.path.join(master_dir, pst_name))
    # case.rei holds the best residuals of an inversion; with NOPTMAX=0
    # PEST_HP writes only case.res
    for ext in (".rei", ".res"):
        res_file = os.path.join(master_dir, case + ext)
        if os.path.exists(res_file):
            pst.set_res(res_file)
            break
    par_file = os.path.join(master_dir, case + ".par")
    par_df = pyemu.pst_utils.read_parfile(par_file) if os.path.exists(par_file) else None
    jco_file = os.path.join(master_dir, case + ".jco")
    jco = pyemu.Jco.from_binary(jco_file) if os.path.exists(jco_file) else None
    return pst, par_df, jco
