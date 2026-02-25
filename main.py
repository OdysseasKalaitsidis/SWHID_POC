from parser import fetch_package
from calculator import unpack_file

file_url = fetch_package("numpy", "2.2.0")
unpack_file(file_url)
