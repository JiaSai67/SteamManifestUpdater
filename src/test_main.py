import sys, os
import tempfile
with open(os.path.join(tempfile.gettempdir(), "nuitka_main.txt"), "w") as log:
    log.write(f"__file__: {__file__}\n")
