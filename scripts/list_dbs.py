import os, sqlite3

conv_dir = r'C:\Users\chuan\.gemini\antigravity-ide\conversations'
found = []
for f in os.listdir(conv_dir):
    if f.endswith('.db'):
        path = os.path.join(conv_dir, f)
        mtime = os.path.getmtime(path)
        found.append((mtime, path))

found.sort() # Oldest first

for mtime, path in found:
    print(f"{os.path.basename(path)} - {mtime}")
