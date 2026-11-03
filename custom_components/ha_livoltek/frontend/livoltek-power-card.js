const CARD_TAG = "livoltek-power-card";
const EDITOR_TAG = "livoltek-power-card-editor";
const EDITOR_URL = "/ha_livoltek/livoltek-power-card-editor.js";
const SENSOR_KEYS = ['pv_power', 'grid_power', 'battery_power', 'battery_soc', 'load_power'];
// Flow direction comes from these when set, otherwise from the sign:
// battery power > 0 = charging, grid power > 0 = import
const STATUS_KEYS = ['battery_status', 'grid_status'];
// Picture of each block: a built-in name (see BUILTIN_ICONS), "mdi:..." or an image URL
const ICON_DEFAULTS = { pv_icon: 'solar', battery_icon: 'battery', grid_icon: 'grid', load_icon: 'home' };
const BUILTIN_ICONS = { solar: 'pv', generator: 'generator', battery: 'battery', grid: 'grid', home: 'load' };

const colorActive = '#00b7ee';
const colorInactive = '#e0e5e9ff';
const colorStale = 'var(--secondary-text-color, #8a8a8a)';
const UNAVAILABLE = ['unknown', 'unavailable', '', null, undefined];

const TIME_LABELS = {
  en: { h: 'h', min: 'min', to: 'to' },
  uk: { h: 'год', min: 'хв', to: 'до' },
};

const escapeHtml = (value) => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');

class LivoltekCard extends HTMLElement {
    static async getConfigElement() {
      if (!customElements.get(EDITOR_TAG)) {
        await import(EDITOR_URL);
      }
      return document.createElement(EDITOR_TAG);
    }
    _renderBlock({type, icon, entity, values, svgId, connected, svgStyle, extraStyle = '', isActive = true, isBack = true}) {
      const entityAttr = (id) => id ? ` data-entity="${escapeHtml(id)}"` : '';
      return `
        <div class="li_powerflow-block li_${type}" style="position:relative;${extraStyle}">
          <div class="li_icon"${entityAttr(entity)}>${icon}</div>
          ${values.map(v => v.text ? `
          <div class="li_value"${entityAttr(v.entity || entity)} style="${v.style}">
            <span style="${v.spanStyle}">${v.text}</span>
          </div>` : '').join('')}
          ${this._svgLine(svgId, connected, svgStyle, !!isActive, !!isBack)}
        </div>
      `;
    }

    _svgLine(id, sensorValue, style = "", isActive = true, isBack = false) {
      const color = !!sensorValue ? colorActive : colorInactive;
      const isBackAttr = isBack ? 'keyPoints="1;0" keyTimes="0;1"' : '';
      return `
        <svg style="${style}; position:absolute; z-index: 2; display: block;" viewBox="0 0 175 40">
          <path d="M.888 5.374h25.178l37.945 29.856h112.771" stroke="${color}" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round" id="${id}"></path>
          ${isActive ? `<circle r="5" fill="${color}"><animateMotion dur="2s" ${isBackAttr} repeatCount="indefinite"><mpath xlink:href="#${id}"></mpath></animateMotion></circle>` : ""}
        </svg>
      `;
    }
  setConfig(config) {
    if (!config || typeof config !== 'object') {
      throw new Error('Invalid configuration');
    }
    this._config = { ...config };
    this._renderKey = null;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 4;
  }

  static getStubConfig(hass) {
    const config = {
      type: `custom:${CARD_TAG}`,
      title: "",
      pv_power: "",
      grid_power: "",
      battery_power: "",
      battery_soc: "",
      load_power: "",
      show_units_pv_power: true,
      show_units_grid_power: true,
      show_units_battery_power: true,
      show_units_battery_soc: true,
      show_units_load_power: true,
    };
    for (const [entityId, entry] of Object.entries(hass?.entities || {})) {
      if (entry.platform !== 'ha_livoltek' || !entityId.startsWith('sensor.')) continue;
      const key = [...SENSOR_KEYS, ...STATUS_KEYS].includes(entry.translation_key) ? entry.translation_key : null;
      if (key && !config[key]) config[key] = entityId;
    }
    return config;
  }

  _ensureCard() {
    if (this._card) return;
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    this._card = document.createElement("ha-card");
    this._card.style.overflow = "hidden";
    this._card.addEventListener('click', (ev) => {
      const entityId = ev.target.closest?.('[data-entity]')?.dataset.entity;
      if (!entityId) return;
      this.dispatchEvent(new CustomEvent('hass-more-info', { detail: { entityId }, bubbles: true, composed: true }));
    });
    this.shadowRoot.appendChild(this._card);
  }

