# Japan Trip App — Notes Tab + Tab Redesign + Rich Notes

Date: 2026-06-11

## Overview

Three related changes to `japan-trip.html`:
1. Activity notes: auto-link URLs + image upload (base64)
2. Merge 記帳 and 統計 into one tab with sub-toggle
3. New 記事本 tab with two card types (記事 / 待辦清單)

---

## Feature 1 — Activity Note: URL Autolink + Image Upload

### URL Autolink
- On render, scan `act.note` for URLs (regex: `https?://\S+`)
- Replace matches with `<a href="..." target="_blank" rel="noopener">...</a>`
- Applied in the activity row render function, not on save (data stays as plain text)

### Image Upload
- In activity modal, add 「📷 新增圖片」button below the note textarea
- On tap: `<input type="file" accept="image/*">` triggered programmatically
- On file selected:
  - Draw to canvas, resize to max 800px on longest side
  - Export as JPEG quality 0.7 → base64 string
  - Preview thumbnail shown in modal (removable with ✕)
- Storage: `act.images = [base64string, ...]`, max 2 images per activity
- On activity row render: show image thumbnails below note; tap to open full-screen lightbox
- On edit: existing images shown with remove buttons

---

## Feature 2 — Tab Restructure

### Current tabs
行程 | 記帳 | 統計 | 設定

### New tabs
行程 | 💰 記帳 | 📒 記事本 | ⚙️ 設定

### 記帳 tab internal sub-toggle
Top of tab: segmented control `支出清單 ｜ 統計圖表`
- Default: 支出清單 (existing expense list view)
- Switch: 統計圖表 (existing stats view)
- State stored in JS variable `curAccTab`, not persisted

---

## Feature 3 — 記事本 Tab

### Firebase schema
```
/notes/{noteId}
  type: 'note' | 'todo'
  title: string
  content: string          // 記事 only
  images: string[]         // 記事 only, base64, max 2
  items: [{text, done}]    // 待辦清單 only
  createdAt: ISO string
  updatedAt: ISO string
```

### UI
- Tab content: scrollable card list, newest first
- Empty state: "尚無記事，點 ＋ 新增"
- FAB (right bottom): tap → expand two buttons: 「📝 記事」「✅ 待辦清單」

### 記事 card
- Shows: title (bold), content preview (2 lines), image thumbnails if any
- Tap → open edit modal
- Edit modal: title input, textarea, image upload (same compress logic as Feature 1)

### 待辦清單 card
- Shows: title, progress indicator (e.g. 2/5 完成), checkbox items
- Checkboxes tappable directly on the card (no need to open modal)
- Tap title/edit button → open edit modal to add/remove/rename items
- Completed items shown with strikethrough

### Shared behaviours
- Swipe-left or ✕ button to delete (with confirm dialog)
- All changes write immediately to Firebase `/notes/`

---

## Data Constraints

| Item | Limit | Reason |
|------|-------|--------|
| Images per activity | 2 | Firebase Realtime DB 1MB node limit |
| Images per note | 2 | Same |
| Image size | Max 800px, JPEG 0.7 | ~60-100KB per image after compress |

---

## Scope Exclusions
- No image re-ordering
- No note search/filter
- No rich text (markdown) in notes
- No push notifications for todos
