# Steam Manifest Updater 2.0 (多源極速版)

🌸 **全新櫻花流光現代化無邊框架構** — 專為 Steam Manifest 清單更新、多源入庫 (Ryuu + Lua.tools) 與 Online-Fix / ZeiGames 補丁無縫安裝而打造。

---

## ✨ 核心特性

- **極速流光 Webview 架構**：基於 Windows 內建 Edge WebView2 核心，記憶體佔用極低、秒開無延遲，徹底告別龐大易衝突的 Qt (PySide6) 庫。
- **多源 Manifest 自動解析與入庫**：支援 Ryuu、Lua.tools、Assiw 多源備援，即時取得最新 Depot 與 Manifest ID。
- **Steam 原生實時下載狀態追蹤**：底層二進位日誌倒讀與多庫狀態機，精準捕獲 Steam 實時下載進度與解壓狀態。
- **Online-Fix 一鍵安裝與自動備份**：安裝補丁時自動建立被覆蓋檔案之 `.bak` 備份，並支援多層目錄全樹一鍵還原。
- **Google Drive 防限流快取**：內建 30 秒記憶體 TTL 快取，0.0000 ms 秒開並 100% 杜絕 Google 429 請求過頻。
- **智慧多硬碟庫自動識別**：全自動解析 Windows 註冊表與 Steam 多磁碟庫（`libraryfolders.vdf`），無須任何手動寫死路徑。

---

## 🚀 快速啟動

```bash
# 1. 安裝輕量依賴 (僅需 pywebview, requests, gdown)
pip install -r requirements.txt

# 2. 啟動主程式
python src/main.py
```

若需建立隔離環境以避免與系統全域套件衝突（推薦）：
```bash
# 建立並啟用虛擬環境
python -m venv .venv
.venv\Scripts\activate

# 安裝依賴並運行
pip install -r requirements.txt
python src/main.py
```

---

## 📁 專案目錄結構

```text
SteamManifestUpdater/
├── src/                        # 2.0 核心代碼庫 (僅 3.14 MB)
│   ├── gui/                    # 櫻花流光 HTML5 / CSS3 / JS 前端介面
│   ├── managers/               # 下載追蹤、Steam 互動、補丁與設定管理核心
│   ├── web_api.py              # 前後端高效能雙向 Bridge
│   └── main.py                 # 2.0 程式主入口
├── data/                       # 本地配置與快取存儲
├── dlls/                       # 補丁依賴與解壓組件
├── opensteamtools/             # 開源輔助套件
├── assets/                     # 靜態圖示與流光背景
├── requirements.txt            # 2.0 純淨輕量依賴清單
└── README.md                   # 本說明文件
```

---

## 📦 依賴需求

- **作業系統**：Windows 10 / 11 (內建 Microsoft Edge WebView2 Runtime)
- **Python**：Python 3.8 ~ 3.12
- **依賴套件**：詳見 [`requirements.txt`](requirements.txt)（極簡 3 個套件：`pywebview`, `requests`, `gdown`）