  _entityIds() {
    const c = this._config;
    return [
      c.pv_power, c.grid_power, c.battery_power, c.battery_soc, c.load_power,
      c.active_sensor_pv, c.active_sensor_battery, c.active_sensor_grid, c.active_sensor_load,
      c.connected_sensor_pv, c.connected_sensor_battery, c.connected_sensor_grid, c.connected_sensor_load,
      c.battery_status, c.grid_status, c.online_sensor, c.battery_capacity,
    ];
  }

  _stateChanged() {
    const states = this._entityIds().map(id => (id ? this._hass.states[id] : undefined));
    const changed = !this._renderKey || states.some((s, i) => s !== this._renderKey[i]);
    this._renderKey = states;
    return changed;
  }

  _stateObj(entityId) {
    return entityId ? this._hass.states[entityId] : undefined;
  }

  _formatState(stateObj, fractionDigits = null, showUnit = true) {
    if (!stateObj || ["unknown", "unavailable", null, undefined].includes(stateObj.state)) {
      return "—";
    }
    let value = stateObj.state;
    const numeric = Number(value);
    if (Number.isFinite(numeric) && fractionDigits !== null) {
      value = numeric.toFixed(fractionDigits);
    }
    const unit = stateObj.attributes.unit_of_measurement || "";
    return escapeHtml(showUnit && unit ? `${value} ${unit}` : `${value}`);
  }

  // power_unit: "W", "kW" or "auto" (kW from 1000 W); without it the sensor's own unit is shown
  _formatPower(stateObj, showUnit = true) {
    const mode = this._config.power_unit;
    const unit = stateObj?.attributes?.unit_of_measurement;
    const numeric = Number(stateObj?.state);
    if (!['W', 'kW', 'auto'].includes(mode) || !['W', 'kW'].includes(unit) || stateObj.state === '' || !Number.isFinite(numeric)) {
      return this._formatState(stateObj, 1, showUnit);
    }
    const watts = unit === 'kW' ? numeric * 1000 : numeric;
    const asKw = mode === 'kW' || (mode === 'auto' && Math.abs(watts) >= 1000);
    const value = asKw ? (watts / 1000).toFixed(2) : watts.toFixed(0);
    return escapeHtml(showUnit ? `${value} ${asKw ? 'kW' : 'W'}` : value);
  }

  // battery_capacity: kWh number or a sensor in kWh / Wh / Ah (Ah × battery_voltage, default 51.2 V)
  _batteryCapacityWh() {
    const cap = this._config.battery_capacity;
    if (cap === undefined || cap === null || cap === '') return null;
    if (Number.isFinite(Number(cap))) return Number(cap) * 1000;
    const stateObj = this._stateObj(String(cap));
    const value = Number(stateObj?.state);
    if (!stateObj || stateObj.state === '' || !Number.isFinite(value) || value <= 0) return null;
    const unit = stateObj.attributes.unit_of_measurement;
    if (unit === 'kWh') return value * 1000;
    if (unit === 'Wh') return value;
    if (unit === 'Ah') return value * (Number(this._config.battery_voltage) || 51.2);
    return null;
  }

  // "~2 h 10 min to 20 %": discharge down to battery_min_soc (20), charge up to battery_max_soc (100)
  _batteryTime(socNum, powerW, discharging) {
    const capacityWh = this._batteryCapacityWh();
    if (!capacityWh || !Number.isFinite(socNum) || Math.abs(powerW) < 50) return '';
    const target = discharging ? Number(this._config.battery_min_soc ?? 20) : Number(this._config.battery_max_soc ?? 100);
    const left = discharging ? socNum - target : target - socNum;
    if (!Number.isFinite(target) || left <= 0) return '';
    const minutes = Math.round(left / 100 * capacityWh / Math.abs(powerW) * 60);
    if (minutes > 99 * 60) return '';
    const lang = String(this._hass?.locale?.language || this._hass?.language || 'en').startsWith('uk') ? 'uk' : 'en';
    const t = TIME_LABELS[lang];
    const h = Math.floor(minutes / 60);
    const duration = h ? `${h} ${t.h} ${minutes % 60} ${t.min}` : `${minutes} ${t.min}`;
    return escapeHtml(`~${duration} ${t.to} ${target} %`);
  }

