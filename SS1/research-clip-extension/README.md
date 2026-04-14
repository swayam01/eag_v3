# Research Clip Chrome Extension

Research Clip is a Manifest V3 Chrome extension to save useful content from any webpage.

## Demo Video
[Watch Demo](https://youtu.be/d6UEMmT2uVA)

## Features
- Save selected text from current page
- Auto-save page URL and page title
- Add manual notes
- Add tags
- Search saved items
- Copy saved note later
- Delete and edit entries
- Dark mode toggle
- Data stored locally using `chrome.storage.local`

## Files
- `manifest.json` - Chrome extension manifest
- `popup.html` - Extension popup UI
- `popup.css` - Styling for popup and dark mode
- `popup.js` - Main extension logic
- `content.js` - Reads page title, URL, and selected text

## How to load in Chrome
1. Open Chrome
2. Go to `chrome://extensions/`
3. Turn on **Developer mode**
4. Click **Load unpacked**
5. Select this project folder

## How to use
1. Open any webpage
2. Select text on the page
3. Click the extension icon
4. Add note and tags if needed
5. Click **Save Clip**
6. Search, copy, edit, or delete clips later from the popup

```
