import os
import sys
import time
import subprocess
import winreg
from pathlib import Path

# Locate root directory
if getattr(sys, 'frozen', False) or "__compiled__" in globals():
    ROOT_DIR = Path(sys.argv[0]).resolve().parent
else:
    ROOT_DIR = Path(__file__).resolve().parent.parent.parent

DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = DATA_DIR / "daemon.pid"

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_NAME = "SteamManifestDaemon"

def get_daemon_cmd():
    """
    Get the command line string used to launch the background daemon without a console window.
    """
    if getattr(sys, 'frozen', False):
        exe_path = Path(sys.executable).resolve()
        return f'"{exe_path}" --daemon'
    else:
        # Locate pythonw.exe in the same directory as python.exe
        python_dir = Path(sys.executable).parent
        pythonw = python_dir / "pythonw.exe"
        if not pythonw.exists():
            pythonw = Path(sys.executable)
            
        daemon_script = ROOT_DIR / "src" / "daemon.py"
        return f'"{pythonw}" "{daemon_script}"'

def is_autostart_enabled():
    """
    Check if daemon is configured to start with Windows.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, REG_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception:
        return False

def set_autostart(enabled=True):
    """
    Enable or disable autostart in Windows Registry.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                cmd = get_daemon_cmd()
                winreg.SetValueEx(key, REG_NAME, 0, winreg.REG_SZ, cmd)
                return True
            else:
                try:
                    winreg.DeleteValue(key, REG_NAME)
                except FileNotFoundError:
                    pass
                return True
    except Exception as e:
        print(f"Error updating autostart: {e}")
        return False

def is_process_running(pid):
    """
    Check if a process with the given PID is currently active.
    """
    if not pid or pid <= 0:
        return False
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return exit_code.value == STILL_ACTIVE
    except Exception:
        pass
    return False

def get_daemon_pid():
    """
    Read the PID file and return PID if daemon is currently running, else None.
    """
    if PID_FILE.exists():
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                pid_str = f.read().strip()
                if pid_str.isdigit():
                    pid = int(pid_str)
                    if is_process_running(pid):
                        return pid
        except Exception:
            pass
    return None

def is_daemon_running():
    """
    Return True if the background daemon is currently running.
    """
    return get_daemon_pid() is not None

def start_daemon():
    """
    Launch the background daemon process (Paused due to Valve CDN manifest changes).
    """
    return False, "背景守護程式因 Valve 伺服端清單政策調整已暫停使用"

def stop_daemon():
    """
    Stop the background daemon process.
    """
    pid = get_daemon_pid()
    if not pid:
        if PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except:
                pass
        return True, "背景守護程式未運行"
        
    try:
        subprocess.call(
            ["taskkill", "/F", "/PID", str(pid)],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        time.sleep(0.3)
        if PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except:
                pass
        return True, "背景守護程式已停止"
    except Exception as e:
        return False, f"停止失敗: {e}"
