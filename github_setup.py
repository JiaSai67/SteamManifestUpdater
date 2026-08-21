import sys
import json
import urllib.request
import os
import subprocess
import shutil

TOKEN = sys.argv[1]
REPO_NAME = "SteamManifestUpdater"

def request_github(method, url, data=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    if data:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(data).encode("utf-8")
    
    try:
        with urllib.request.urlopen(req, data=data) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}: {e.read().decode()}")
        sys.exit(1)

# 1. Get Username
print("Fetching username...")
user_data = request_github("GET", "https://api.github.com/user")
username = user_data["login"]
print(f"Logged in as: {username}")

# 2. Create Repository
print(f"Creating repository {REPO_NAME}...")
try:
    repo_data = request_github("POST", "https://api.github.com/user/repos", {
        "name": REPO_NAME,
        "description": "Steam Manifest Updater - Auto uploaded version",
        "private": False
    })
    print(f"Repository created: {repo_data['html_url']}")
except SystemExit:
    print("Repository might already exist, continuing...")

# 3. Git Init and Push
print("Pushing source code to GitHub...")
os.system("git init")
os.system("git add .")
os.system('git commit -m "Initial commit"')
os.system(f"git branch -M main")
# Overwrite remote if exists
os.system(f"git remote remove origin")
os.system(f"git remote add origin https://{username}:{TOKEN}@github.com/{username}/{REPO_NAME}.git")
os.system("git push -u origin main --force")

print("\n--- Setup Complete! ---")
print(f"Your source code is live at: https://github.com/{username}/{REPO_NAME}")