  // Last valid value from the history, for a sensor that is unavailable now (inverter offline). Re-read at most every 5 min.
  _fetchLastKnown(entityId) {
    this._lastKnown = this._lastKnown || {};
    const entry = this._lastKnown[entityId];
    if (entry && (entry.pending || Date.now() - entry.at < 5 * 60 * 1000)) return;
    this._lastKnown[entityId] = { ...entry, pending: true, at: Date.now() };
    this._hass.callWS({
      type: 'history/history_during_period',
      start_time: new Date(Date.now() - 7 * 24 * 3600 * 1000).toISOString(),
      entity_ids: [entityId],
      minimal_response: true,
      no_attributes: true,
      significant_changes_only: false,
    }).then((result) => {
      const valid = (result?.[entityId] || []).filter(item => !UNAVAILABLE.includes(item.s));
      const last = valid[valid.length - 1];
      this._lastKnown[entityId] = { state: last ? last.s : null, pending: false, at: Date.now() };
      if (last) {
        this._renderKey = null;
        this._render();
      }
    }).catch(() => {
      this._lastKnown[entityId] = { state: entry?.state ?? null, pending: false, at: Date.now() };
    });
  }

  // The value to show and whether it is stale (offline, or the last known value of an unavailable sensor)
  _shownState(entityId, online) {
    const stateObj = this._stateObj(entityId);
    if (!entityId || (stateObj && !UNAVAILABLE.includes(stateObj.state))) return { stateObj, stale: !online };
    if (this._config.last_known === false) return { stateObj, stale: true };
    this._fetchLastKnown(entityId);
    const known = this._lastKnown?.[entityId]?.state;
    if (UNAVAILABLE.includes(known)) return { stateObj, stale: true };
    return { stateObj: { state: known, attributes: stateObj?.attributes || {} }, stale: true };
  }

  _metric(label, value, icon, accent = false) {
    return `
      <div class="li_metric ${accent ? "li_metric--accent" : ""}">
        <div class="li_metric__icon">${icon}</div>
        <div class="li_metric__body">
          <div class="li_metric__label">${label}</div>
          <div class="li_metric__value">${value}</div>
        </div>
      </div>
    `;
  }

  _statusText(entityId) {
    const stateObj = this._stateObj(entityId);
    if (!stateObj) return '';
    return String(stateObj.attributes.raw_value ?? stateObj.state).toLowerCase();
  }

  _isActiveState(stateObj) {
    if (!stateObj || [null, undefined, 'unknown', 'unavailable'].includes(stateObj.state)) return false;
    const val = stateObj.state;
    if (typeof val === 'boolean') return val;
    if (typeof val === 'number') return val !== 0;
    if (typeof val === 'string') {
      const v = val.toLowerCase();
      if (v === 'on' || v === 'true' || v === 'yes') return true;
      if (v === 'off' || v === 'false' || v === 'no') return false;
      const num = Number(val);
      if (!isNaN(num)) return num !== 0;
    }
    return false;
  }


