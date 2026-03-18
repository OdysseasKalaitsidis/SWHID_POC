import json
import requests
import tarfile
import zipfile
import io
import os
import shutil
from swh.model.from_disk import Directory

CARGO_INJECTED = [".cargo_vcs_info.json", "Cargo.toml", "Cargo.toml.orig"]

def unpack_file(file_url):
    target_dir = "tmp"

    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(target_dir)

    print(f"Downloading from {file_url}...")
    resp = requests.get(file_url)
    resp.raise_for_status()

    # In memory download
    file_obj = io.BytesIO(resp.content)
    
    print(f"Unpacking to '{target_dir}/'...")
    with tarfile.open(fileobj=file_obj, mode="r:gz") as tar:
        tar.extractall(path=target_dir, filter='data')

    return target_dir


def unpack_wheel(file_url, wheel_filename):
    target_dir = os.path.join("tmp", wheel_filename[:-4])  # strip .whl

    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(target_dir)

    print(f"Downloading {wheel_filename}...")
    resp = requests.get(file_url)
    resp.raise_for_status()

    print(f"Unpacking to 'tmp/{wheel_filename[:-4]}/'...")
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(path=target_dir)

    return target_dir


def unpack_crate(file_url, name, version):
    target_dir = "tmp"

    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(target_dir)

    print(f"Downloading from {file_url}...")
    resp = requests.get(file_url)
    resp.raise_for_status()

    print(f"Unpacking to '{target_dir}/'...")
    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        tar.extractall(path=target_dir, filter='data')

    source_path = find_source(target_dir)

    # Read injected files before any stripping
    injected = {}
    for filename in CARGO_INJECTED:
        full = os.path.join(source_path, filename)
        if os.path.exists(full):
            with open(full, "r", encoding="utf-8") as f:
                injected[filename] = f.read()

    return source_path, injected


def strip_cargo_injected_files(source_path):
    removed = []
    for filename in CARGO_INJECTED:
        full = os.path.join(source_path, filename)
        if os.path.exists(full):
            os.remove(full)
            removed.append(filename)
    return removed


def find_source(extract_path):
   
    items = os.listdir(extract_path)
    
    if len(items) == 1:
        inner_folder = os.path.join(extract_path, items[0])
        if os.path.isdir(inner_folder):
            return inner_folder
            
    return extract_path

def swhid_generator(folder_path):
    directory = Directory.from_disk(path=os.fsencode(folder_path), max_content_length=None)
    swhid = directory.swhid()

    return swhid


