using System;
using System.IO;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("Steam Manifest Updater 2.0.2")]
[assembly: System.Reflection.AssemblyProduct("Steam Manifest Updater")]
[assembly: System.Reflection.AssemblyDescription("Steam 入庫與清單更新工具 (多源極速版)")]
[assembly: System.Reflection.AssemblyVersion("2.0.2.0")]
[assembly: System.Reflection.AssemblyFileVersion("2.0.2.0")]

namespace SteamManifestUpdaterLauncher
{
    static class Program
    {
        [DllImport("shell32.dll", SetLastError = true)]
        static extern void SetCurrentProcessExplicitAppUserModelID([MarshalAs(UnmanagedType.LPWStr)] string AppID);

        [STAThread]
        static void Main(string[] args)
        {
            try
            {
                SetCurrentProcessExplicitAppUserModelID("jiasai.steammanifestupdater.modern.v2");
            }
            catch { }

            string appDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\', '/');

            // 尋找主入口腳本
            string mainPy = Path.Combine(appDir, "src", "main.py");
            if (!File.Exists(mainPy))
            {
                mainPy = Path.Combine(appDir, "main.py");
            }

            if (!File.Exists(mainPy))
            {
                MessageBox.Show("找不到主程式入口：src\\main.py 或 main.py！\n請確認執行檔位於 SteamManifestUpdater 專案根目錄。", "啟動錯誤", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            // 智能尋找 Python (優先 pythonw 避免黑框閃退)
            string pythonExe = ResolvePython(appDir);

            if (string.IsNullOrEmpty(pythonExe) || !File.Exists(pythonExe))
            {
                MessageBox.Show("系統未檢測到 Python 環境！\n請先安裝 Python 3.8 或以上版本，或透過 AI Tool Launcher 進行環境配置。", "環境缺失", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = pythonExe;

                // 組合命令列參數
                string cmdArgs = string.Format("\"{0}\"", mainPy);
                if (args != null && args.Length > 0)
                {
                    cmdArgs += " " + string.Join(" ", args);
                }

                psi.Arguments = cmdArgs;
                psi.WorkingDirectory = appDir;
                psi.UseShellExecute = false;

                // 若使用 python.exe 則隱藏主命令提示字元黑框
                if (Path.GetFileNameWithoutExtension(pythonExe).ToLower() == "python")
                {
                    psi.CreateNoWindow = true;
                }

                Process.Start(psi);
            }
            catch (Exception ex)
            {
                MessageBox.Show("啟動 SteamManifestUpdater 失敗：\n" + ex.Message, "錯誤", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private static string ResolvePython(string appDir)
        {
            // 1. 本地獨立虛擬環境 .venv
            string venvPyw = Path.Combine(appDir, ".venv", "Scripts", "pythonw.exe");
            if (File.Exists(venvPyw)) return venvPyw;
            string venvPy = Path.Combine(appDir, ".venv", "Scripts", "python.exe");
            if (File.Exists(venvPy)) return venvPy;

            // 2. 優先透過 where 指令查詢 PATH 中的 python (與使用者 terminal / pip 依賴環境 100% 同步)
            string wherePy = SearchCommand("where", "python");
            if (!string.IsNullOrEmpty(wherePy) && File.Exists(wherePy))
            {
                string pyDir = Path.GetDirectoryName(wherePy);
                string companionPyw = Path.Combine(pyDir, "pythonw.exe");
                if (File.Exists(companionPyw)) return companionPyw;
                return wherePy;
            }

            string wherePyw = SearchCommand("where", "pythonw");
            if (!string.IsNullOrEmpty(wherePyw) && File.Exists(wherePyw)) return wherePyw;

            // 3. 常見使用者層級與系統層級 Python 安裝路徑後備
            string localApp = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string[] userPyPaths = {
                @"C:\Program Files\Python311\pythonw.exe",
                @"C:\Program Files\Python311\python.exe",
                Path.Combine(localApp, "Programs", "Python", "Python311", "pythonw.exe"),
                Path.Combine(localApp, "Programs", "Python", "Python311", "python.exe"),
                @"C:\Program Files\Python312\pythonw.exe",
                @"C:\Program Files\Python312\python.exe",
                Path.Combine(localApp, "Programs", "Python", "Python312", "pythonw.exe"),
                Path.Combine(localApp, "Programs", "Python", "Python312", "python.exe"),
                Path.Combine(localApp, "Programs", "Python", "Python310", "pythonw.exe"),
                Path.Combine(localApp, "Programs", "Python", "Python310", "python.exe")
            };

            foreach (string p in userPyPaths)
            {
                if (File.Exists(p)) return p;
            }

            return null;
        }

        private static string SearchCommand(string cmd, string arg)
        {
            try
            {
                Process p = new Process();
                p.StartInfo.FileName = cmd;
                p.StartInfo.Arguments = arg;
                p.StartInfo.UseShellExecute = false;
                p.StartInfo.RedirectStandardOutput = true;
                p.StartInfo.CreateNoWindow = true;
                p.Start();
                string output = p.StandardOutput.ReadLine();
                p.WaitForExit(2000);
                if (!string.IsNullOrEmpty(output)) return output.Trim();
            }
            catch { }
            return null;
        }
    }
}
