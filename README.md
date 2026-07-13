# YouTube Analytics 自動報表（半盞江湖）

每天台灣時間凌晨 03:30，自動讀取「半盞江湖 Half Cup of Jianghu」前一天的 YouTube Studio 私人數據，產生：

- `reports/YYYY-MM-DD.md`：容易閱讀的每日報表
- `data/history.csv`：可用 Excel 開啟的歷史資料

目前只支援一個頻道，不含 OpenAI API 或 AI 分析。OAuth JSON、密碼與 token 都不會寫入 repository。

## 會取得哪些資料

前一天：觀看次數、觀看分鐘、平均觀看時間、新增／取消訂閱、喜歡、留言、分享，以及觀看最高的 5 支影片。另會保存目前訂閱總數、累積觀看總數及影片總數。

## 第一步：安裝 Python 3.12

1. 前往 [Python 官方下載頁](https://www.python.org/downloads/)下載 Python 3.12。
2. 執行安裝程式時，先勾選 **Add python.exe to PATH**，再按 **Install Now**。
3. 開啟 Windows PowerShell，輸入 `python --version`，應看到 `Python 3.12.x`。

## 第二步：下載 repository

1. 開啟本 repository，按綠色 **Code** → **Download ZIP**。
2. 解壓縮後進入資料夾。
3. 在資料夾空白處按住 Shift 再按滑鼠右鍵，選擇「在終端機中開啟」。
4. 依序執行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

若 PowerShell 阻止啟用，可先執行 `Set-ExecutionPolicy -Scope Process Bypass`，再執行啟用指令。

## 第三步：設定 Google Cloud

1. 開啟 [Google Cloud Console](https://console.cloud.google.com/)並選擇原本建立的專案。
2. 進入「API 和服務」→「程式庫」，分別搜尋並啟用：
   - **YouTube Data API v3**
   - **YouTube Analytics API**
3. 進入「Google Auth Platform」設定應用程式名稱與聯絡信箱。
4. Audience（目標對象）使用 **External**。若應用程式仍在 Testing，將自己的 Google 帳號加入 **Test users**。
5. 進入「Clients」→「Create client」→ 類型選 **Desktop app**。
6. 建立後複製畫面上的 **Client ID** 與 **Client secret**。不要把它們貼到聊天、程式檔或 GitHub。

本專案不需要下載 OAuth JSON；若已下載，也不得放進 repository。

## 第四步：執行 authorize.py

在剛才的 PowerShell 視窗設定暫時環境變數（只在該視窗有效）：

```powershell
$env:GOOGLE_CLIENT_ID="你的 Client ID"
$env:GOOGLE_CLIENT_SECRET="你的 Client secret"
python authorize.py
```

瀏覽器開啟後：

1. 登入擁有半盞江湖的 Google 帳號。
2. 若 Google 顯示品牌頻道選擇，選「半盞江湖 Half Cup of Jianghu」。
3. 同意唯讀權限。
4. 回到 PowerShell，確認顯示的頻道名稱及 ID，輸入大寫 `YES`。
5. 畫面會顯示 `GOOGLE_REFRESH_TOKEN` 及 `YOUTUBE_CHANNEL_ID`。只把它們存入 GitHub Secrets。

如果選錯頻道，程式不會接受確認；重新執行即可。`authorize.py` 不會把 token 寫入檔案。

## 第五步：新增 GitHub Actions Secrets

進入 repository 的 **Settings** → **Secrets and variables** → **Actions** → **New repository secret**，逐一新增：

| Secret 名稱 | 值 |
|---|---|
| `GOOGLE_CLIENT_ID` | Desktop App 的 Client ID |
| `GOOGLE_CLIENT_SECRET` | Desktop App 的 Client secret |
| `GOOGLE_REFRESH_TOKEN` | `authorize.py` 顯示的 refresh token |
| `YOUTUBE_CHANNEL_ID` | `authorize.py` 確認後顯示的半盞江湖頻道 ID |

Secret 儲存後無法再次查看明文，這是正常的。絕對不要將值寫進 `.env` 後提交，也不要放在 Issue、聊天或 Actions log。

## 第六步：手動測試 GitHub Actions

1. 開啟 repository 上方 **Actions**。
2. 左側選擇 **YouTube daily report**。
3. 按 **Run workflow** → 綠色 **Run workflow**。
4. 等待執行完成並出現綠色勾勾。
5. 回到 repository，確認出現 `reports/日期.md` 及 `data/history.csv`。

之後系統會每天台灣時間 03:30 自動執行。GitHub 排程可能因平台忙碌延後數分鐘。相同日期再次執行時，CSV 會更新該列，不會新增重複日期。

## 本機測試（不呼叫 Google API）

```powershell
pytest -q
```

## 常見錯誤

- **OAuth 授權失敗／瀏覽器未開啟**：確認 Python 防火牆權限，並重新執行；不要關閉等待授權的 PowerShell。
- **選錯品牌頻道**：不要輸入 `YES`，重新執行並選半盞江湖。每日程式也會核對 `YOUTUBE_CHANNEL_ID`，不符就停止。
- **API has not been used / accessNotConfigured**：回 Google Cloud 啟用兩個 API，等待數分鐘後重試。
- **invalid_grant / refresh token 無效**：重新執行 `authorize.py`，並更新 `GOOGLE_REFRESH_TOKEN` Secret。
- **403 access_denied**：確認 OAuth 測試使用者含目前登入信箱，且授權了兩個唯讀 scope。
- **當日無資料**：新資料可能尚未處理完成；程式仍會產生 0 值報表，隔天或手動重跑可更新同一日期。
- **選對帳號仍是錯誤頻道**：到 Google 帳號的第三方存取權撤銷此 OAuth 應用程式，再執行 `authorize.py` 重新選品牌頻道。

## 安全原則

- OAuth 權限均為唯讀。
- `.gitignore` 排除常見憑證檔、`.env` 與 token 檔。
- GitHub Actions 只從 Secrets 注入敏感值。
- 請勿將任何秘密貼到聊天中。