  _render() {
    if (!this._config || !this._hass) return;
    this._ensureCard();
    if (!this._stateChanged()) return;
    // The inverter is offline: values are the last known ones (grey), flows are not animated, blocks are not connected
    const online = !this._config.online_sensor || this._isActiveState(this._stateObj(this._config.online_sensor));
    const shown = {};
    ['pv_power', 'grid_power', 'battery_power', 'battery_soc', 'load_power'].forEach(key => {
      shown[key] = this._shownState(this._config[key], online);
    });
    const pv = shown.pv_power.stateObj;
    const grid = shown.grid_power.stateObj;
    const battery = shown.battery_power.stateObj;
    const soc = shown.battery_soc.stateObj;
    const load = shown.load_power.stateObj;
    const valueColor = (key, color) => shown[key].stale ? colorStale : color;

    const pvActiveSensor = this._stateObj(this._config.active_sensor_pv || this._config.pv_power);
    const batteryActiveSensor = this._stateObj(this._config.active_sensor_battery || this._config.battery_power);
    const gridActiveSensor = this._stateObj(this._config.active_sensor_grid || this._config.grid_power);
    const loadActiveSensor = this._stateObj(this._config.active_sensor_load || this._config.load_power);

    const pvConnectedSensor = this._stateObj(this._config.connected_sensor_pv || this._config.pv_power);
    const batteryConnectedSensor = this._stateObj(this._config.connected_sensor_battery || this._config.battery_power);
    const gridConnectedSensor = this._stateObj(this._config.connected_sensor_grid || this._config.grid_power);
    const loadConnectedSensor = this._stateObj(this._config.connected_sensor_load || this._config.load_power);

    const showUnitsPv = this._config.show_units_pv_power !== false;
    const showUnitsGrid = this._config.show_units_grid_power !== false;
    const showUnitsBattery = this._config.show_units_battery_power !== false;
    const showUnitsSoc = this._config.show_units_battery_soc !== false;
    const showUnitsLoad = this._config.show_units_load_power !== false;

    const pvVal = this._formatPower(pv, showUnitsPv);
    const gridVal = this._formatPower(grid, showUnitsGrid);
    const batteryVal = this._formatPower(battery, showUnitsBattery);
    const socVal = this._formatState(soc, 0, showUnitsSoc);
    const loadVal = this._formatPower(load, showUnitsLoad);

    const isConnected = (stateObj) => {
      if (!stateObj || [null, undefined, 'unknown', 'unavailable'].includes(stateObj.state)) return false;
      return this._isActiveState(stateObj);
    };

    const svgIcon = (icon, connected) => {
      const color = connected ? colorActive : colorInactive;
      if (!connected) {
        icon = icon.replace(/<circle[^>]*fill="url\(#A\)"[^>]*>/g, '');
      }
      icon = icon.replace(/fill="(?!url\(#A\))[^\"]*"/g, `fill="${color}"`);
      return icon;
    }

    // mdi icons and images are drawn inside the same ring as the built-in pictures
    const blockIcon = (key, connected) => {
      const spec = String(this._config[key] || ICON_DEFAULTS[key]).trim();
      const builtin = BUILTIN_ICONS[spec.toLowerCase()];
      if (builtin) return svgIcon(this._icons[builtin], connected);
      const inner = /^[a-z]+:[\w-]+$/i.test(spec)
        ? `<ha-icon icon="${escapeHtml(spec)}" style="color:${connected ? colorActive : colorInactive}"></ha-icon>`
        : `<img src="${escapeHtml(spec)}" alt="" style="${connected ? '' : 'opacity:.45;'}">`;
      return `<div class="li_icon-custom">${svgIcon(this._icons.ring, connected)}${inner}</div>`;
    }

    const pvNum = Number(pv && !isNaN(Number(pv.state)) ? pv.state : 0);
    const batteryNum = Number(battery && !isNaN(Number(battery.state)) ? battery.state : 0);
    const socNum = Number(soc && !isNaN(Number(soc.state)) ? soc.state : 0);
    const gridNum = Number(grid && !isNaN(Number(grid.state)) ? grid.state : 0);
    const loadNum = Number(load && !isNaN(Number(load.state)) ? load.state : 0);

    // isBack: the dot moves from the device to the inverter
    const batteryStatus = this._statusText(this._config.battery_status);
    // "Importing" is reported while the battery charges from the grid
    const batteryBack = batteryStatus.includes('discharg') ? true
      : batteryStatus.includes('charg') || batteryStatus.includes('import') ? false
      : batteryNum < 0;
    const gridStatus = this._statusText(this._config.grid_status);
    const gridBack = gridStatus.includes('import') ? true
      : gridStatus.includes('export') ? false
      : gridNum > 0;

    const batteryUnit = battery?.attributes?.unit_of_measurement;
    const batteryTime = online && !shown.battery_power.stale && !shown.battery_soc.stale
      ? this._batteryTime(Number(soc?.state), batteryNum * (batteryUnit === 'kW' ? 1000 : 1), batteryBack)
      : '';
    const pvActive = online && this._isActiveState(pvActiveSensor);
    const batteryActive = online && this._isActiveState(batteryActiveSensor);
    const gridActive = online && this._isActiveState(gridActiveSensor);
    const loadActive = online && this._isActiveState(loadActiveSensor);

    const pvConnected = online && isConnected(pvConnectedSensor);
    const batteryConnected = online && isConnected(batteryConnectedSensor);
    const gridConnected = online && isConnected(gridConnectedSensor);
    const loadConnected = online && isConnected(loadConnectedSensor);

    this._card.innerHTML = `
      <div class="li_powerflow-card">
        ${this._config.title ? `
          <div class="li_powerflow-header">${escapeHtml(this._config.title)}</div>
        ` : ''}
        <div class="li_powerflow-body">
          <div class="li_powerflow-left">
            ${this._renderBlock({
              type: 'pv',
              icon: blockIcon('pv_icon', pvConnected),
              entity: this._config.pv_power,
              values: [{
                style: 'position: absolute; left: calc(var(--icon-width) + 2px); top: calc((var(--icon-width) / 2) - 24px);',
                spanStyle: `color:${valueColor('pv_power', '#0382cc')}; white-space: nowrap;`,
                text: pvNum ? pvVal : ''
              }],
              svgId: 'pv-inverter',
              connected: pvConnected,
              svgStyle: 'transform: rotateX(180deg) rotateY(180deg); top: calc(var(--icon-width) / 2); left: var(--icon-width); right: 0;',
              isActive: pvActive,
              isBack: pvNum > 0
            })}
            ${this._renderBlock({
              type: 'battery',
              icon: blockIcon('battery_icon', batteryConnected),
              entity: this._config.battery_power,
              values: [
                {
                  style: 'position: absolute; left: calc(var(--icon-width) + 2px); top: calc((var(--icon-width) / 2 - 28px));',
                  spanStyle: `color:${valueColor('battery_soc', '#21a240')}; white-space: nowrap; font-weight: 600;`,
                  entity: this._config.battery_soc,
                  text: socVal
                },
                {
                  style: 'position: absolute; left: calc(var(--icon-width) + 2px); top: calc((var(--icon-width) / 2));',
                  spanStyle: `color:${valueColor('battery_power', '#0382cc')}; white-space: nowrap;`,
                  text: batteryNum ? batteryVal : ''
                },
                {
                  style: 'position: absolute; left: calc(var(--icon-width) + 2px); top: calc((var(--icon-width) / 2) + 20px);',
                  spanStyle: 'color: var(--secondary-text-color, #8a8a8a); white-space: nowrap; font-size: 12px;',
                  entity: this._config.battery_soc,
                  text: batteryTime
                }
              ],
              svgId: 'battery-inverter',
              connected: batteryConnected,
              svgStyle: 'left: 0; right: 0; transform: rotateY(180deg);bottom: calc(var(--icon-width) / 2);left: var(--icon-width);',
              extraStyle: 'align-items: start;',
              isActive: batteryActive,
              isBack: batteryBack
            })}
          </div>
          <div class="li_powerflow-center">
            ${this._icons.inverter}
          </div>
          <div class="li_powerflow-right">
            ${this._renderBlock({
              type: 'grid',
              icon: blockIcon('grid_icon', gridConnected),
              entity: this._config.grid_power,
              values: [{
                style: 'position: absolute; right: calc(var(--icon-width) + 2px); top: calc((var(--icon-width) / 2) - 24px);',
                spanStyle: `color:${valueColor('grid_power', '#0382cc')}; white-space: nowrap;`,
                text: gridNum ? gridVal : ''
              }],
              svgId: 'grid-inverter',
              connected: gridConnected,
              svgStyle: 'right: var(--icon-width);top: calc(var(--icon-width) / 2);left: 0; transform: rotateX(180deg);',
              extraStyle: 'display: flex; justify-content: flex-end; align-items: flex-start;',
              isActive: gridActive,
              isBack: gridBack
            })}
            ${this._renderBlock({
              type: 'load',
              icon: blockIcon('load_icon', loadConnected),
              entity: this._config.load_power,
              values: [{
                style: 'position: absolute; right: calc(var(--icon-width) + 2px); top: calc((var(--icon-width) / 2));',
                spanStyle: `color:${valueColor('load_power', '#0382cc')}; white-space: nowrap;`,
                text: loadNum ? loadVal : ''
              }],
              svgId: 'load-inverter',
              connected: loadConnected,
              svgStyle: 'right: var(--icon-width); bottom: calc(var(--icon-width) / 2);',
              extraStyle: 'display: flex; justify-content: flex-end; align-items: flex-start;',
              isActive: loadActive,
              isBack: loadNum < 0
            })}
          </div>
        </div>
      </div>
      ${this._styles()}
    `;
  }

