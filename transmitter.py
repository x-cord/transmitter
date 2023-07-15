import subprocess
import hashlib
import shutil
import random
import string
import glob
import time
import sys
import os

import xml.etree.ElementTree as ET
from natsort import natsorted

accounts = {
    "main": ["--nzb-poster", "user@fake.com", "--user", "abcdef", "--password", "0123456789", "--host", "news.provider.com", "--ssl", "--from", "${rand(20)}@${rand(20)}.${rand(3)}", "--subject", "${rand(20)}", "--filename", "${rand(20)}", "--connections", "90", "--check-connections", "8", "--groups", "alt.binaries.boneless"],
}

locations = [
    "/mnt/abcd/abs-path-to-dir/with/glob/*",
]

tmp_dir = "/tmp/transmitter"
staging_dir = "/home/user/transmitter/staging"
failed_dir = "/home/user/transmitter/failed"
out_dir = "/home/user/transmitter/out"

parpar_path = ["node", "ParPar/bin/parpar.js"]
nyuu_path = ["node", "Nyuu/bin/nyuu.js"]

# 200GiB
split_size = 200 * 1024 * 1024 * 1024
# 10GiB
last_slack = 10 * 1024 * 1024 * 1024

min_size = 1

def transmitter_path(path):
    return path.replace("/mnt/abcd/abs-path-to-dir/with/glob/", "")

def get_chunks(path, split_size):
    if os.path.isfile(path):
        return [[path]], os.path.getsize(path), True

    total = 0
    cur = 0
    chunks = []
    chunk = []

    files = glob.glob("**", root_dir=path, recursive=True, include_hidden=True)
    for file in natsorted(files):
        if file.endswith(".lwi") or file.endswith(".ffindex"):
            continue
        file_path = f"{path}/{file}"
        if not os.path.isfile(file_path):
            continue
        cur += os.path.getsize(file_path)
        if cur > split_size and chunk:
            total += cur
            cur = 0
            chunks.append(chunk)
            chunk = []
        chunk.append(file_path)
    if chunk:
        total += cur
        chunks.append(chunk)

    if len(chunks) > 1 and cur <= last_slack:
        chunks[-2].extend(chunks[-1])
        del chunks[-1]

    return chunks, total, False

def check_nzb(path):
    tree = ET.parse(path)
    segments = tree.findall("./{http://www.newzbin.com/DTD/2003/nzb}file/{http://www.newzbin.com/DTD/2003/nzb}segments")
    return segments and 0 not in [len(segment) for segment in segments]

def rm_file(path):
    try:
        os.remove(path)
    except OSError:
        pass

os.makedirs(f"{staging_dir}/par", exist_ok=True)
os.makedirs(f"{staging_dir}/nzb", exist_ok=True)
os.makedirs(tmp_dir, exist_ok=True)

