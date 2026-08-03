# 115分科分發 落點試算 — 專案說明（給 Claude Code）

## 專案目標
把 site/index.html（已完成的單檔落點試算網頁）升級為正式網站＋PWA，
部署到 GitHub Pages，供家人手機「加入主畫面」當 App 使用。

## 版本鐵則（最優先）
- **公開部署一律使用通用版**：site/index.html（預設空白、含輸入引導）即為通用版，直接部署此檔。
- site/index_personal.html 為個人版（內含使用者實際學測成績預設值），僅供本機/私人使用，**嚴禁**部署到公開網址或提交到公開 repo（部署前將其加入 .gitignore 或刪除）。

## 目前結構
- site/index.html：通用版單檔網頁（公開部署用）
- site/index_personal.html：個人版（含個人成績預設，勿公開）（內嵌 1,764 系組資料，資料已三重核實（含210系組學測五標檢定與20系組英聽檢定自動判定；預設為使用者實際學測成績，分科為預估值），勿改動計算邏輯與資料值）
- data/data.json：同一份資料的獨立 JSON（527KB）
- tools/：資料產生管線（116學年度更新時使用）
  - parse_115_recruit.py：解析分發簡章校系分則（pdfplumber，字元座標法；來源PDF路徑需自行調整）
  - parse_history_results.py：解析考分會歷年最低錄取標準，讀取 tools/112~115 四個年度資料夾，輸出統一格式 hist.json
  - parse_accu.py：解析 tools/年度/accu-年度.xls（採計組合成績人數累計表），建立「組合代碼 → 科目集合 → 分數區間人數累計」查詢資料庫，供加權皆1.00之系組計算官方精確排名／PR
  - make_data.py：由 r115.json + hist.json + accu資料庫 合併輸出前端用 data.json
  - build_excel.py：產出 Excel 個人版
  - build_excel_universal.py：產出 Excel 通用版（對外分享用）
  - r115.json / hist.json：本年度已核實之中繼資料
  - tools/112、tools/113、tools/114：各年度原始資料夾。各含 21~26 系列 xls（原得總分與級分對照表、各科級分人數百分比累計表/分布圖、各科成績標準一覽表）、accu-年度.xls（採計組合成績人數累計表）、count-年度.xlsx（回流後分發入學總名額表）。**不含**該年度「各系組最低錄取分」原始榜單檔——此資料已於既有 hist.json 中（來源為先前處理的逐頁 PDF/txt，該來源檔已不在資料夾內，如需重新核實請另行取得）
  - tools/115：115學年度資料夾。同樣含 21~26 系列 xls（含各科成績標準一覽表五標）、accu-115.xls、count-115.xlsx，另有 115學年度分科測驗成績相關統計資料_20250803.pdf。**不含**「最低錄取分」（115尚未分發放榜，屬預期狀況），故 115 年僅能提供官方組合排名法（combo_rank/combo_total/combo_pr），無法提供 115 年「最低錄取分」數值

## 待辦（依序執行，每項完成後停下讓使用者確認）

### 已完成
1. ~~將 index.html 拆為 index.html + app.js + style.css + data/data.json（改為 fetch 載入），功能與畫面不變~~ ✅
2. ~~加入 PWA：manifest.json（名稱「115分科落點試算」、theme_color #16243A、lang zh-Hant）、service worker（cache-first，快取全部靜態資源與 data.json，支援完全離線）、產生 192/512 icon~~ ✅
3. ~~初始化 git、建立 GitHub repo、部署 GitHub Pages~~ ✅（https://mk100-mk.github.io/115-luodian/）
4. ~~驗收：PWA 可安裝、離線可用、手機加入主畫面測試清單~~ ✅

### 進行中（官方組合排名法整合，2026-08 更新）
5. 確認 tools/112、113、114、115 四個年度資料夾內檔案清單
6. 重寫 tools/parse_history_results.py：讀取112-115四年榜單資料，輸出統一格式 hist.json（含每年每系組採計科目、加權、最低錄取分、錄取人數）
7. 新增 tools/parse_accu.py：解析 accu 系列檔案，建立「組合代碼→科目集合→分數區間人數累計」查詢資料庫，供加權皆1.00系組計算全國精確排名／PR
8. 更新 make_data.py：整合 r115.json + hist.json + accu資料庫，輸出新版 data.json，每系組新增 112/113/114/115四年最低錄取分、combo_rank/combo_total/combo_pr（若有官方組合排名可查）、seat_change（115回流後名額 vs 114名額）、same_as_prev（採計科目是否與前一年不同）欄位
9. 更新 site/index.html（通用版）與 index_personal.html（個人版）：落點評估優先使用官方組合排名（若有），其餘維持114年比較邏輯並標示資料來源；新增「115名額變化」與「採計是否變動」視覺提示；四年歷史分數（112/113/114/115）改為可展開查看
10. 更新 index_personal.html 預設成績為 8/3 公告之實際成績（學測 國56/英40/數A45/數B47/社53/英聽B；分科 數甲33/數乙50/歷56/地58/公52）
11. 驗證：與使用者已核實之關鍵系組（台大歷史、政大歷史等）數值比對一致後，才進行部署

## 鐵則
- 資料值（採計科目、加權、歷年最低分）不可修改；有疑義以 data/data.json 為準
- 成績僅在裝置端計算，不得加入任何上傳、統計或第三方追蹤程式
- 介面語言：繁體中文；行動裝置優先
- 機會判斷優先採用官方組合排名（加權皆1.00且有累計表對應者），其餘系組以114年比較法為輔，並標示資料來源

## Changelog

### 2026-08-03
- 更新 CLAUDE.md：新增 tools/112~115 四個年度資料夾說明、parse_accu.py 用途；標記 PWA 部署四項待辦為已完成；新增官方組合排名法整合六項新待辦；新增鐵則一條（機會判斷優先順序與資料來源標示）
- 確認 tools/112、113、114、115 資料夾檔案清單（詳見對話紀錄／步驟1回報）