  get _icons() {
    return {
      pv: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 82 82" fill="none">
        <defs><radialGradient id="A" cx="-70.159" cy="66.292" fx="-70.159" fy="66.292" r="30.571" gradientTransform="matrix(1.0590948,0,0,1.0590948,115.30516,-29.209956)" gradientUnits="userSpaceOnUse"><stop offset=".308" stop-color="#fff" stop-opacity="0"/><stop offset=".958" stop-color="#1ebcf0" stop-opacity=".267"/><stop offset=".995" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>
        <path d="M33.824 24.862a1 1 0 0 0-1 1v5.561a1 1 0 1 0 2 0v-5.561a1 1 0 0 0-1-1zm-8.814 3.043a1 1 0 0 0-.746 1.641l3.232 3.871a1 1 0 0 0 1.535-1.283l-3.232-3.869a1 1 0 0 0-.789-.359zm16.58.117a1 1 0 0 0-.68.352l-3.156 3.758a1 1 0 0 0 1.533 1.287l3.154-3.758a1 1 0 0 0-.852-1.639zm-9.238 4.85c-3.045 0-5.451 2.655-5.451 5.809 0 2.196 1.086 4.407 2.879 5.215l-8.51 11.115a1 1 0 0 0 .777 1.609l7.967.141a1 1 0 0 0 .178.193 1 1 0 0 0 1.34-.168l6.354.111a1 1 0 0 0 .002.002 1 1 0 0 0 1.078.018l8.631.152a1 1 0 0 0 .838-.426l13.75-19.689a1 1 0 0 0-.818-1.572h-9.289a1 1 0 0 0-.66 0h-5.633a1 1 0 0 0-1.025 0h-7.965a1 1 0 0 0-.064.016c-1.139-1.245-2.629-2.525-4.377-2.525zm-6.764 4.014l-4.959.037a1 1 0 1 0 .016 2l4.959-.037a1 1 0 1 0-.016-2zm11.697.496h5.924l-3.168 4.352-5.973-.148zm8.398 0h4.133l-3.041 4.52-4.305-.107zm6.545 0h7.219l-3.32 4.752-6.979-.174zm-26.021 5.215a1 1 0 0 0-.557.162l-4.207 2.742a1 1 0 1 0 1.092 1.676l4.207-2.742a1 1 0 0 0-.34-1.816 1 1 0 0 0-.195-.021zm6.357.951l6.045.15-2.988 4.102-6.211-.133zm8.475.211l4.412.109-2.748 4.084-4.646-.1zm6.785.17l6.93.172-2.828 4.049-6.844-.146zm-19.92 5.705l6.283.137-3.641 5-6.486-.115zm8.719.188l4.752.104-3.35 4.977-5.037-.088zm7.131.154l6.795.145-3.451 4.941-6.689-.117z" fill="#00b7ee"/>
        <circle cx="41" cy="41" r="32.378" fill="url(#A)"/>
        <path d="M41.001.055C18.442.055.13 18.402.13 41s18.313 40.945 40.871 40.945S81.87 63.598 81.87 41 63.56.055 41.001.055zm0 2.467c21.223 0 38.402 17.212 38.402 38.479s-17.18 38.477-38.402 38.477S2.597 62.267 2.597 41 19.778 2.521 41.001 2.521z" fill="#00b7ee"/>
      </svg>`,
      battery: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 82 82" fill="none">
        <defs><radialGradient id="A" cx="-70.159" cy="66.292" fx="-70.159" fy="66.292" r="30.571" gradientTransform="matrix(1.0590948,0,0,1.0590948,115.30516,-29.209956)" gradientUnits="userSpaceOnUse"><stop offset=".308" stop-color="#fff" stop-opacity="0"/><stop offset=".958" stop-color="#1ebcf0" stop-opacity=".267"/><stop offset=".995" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>
        <circle cx="41" cy="41" r="32.378" fill="url(#A)"/>
        <path d="M41.001.055C18.442.055.13 18.402.13 41s18.313 40.945 40.871 40.945S81.87 63.598 81.87 41 63.56.055 41.001.055zm0 2.467c21.223 0 38.402 17.212 38.402 38.479s-17.18 38.477-38.402 38.477S2.597 62.267 2.597 41 19.778 2.521 41.001 2.521zM21.678 28.918a1.25 1.25 0 0 0-1.25 1.25v21.664a1.25 1.25 0 0 0 1.25 1.25h35.32a1.25 1.25 0 0 0 1.25-1.25v-4.67h3.324v-1.725-8.875-1.725h-3.324v-4.67a1.25 1.25 0 0 0-1.25-1.25zm1.25 2.5h32.82v19.164h-32.82zm1.504 1.559v16.047h2.021V32.977zm4.971 0v16.047h2.02V32.977zm5.004 0v16.047h2.02V32.977zm5.082 0v16.047h2.02V32.977zm4.938 0v16.047h2.02V32.977z" fill="#00b7ee"/>
      </svg>`,
      grid: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 82 82" fill="none">
        <defs><radialGradient id="A" cx="-70.159" cy="66.292" fx="-70.159" fy="66.292" r="30.571" gradientTransform="matrix(1.0590948,0,0,1.0590948,115.30516,-29.209956)" gradientUnits="userSpaceOnUse"><stop offset=".308" stop-color="#fff" stop-opacity="0"/><stop offset=".958" stop-color="#1ebcf0" stop-opacity=".267"/><stop offset=".995" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>
        <path d="M35.576 20.284l-1.158 6.32h-2.912v2.5h2.453l-2.367 12.904h-3.09v2.5h2.631l-1.381 7.535-1.32 6.877.066-.045-.25 1.365a1.25 1.25 0 1 0 2.459.451l.695-3.795 9.797-6.674 9.246 6.113.875 4.445v.002l2.453-.48V60.3l-.037-.186-3.041-15.607h2.379v-2.5h-2.867l-2.373-12.178.006-.006-.043-.182-.105-.539h2.377v-2.5h-2.865l-1.213-6.227zm2.08 2.518l6.27.057.73 3.746h-.154-7.543zm-1.145 6.303h8.506L40.8 33.299l-4.291-4.176zm9.188 2.85l1.471 7.547-4.578-4.457zm-9.744.119l3.072 2.99-4.428 4.402zm4.863 4.732l5.346 5.203H35.587zm-3.729 7.703h8.057l-3.969 2.703zm-3.48.695l5.338 3.529-6.91 4.707.18-.984zm14.707.172l1.467 7.527-6.352-4.201zM41.001.055C18.442.055.13 18.402.13 41s18.313 40.945 40.871 40.945S81.87 63.598 81.87 41 63.56.055 41.001.055zm0 2.467c21.223 0 38.402 17.212 38.402 38.479s-17.18 38.477-38.402 38.477S2.597 62.267 2.597 41 19.778 2.521 41.001 2.521z" fill="#00b7ee"/>
        <circle cx="41" cy="41" r="32.378" fill="url(#A)"/>
      </svg>`,
      load: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 82 82" fill="none">
        <defs><radialGradient id="A" cx="-70.159" cy="66.292" fx="-70.159" fy="66.292" r="30.571" gradientTransform="matrix(1.0590948,0,0,1.0590948,115.30516,-29.209956)" gradientUnits="userSpaceOnUse"><stop offset=".308" stop-color="#fff" stop-opacity="0"/><stop offset=".958" stop-color="#1ebcf0" stop-opacity=".267"/><stop offset=".995" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>
        <circle cx="41" cy="41" r="32.378" fill="url(#A)"/>
        <path d="M41.001.055C18.442.055.13 18.402.13 41s18.313 40.945 40.871 40.945S81.87 63.598 81.87 41 63.56.055 41.001.055zm0 2.467c21.223 0 38.402 17.212 38.402 38.479s-17.18 38.477-38.402 38.477S2.597 62.267 2.597 41 19.778 2.521 41.001 2.521zm-.222 20.145a1 1 0 0 0-.395.188L22.8 36.605a1 1 0 0 0 1.232 1.576L41.001 24.91 57.97 38.106a1 1 0 0 0 1.402-.174 1 1 0 0 0-.176-1.404L41.613 22.852a1 1 0 0 0-.834-.186zm.232 5.482a1 1 0 0 0-.393.182l-13.3 10.144a1 1 0 0 0-.393.797v19.086a1 1 0 0 0 1 1h26.301a1 1 0 0 0 1-1V39.122a1 1 0 0 0-.391-.793l-13-9.994a1 1 0 0 0-.824-.186zm.211 2.236l12.004 9.229v17.744h-24.3V39.766zm2.361 7.631l-7.334 8.715 4.039.238-1.834 6.271 7.732-9.061-4.41.053z" fill="#00b7ee"/>
      </svg>`,
      generator: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 82 82" fill="none">
        <defs><radialGradient id="A" cx="-70.159" cy="66.292" fx="-70.159" fy="66.292" r="30.571" gradientTransform="matrix(1.0590948,0,0,1.0590948,115.30516,-29.209956)" gradientUnits="userSpaceOnUse"><stop offset=".308" stop-color="#fff" stop-opacity="0"/><stop offset=".958" stop-color="#1ebcf0" stop-opacity=".267"/><stop offset=".995" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>
        <circle cx="41" cy="41" r="32.378" fill="url(#A)"/>
        <path d="M41.001.055C18.442.055.13 18.402.13 41s18.313 40.945 40.871 40.945S81.87 63.598 81.87 41 63.56.055 41.001.055zm0 2.467c21.223 0 38.402 17.212 38.402 38.479s-17.18 38.477-38.402 38.477S2.597 62.267 2.597 41 19.778 2.521 41.001 2.521z" fill="#00b7ee"/>
        <path fill-rule="evenodd" d="M21.5 31.5h37v20.5h-37zm2.25 2.25v16h32.5v-16zM29.5 26h21v5.5h-2.25v-3.25h-16.5v3.25H29.5zM24.5 52h5v4.5h-5zm27 0h5v4.5h-5zm7-15.5h4v2.25h-4zm-15.25-.75l-7.75 9h4.75l-1.75 6 7.75-9h-4.75z" fill="#00b7ee"/>
      </svg>`,
      ring: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 82 82" fill="none">
        <defs><radialGradient id="A" cx="-70.159" cy="66.292" fx="-70.159" fy="66.292" r="30.571" gradientTransform="matrix(1.0590948,0,0,1.0590948,115.30516,-29.209956)" gradientUnits="userSpaceOnUse"><stop offset=".308" stop-color="#fff" stop-opacity="0"/><stop offset=".958" stop-color="#1ebcf0" stop-opacity=".267"/><stop offset=".995" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>
        <circle cx="41" cy="41" r="32.378" fill="url(#A)"/>
        <path d="M41.001.055C18.442.055.13 18.402.13 41s18.313 40.945 40.871 40.945S81.87 63.598 81.87 41 63.56.055 41.001.055zm0 2.467c21.223 0 38.402 17.212 38.402 38.479s-17.18 38.477-38.402 38.477S2.597 62.267 2.597 41 19.778 2.521 41.001 2.521z" fill="#00b7ee"/>
      </svg>`,
      inverter: `<svg xmlns="http://www.w3.org/2000/svg" 
          viewBox="0 0 60 70" 
          fill="none" 
          preserveAspectRatio="xMidYMid meet"
          style="width: 100%; height: auto;">
        <path fill="#00B7EE" d="M29.7 6.2L5.3 20.4v27.9l24.5 14.2 24.3-14.4v-27.8zm9.5 17.6L19.3 43.7c-11.8-13.2 7-31.3 19.9-19.9zm1.2 1.2c11.8 13.2-7 31.4-19.9 19.9zm-1 11.7a1 1 0 00-1.2.9c-.1 1-.4 1.6-.6 2s-.3.4-.4.4c-.3.1-1.1-.1-2.1-.6s-2.2-1-3.5-.7c-.7.2-1.3.7-1.8 1.4s-.8 1.5-1 2.7a1 1 0 002 .4c.2-1 .5-1.7.7-2.1s.5-.5.7-.5c.4-.1 1.2.1 2.2.5s2.1 1.1 3.4.7c.7-.2 1.3-.7 1.7-1.3s.6-1.6.8-2.7a1 1 0 00-.8-1.1zm-18.4-5.9a1 1 0 000 2l7.5.1a1 1 0 100-2zm.1-3.4a1 1 0 100 2l7.5.1a1 1 0 100-2z"/>
        <path stroke="#ABCAD5" stroke-opacity=".992" stroke-width="1.25" d="M29.8.7L.6 17.7l0 33.8 29.1 16.7 29.2-16.8 0-33.9z"/>
        <path fill="#FFF" d="M40.3 23.8L19.4 44.8"/>
      </svg>`
    };
  }

