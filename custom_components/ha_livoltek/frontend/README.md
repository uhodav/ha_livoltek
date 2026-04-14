# Livoltek Power Card Test Guide

This document describes how to test and develop the `livoltek-power-card` custom Lovelace card for Home Assistant.

## Quick Start

1. **Run a local HTTP server**
   - Open a terminal in this directory:
     ```
     cd custom_components/ha_livoltek/frontend
     python -m http.server 8005
     ```
   - Open your browser at: [http://localhost:8005/test-livoltek-card.html](http://localhost:8005/test-livoltek-card.html)

2. **Edit and test the card**
   - Make changes to `livoltek-power-card.js`.
   - Reload the test page in your browser (Ctrl+F5 for hard refresh).

3. **Preview image**
   - The file `images/preview.png` is used as a static preview for Home Assistant card gallery.

## Files
- `livoltek-power-card.js` — main card source code
- `livoltek-power-card-editor.js` — visual editor for Lovelace UI
- `test-livoltek-card.html` — standalone test page (no Home Assistant required)
- `images/preview.png` — preview image for Home Assistant

## Test Page Usage
- The test page simulates Home Assistant environment and allows you to test the card UI and logic without running Home Assistant.
- You can edit the test entities and config directly in `test-livoltek-card.html`.

## Development Tips
- Use browser DevTools for debugging and live editing.
- After editing JS files, always do a hard refresh (Ctrl+F5) to avoid cache issues.
- For Home Assistant integration, copy the JS files to your `www/community/ha_livoltek/frontend/` directory and add as a Lovelace resource.

## Example Card Config
```yaml
type: custom:livoltek-power-card
title: Livoltek
pv_power: sensor.livoltek_XXXXXXXX_pv_power
grid_power: sensor.livoltek_XXXXXXXX_grid_power
battery_power: sensor.livoltek_XXXXXXXX_battery_power
battery_soc: sensor.livoltek_XXXXXXXX_battery_soc
load_power: sensor.livoltek_XXXXXXXX_load_power
```

---