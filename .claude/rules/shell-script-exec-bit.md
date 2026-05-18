---
paths:
  - "**/*.sh"
  - "**/scripts/**"
---

# Shell Script Exec Bit（Windows ↔ Linux）

Windows filesystem 無 POSIX exec bit，git 預設以 `100644` 記錄；Linux 端拉下後 `./xxx.sh` 觸發 `Permission denied` 或 `No such file or directory`。CLAUDE.md 強制規範 #22.d 已列為總則，本規則為 `*.sh` 編輯時的就近提示與具體指令。

## 操作流程

1. 完成 `Write` / `Edit` 任何 `*.sh` 檔之後**立即**執行（在主對話 Bash，不在腳本內）：

   ```bash
   git update-index --chmod=+x <path/to/script.sh>
   ```

2. 驗證 git index mode：

   ```bash
   git ls-files --stage <path/to/script.sh>
   # 預期第一欄 100755（不是 100644）
   ```

3. 若 commit 後才發現 mode 錯，補一個獨立 chmod commit：

   ```bash
   git update-index --chmod=+x <file>
   git commit -m "chore(scripts): mark <file> executable in git"
   ```

## 反模式（不可替代）

- ❌ **靠 Dockerfile `COPY --chmod=755` 補救**：那只影響 container 內 mode，git index 仍是 100644，使用者直接 clone repo 後 `./script.sh` 仍會 fail。
- ❌ **靠 Linux 端 `chmod +x` 之後 commit**：Windows 端 clone 後再 commit 又會被改回 100644，無止盡循環。
- ❌ **靠 README 寫「請先 `chmod +x`」**：把責任丟給使用者，違反 CLAUDE.md #23（交付指令不寫 placeholder）。

正解只有一個：`git update-index --chmod=+x` 直接寫入 git index，跨平台一致。

## 過往實例（避免重蹈）

| 檔案 | Commit | 情境 |
|------|--------|------|
| `backend/scripts/smoke_asr.sh` | `c137f9e` | 2026-05-18 A-1 揭發：第一次 commit 為 100644，Linux 端使用者跑 `./scripts/smoke_asr.sh` 直接 `No such file or directory`；補一個獨立 chmod commit 修正 |
| `backend/scripts/entrypoint.sh` | `a8f42bd` | 2026-05-19 OPT-06：一次到位 100755，commit 訊息列出 `create mode 100755`，使用者直接 `git pull` + `docker compose up -d --force-recreate` 即可運作 |

相關：[CLAUDE.md 強制規範 #22](../../CLAUDE.md) 交付與驗證四步驗證 / `MEMORY.md` 歷史條目 `feedback_verify_actual_deliverable`（已 promote）。