for location in locations:
    for unit in glob.iglob(location):
        chunks, total_size, is_file = get_chunks(unit, split_size)

        if total_size < min_size:
            continue

        unit_name = unit.split("/")[-1]
        chunk_count = len(chunks)
        t_path = transmitter_path(unit)
        t_hash = hashlib.sha1(unit.encode()).hexdigest()

        for chunk_n, chunk in enumerate(chunks, 1):
            chunk_id = f"{t_hash}-{chunk_n}"
            t_part = "" if chunk_count <= 1 else f".part{chunk_n:04d}"

            new_par = False
            par_files = glob.glob(f"{tmp_dir}/{chunk_id}/*.par2")
            if not par_files:
                par_files = glob.glob(f"{staging_dir}/par/{chunk_id}/*.par2")

            # generate par files
            if not par_files:
                has_nzb = False
                missing_nzb = False
                for account_id, account in accounts.items():
                    staging_nzb = glob.glob(f"{staging_dir}/nzb/{chunk_id}-{account_id}.nzb*")
                    out_nzb = os.path.isfile(f"{out_dir}/{account_id}/{t_path}{t_part}.nzb")
                    has_nzb = has_nzb or staging_nzb or out_nzb
                    missing_nzb = missing_nzb or not out_nzb
                if not missing_nzb:
                    failed_articles = [item for item in glob.glob(f"{failed_dir}/{chunk_id}/{account_id}/*") for account_id in accounts.keys()]
                    if not failed_articles:
                        print(f"skip {chunk_n}/{chunk_count} {unit}")
                        continue
                with open(f"{tmp_dir}/chunk.txt", "w") as f:
                    f.write("\0".join(chunk))
                if not has_nzb:
                    print(f"par2 {chunk_n}/{chunk_count} {unit}")
                    shutil.rmtree(f"{tmp_dir}/{chunk_id}", ignore_errors=True)
                    shutil.rmtree(f"{tmp_dir}/{chunk_id}-tmp", ignore_errors=True)
                    os.makedirs(f"{tmp_dir}/{chunk_id}-tmp", exist_ok=True)
                    shutil.rmtree(f"{failed_dir}/{chunk_id}", ignore_errors=True)
                    p = subprocess.run(parpar_path + ["-s5600K", "--threads", "4", "--slice-size-multiple=700K", "--auto-slice-size", "-r1n*1.2", "--noindex"] + ([] if is_file else ["--filepath-format", "path", "--filepath-base", unit]) + ["--quiet", "--progress", "stderr", "--out", f"{tmp_dir}/{chunk_id}-tmp/{unit_name}{t_part}", "--input-file0", f"{tmp_dir}/chunk.txt"])
                    if p.returncode != 0:
                        print(f"!parpar fail {chunk_n}/{chunk_count} {unit}")
                        shutil.rmtree(f"{tmp_dir}/{chunk_id}-tmp", ignore_errors=True)
                        continue
                    shutil.move(f"{tmp_dir}/{chunk_id}-tmp", f"{tmp_dir}/{chunk_id}")
                par_files = glob.glob(f"{tmp_dir}/{chunk_id}/*.par2")
                if not par_files:
                    print(f"!no par2 {chunk_n}/{chunk_count} {unit}")
                new_par = True
            else:
                with open(f"{tmp_dir}/chunk.txt", "w") as f:
                    f.write("\0".join(chunk))

            with open(f"{tmp_dir}/par.txt", "w") as f:
                f.write("\0".join(par_files))

            # upload articles
            processes = []
            for account_id, account in accounts.items():
                failed_articles = []
                if not new_par:
                    failed_articles = glob.glob(f"{failed_dir}/{chunk_id}/{account_id}/*")
                    if not failed_articles and not glob.glob(f"{staging_dir}/nzb/{chunk_id}-{account_id}.nzb.*.fail"):
                        continue
                os.makedirs(f"{failed_dir}/{chunk_id}/{account_id}", exist_ok=True)
                nyuu_command = nyuu_path + account + ["--group-files", "--skip-errors", "post-timeout,check-timeout,check-missing", "--on-post-timeout", "retry,ignore", "--check-tries", "4", "--check-post-tries", "2", "--check-delay", "2s", "--log-time", "--quiet", "--progress", "stderr", "--disk-req-size", "28000K", "--post-queue-size", "16", "--request-retries", "8", "--nzb-subject", "[{0filenum}/{files}] - \"{filebase}\" yEnc ({part}/{parts}) {filesize}", "--meta", f"title: {unit_name}", "--meta", f"path: {t_path}", "--overwrite", "--out", f"{staging_dir}/nzb/{chunk_id}-{account_id}.nzb"]
                if failed_articles:
                    print(f"resume #{account_id} {chunk_n}/{chunk_count} {unit}")
                    nyuu_command.extend(["--input-raw-posts", "--delete-raw-posts"] + failed_articles)
                else:
                    print(f"upload #{account_id} {chunk_n}/{chunk_count} {unit}")
                    nyuu_command.extend(["--dump-failed-posts", f"{failed_dir}/{chunk_id}/{account_id}", "--input-file0", f"{tmp_dir}/chunk.txt", "--input-file0", f"{tmp_dir}/par.txt"])
                nyuu = subprocess.Popen(nyuu_command)
                processes.append(nyuu)

            # nothing to post
            if not processes:
                shutil.rmtree(f"{failed_dir}/{chunk_id}", ignore_errors=True)
                shutil.rmtree(f"{staging_dir}/par/{chunk_id}", ignore_errors=True)
                continue

            for process in processes:
                process.wait()

            # nyuu doesn't generate a newline on exit when displaying progress
            print()

            t_time = int(time.time())
            aborted_upload = False

            # move nzbs to final destination if no empty segments, check for nzb errors
            for account_id, account in accounts.items():
                if not os.path.isfile(f"{staging_dir}/nzb/{chunk_id}-{account_id}.nzb"):
                    print(f"!nzb skip #{account_id} {chunk_n}/{chunk_count} {unit}")
                    continue
                if not check_nzb(f"{staging_dir}/nzb/{chunk_id}-{account_id}.nzb"):
                    print(f"!error #{account_id} {chunk_n}/{chunk_count} {unit}")
                    shutil.move(f"{staging_dir}/nzb/{chunk_id}-{account_id}.nzb", f"{staging_dir}/nzb/{chunk_id}-{account_id}.nzb.{t_time}.fail")
                    shutil.move(f"{failed_dir}/{chunk_id}/{account_id}", f"{failed_dir}/{chunk_id}/{account_id}.{t_time}.fail")
                    aborted_upload = True
                    continue
                d_path = "/".join(t_path.split("/")[:-1])
                os.makedirs(f"{out_dir}/{account_id}/{d_path}", exist_ok=True)
                shutil.move(f"{staging_dir}/nzb/{chunk_id}-{account_id}.nzb", f"{out_dir}/{account_id}/{t_path}{t_part}.nzb")

            failed_articles = [item for item in glob.glob(f"{failed_dir}/{chunk_id}/{account_id}/*") for account_id in accounts.keys()]

            # delete par2 files if no failed articles, otherwise move to staging area
            if not failed_articles and not aborted_upload:
                shutil.rmtree(f"{failed_dir}/{chunk_id}", ignore_errors=True)
                if new_par:
                    shutil.rmtree(f"{tmp_dir}/{chunk_id}", ignore_errors=True)
                else:
                    shutil.rmtree(f"{staging_dir}/par/{chunk_id}", ignore_errors=True)
                with open("processed.txt", "a") as f:
                    f.write("\n".join(chunk) + "\n")
            elif new_par:
                shutil.move(f"{tmp_dir}/{chunk_id}", f"{staging_dir}/par/{chunk_id}")
