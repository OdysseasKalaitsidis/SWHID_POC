from parser import fetch_package
import requests
import tarfile
import io
import os  
from swh.model.from_disk import Directory

def unpack_file(file_url):
    target_dir = "tmp"  
    
    os.makedirs(target_dir, exist_ok=True)

    print(f"Downloading from {file_url}...")
    resp = requests.get(file_url)
    resp.raise_for_status()

    # In memory download
    file_obj = io.BytesIO(resp.content)
    
    try:
        print(f"Unpacking to '{target_dir}/'...")
        with tarfile.open(fileobj=file_obj, mode="r:gz") as tar:
            tar.extractall(path=target_dir, filter='data')
            
        print("Files unpacked")
            
    except Exception as e:
        print(f"Error unpacking: {e}")

import os

def find_source_root(extract_path):
   
    items = os.listdir(extract_path)
    
    if len(items) == 1:
        inner_folder = os.path.join(extract_path, items[0])
        if os.path.isdir(inner_folder):
            return inner_folder
            
    return extract_path

def swhid_generator (folder_path):
    directory = Directory.from_disk(path=folder_path)
    swhid = directory.swhid()
    
    return swhid


