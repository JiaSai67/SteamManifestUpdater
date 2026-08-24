import os

conv_dir = r'C:\Users\chuan\.gemini\antigravity-ide\conversations'
brain_dir = r'C:\Users\chuan\.gemini\antigravity-ide\brain'

found = []
for f in os.listdir(conv_dir):
    if f.endswith('.db'):
        path = os.path.join(conv_dir, f)
        try:
            with open(path, 'rb') as file:
                content = file.read()
                # Find occurrences of SteamManifestUpdater
                if b'SteamManifest' in content or b'steam_manifest' in content or b'onlinefix' in content:
                    found.append(f.replace('.db', ''))
        except:
            pass

for cid in found:
    log_file = os.path.join(brain_dir, cid, ".system_generated", "logs", "transcript.jsonl")
    if os.path.exists(log_file):
        print(f"--- Conversation {cid} ---")
        try:
            import json
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        step = json.loads(line)
                        if step.get("type") == "USER_INPUT":
                            print(f"USER: {step.get('content', '')}")
                    except:
                        pass
        except:
            pass
        print("\n")