  _styles() {
    return `
      <style>
        .li_powerflow-card {
          --icon-width: 4vw;
          margin: 0 auto;
        }
        .li_powerflow-header {
          font-size: 22px;
          font-weight: 700;
          padding: 16px 0 0 16px;
          color: var(--primary-text-color, #222);
        }
        .li_powerflow-body {
          display: grid;
          grid-template-columns: 
          minmax(calc(var(--icon-width) + 42px), calc(var(--icon-width) + 105px)) 
          auto 
          minmax(calc(var(--icon-width) + 42px), calc(var(--icon-width) + 105px));
          padding: 13px;
          justify-content: center;
        }
        .li_powerflow-left, .li_powerflow-right {
          z-index: 2;
        }
        .li_powerflow-left {
          text-align: left;
        }
        .li_powerflow-right {
          text-align: right;
        }

        .li_powerflow-block {
          /* BEM: .li_value, .li_icon, .li_battery, .li_load */
        }
        .li_powerflow-block .li_value {
          font-size: 14px;
          color: #0382cc;
          z-index: 3;
          background: var(--ha-card-background, var(--card-background-color, #fff));
        }
        .li_powerflow-block [data-entity] {
          cursor: pointer;
        }
        .li_powerflow-block .li_icon {
          z-index: 2;
          width: var(--icon-width);
          height: var(--icon-width);
        }
        .li_icon-custom {
          position: relative;
          width: 100%;
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .li_icon-custom > svg {
          position: absolute;
          inset: 0;
        }
        .li_icon-custom ha-icon {
          --mdc-icon-size: calc(var(--icon-width) * 0.5);
          display: flex;
        }
        .li_icon-custom img {
          width: 56%;
          height: 56%;
          object-fit: contain;
          border-radius: 50%;
        }
        .li_powerflow-block.li_battery,
        .li_powerflow-block.li_load {
          margin-top: 8px;
        }
        .li_powerflow-block.li_battery .li_value {
          font-size: 14px;
        }
        .li_powerflow-center {
          display: flex;
          justify-content: center;
          align-items: center;
          width: calc(var(--icon-width) + 14px);
        }
        @media (max-width: 900px) {
          .li_powerflow-card {
            --icon-width: 41px;
            width: calc(var(--icon-width) + 248px);
          }
          .li_powerflow-body {
            grid-template-columns: 1fr auto 1fr;
          }
          .li_powerflow-header {
            font-size: var(--ha-font-size-xl, 14px);
          }
          .li_powerflow-center {
            width: calc(var(--icon-width) + 14px);
          }
        }
      </style>
    `;
  }
}

if (!customElements.get(CARD_TAG)) {
  customElements.define(CARD_TAG, LivoltekCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some(card => card.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "Livoltek Power Card",
    description: "Summary card for Livoltek sensors",
    preview: true,
  });
}

console.groupCollapsed(
  '%c LIVOLTEK-POWER-CARD %c v1.6.0 ',
  'color: white; background: #488fc2; font-weight: 700;',
  'color: #488fc2; background: white; font-weight: 700;'
);
console.log("Readme:", "https://github.com/uhodav/ha_livoltek");
console.groupEnd();
