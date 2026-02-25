import requests 

def fetch_package(package_name, version):

    URL = f"https://pypi.org/pypi/{package_name}/{version}/json"

    try:
        resp = requests.get(URL)
        data = resp.json()
        for file_info in data['urls']:
            if file_info['packagetype'] == 'sdist':
                print(file_info['url'])
                return (file_info['url'])
    except requests.exceptions.RequestException as e:
        print(f"Error fetching package: {e}")









