import os
import sys
import base64
import subprocess
import threading

def _send_toast_powershell(title, message):
    """
    Send a Windows desktop notification using PowerShell.
    Attempts WinRT Toast first, and supplements/falls back with System.Windows.Forms.NotifyIcon Balloon Tip.
    """
    safe_title = str(title).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "''")
    safe_msg = str(message).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "''")
    
    ps_code = f"""
    # 1. Try WinRT Toast Notification
    $toastSent = $false
    try {{
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $template = @"
<toast>
    <visual>
        <binding template="ToastGeneric">
            <text>{safe_title}</text>
            <text>{safe_msg}</text>
        </binding>
    </visual>
</toast>
"@
        $xml.LoadXml($template)
        $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe')
        $notifier.Show($toast)
        $toastSent = $true
    }} catch {{
        $toastSent = $false
    }}

    # 2. Supplementary Windows Forms Balloon Tip if WinRT was suppressed or as reliable popup
    try {{
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $notify = New-Object System.Windows.Forms.NotifyIcon
        $notify.Icon = [System.Drawing.SystemIcons]::Information
        $notify.Visible = $True
        $notify.ShowBalloonTip(4000, "{safe_title}", "{safe_msg}", [System.Windows.Forms.ToolTipIcon]::Info)
        $start = [System.DateTime]::Now
        while (([System.DateTime]::Now - $start).TotalSeconds -lt 3) {{
            [System.Windows.Forms.Application]::DoEvents()
            Start-Sleep -Milliseconds 100
        }}
        $notify.Dispose()
    }} catch {{}}
    """
    try:
        encoded = base64.b64encode(ps_code.encode('utf-16le')).decode('ascii')
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"Failed to send toast notification: {e}")

def send_notification(title, message):
    """
    Non-blocking native notification dispatcher.
    """
    threading.Thread(target=_send_toast_powershell, args=(title, message), daemon=True).start()

if __name__ == "__main__":
    send_notification("SteamManifestUpdater", "測試通知：背景守護已正常啟動！")
