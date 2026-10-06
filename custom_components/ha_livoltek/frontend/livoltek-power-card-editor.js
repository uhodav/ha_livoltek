
const LABELS = {
  en: {
    title_label: "Title",
    none_label: "None",
    device_label: "Device",
    pv_power: "PV Power",
    grid_power: "Grid Power",
    battery_power: "Battery Power",
    battery_soc: "Battery SoC",
    load_power: "Load Power",
    updatedAt: "Updated",
    unavailable: "Unavailable",
    configure: "Configure sensor entities",
    show_units_label: "Units",
    activity_label: "Activity",
    connection_label: "Connection",
  },
  uk: {
    title_label: "Заголовок",
    none_label: "Немає",
    device_label: "Пристрій",
    pv_power: "PV Потужність",
    grid_power: "Мережа",
    battery_power: "Акумулятор",
    battery_soc: "Заряд акумулятора",
    load_power: "Споживання",
    updatedAt: "Оновлено",
    unavailable: "Недоступно",
    configure: "Вкажіть сенсори в конфігурації",
    show_units_label: "Одиниці виміру",
    activity_label: "Активність",
    connection_label: "Підключення",
  },
};


const OVERRIDE_KEYS = [
  'active_sensor_pv', 'active_sensor_battery', 'active_sensor_grid', 'active_sensor_load',
  'connected_sensor_pv', 'connected_sensor_battery', 'connected_sensor_grid', 'connected_sensor_load',
];

const escapeHtml = (value) => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');

class LivoltekPowerCardEditor extends HTMLElement {
  // Groups power-flow sensors by HA device; sensor role is taken from translation_key
  _buildInverterMap() {
    if (!this._hass) return {};
    const entities = this._hass.entities || {};
    const map = {};

    for (const [entityId, entry] of Object.entries(entities)) {
      if (entry.platform !== 'ha_livoltek') continue;
      if (!entityId.startsWith('sensor.')) continue;

      const key = this._sensorKeys.includes(entry.translation_key)
        ? entry.translation_key
        : this._sensorKeys.find(k => entityId.endsWith('_' + k));
      if (!key) continue;

      const inverterId = entry.device_id || 'ha_livoltek';
      if (!map[inverterId]) map[inverterId] = {};
      map[inverterId][key] = entityId;
    }
    return map;
  }

  _inverterLabel(inverterId) {
    const device = this._hass?.devices?.[inverterId];
    return device?.name_by_user || device?.name || inverterId;
  }

  _applyInverterSensors(inverterId) {
    if (!inverterId || !this._hass) return;
    const sensors = this._inverterMap[inverterId] || {};
    this._sensorKeys.forEach(key => {
      const entityId = sensors[key];
      if (entityId && this._hass.states[entityId]) {
        this._config[key] = entityId;
      }
    });
    OVERRIDE_KEYS.forEach(key => delete this._config[key]);
    this.setupEntityPickers();
    this.configChanged(this._config);
  }
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hassSet = false;
    this._deviceds = [];
    this._sensorKeys = ['pv_power', 'grid_power', 'battery_power', 'battery_soc', 'load_power'];
    this._deviceInverter = '';
    this._inverterMap = {};
    this._rendered = false;
    this._elementsLoaded = false;
  }

  setConfig(config) {
    this._config = { ...config };
    // Initialize per-sensor show_units flags (default true)
    this._sensorKeys.forEach(key => {
      const unitKey = `show_units_${key}`;
      if (typeof this._config[unitKey] === 'undefined') {
        this._config[unitKey] = true;
      }
    });
    // Render only when both config and hass are available
    if (this._hass && !this._rendered) {
      this._findInverters();
      this.render();
    } else if (this._rendered) {
      this._syncInputs();
      this.setupEntityPickers();
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    if (!this._hassSet) {
      this._hassSet = true;
      this._findInverters();
      if (!this._rendered) {
        this.render();
      } else {
        this.setupEntityPickers();
      }
      return;
    }
    if (this._elementsLoaded) {
      this.shadowRoot.querySelectorAll('ha-entity-picker').forEach(picker => { picker.hass = hass; });
    }
  }

  // ha-entity-picker and friends are lazy-loaded by HA; force-load them via the entities card editor
  async _loadHaElements() {
    if (!customElements.get('ha-entity-picker')) {
      try {
        const helpers = await window.loadCardHelpers?.();
        const card = await helpers?.createCardElement({ type: 'entities', entities: [] });
        await card?.constructor?.getConfigElement?.();
      } catch (err) {
        console.warn('Livoltek card editor: failed to preload HA elements', err);
      }
    }
    this._elementsLoaded = true;
  }

  _findInverters() {
    if (!this._hass) return;

    this._inverterMap = this._buildInverterMap();
    this._deviceds = Object.keys(this._inverterMap);

    if (this._deviceInverter) return;

    const current = Object.entries(this._inverterMap).find(([, sensors]) =>
      this._sensorKeys.some(key => this._config[key] && sensors[key] === this._config[key]));
    if (current) {
      this._deviceInverter = current[0];
      return;
    }

    const isEmpty = this._sensorKeys.every(key => !this._config[key]);
    if (isEmpty && this._deviceds.length) {
      this._deviceInverter = this._deviceds[0];
      this._applyInverterSensors(this._deviceInverter);
    }
  }

  _syncInputs() {
    const title = this.shadowRoot.getElementById('title');
    if (title && title.value !== (this._config.title || '')) title.value = this._config.title || '';
    this._sensorKeys.forEach(key => {
      const toggle = this.shadowRoot.getElementById(`show_units_${key}`);
      if (toggle) toggle.checked = this._config[`show_units_${key}`] !== false;
    });
  }

  configChanged(newConfig) {
    this.dispatchEvent(new CustomEvent('config-changed', {
      bubbles: true,
      composed: true,
      detail: { config: newConfig },
    }));
  }

  _lang() {
    const lang = this._hass?.locale?.language || this._hass?.language || "en";
    return String(lang).startsWith("uk") ? "uk" : "en";
  }

  _t(key) {
    return LABELS[this._lang()][key] || LABELS.en[key] || key;
  }

  render() {
    if (!this._config) return;
    this.shadowRoot.innerHTML = `
      <style>
        .card-config { padding: 16px; }
        .option { margin-bottom: 16px; }
        .option label { display: block; margin-bottom: 4px; font-weight: 500; }
        .option input, .option select { width: 100%; padding: 8px; box-sizing: border-box; }
        .reset-btn {
          padding: 4px 10px;
          font-size: 13px;
          border-radius: 6px;
          border: transparent;
          background: transparent;
          color: #00b7ee;
          cursor: pointer;
          transition: background .2s;
        }
        .reset-btn:hover {
          background: #e0f7ff;
        }
        ha-expansion-panel {
          margin-bottom: 8px;
        }
        .sensor-row {
          align-items: center;
          gap: 8px;
          padding: 8px 16px;
        }
        .sensor-row ha-entity-picker {
          flex: 1;
        }
        .unit-toggle {
          margin-top: 14px;
          display: flex;
          align-items: center;
          gap: 4px;
          white-space: nowrap;
        }
      </style>
      <div class="card-config">
        <div class="option">
          <label>${this._t('title_label')}</label>
          <input type="text" id="title" value="${escapeHtml(this._config.title)}" placeholder="${this._t('title_label')}" />
        </div>
        ${this._deviceds.length ? `
        <div class="option">
          <label>${this._t('device_label')}</label>
          <div style="display: flex; gap: 8px;">
            <select id="inverter_select" style="flex:1;">
              <option value="" ${!this._deviceInverter ? 'selected' : ''}>${this._t('none_label')}</option>
              ${this._deviceds.map(id => `<option value="${escapeHtml(id)}" ${id === this._deviceInverter ? 'selected' : ''}>${escapeHtml(this._inverterLabel(id))}</option>`).join('')}
            </select>
            <button class="reset-btn" id="reset_sensors">⟳</button>
          </div>
        </div>
        ` : ''}

        <ha-expansion-panel outlined>
          <span slot="header">${this._t('pv_power')}</span>
          <div class="sensor-row">
            <ha-entity-picker id="pv_power" allow-custom-entity></ha-entity-picker>
            <div class="unit-toggle">
              <ha-switch id="show_units_pv_power" ${this._config.show_units_pv_power !== false ? 'checked' : ''}></ha-switch>
              <span>${this._t('show_units_label')}</span>
            </div>
          </div>
          <div class="sensor-row">
            <span style="min-width:90px">${this._t('activity_label')}:</span>
            <ha-entity-picker id="active_sensor_pv" allow-custom-entity></ha-entity-picker>
          </div>
          <div class="sensor-row">
            <span style="min-width:90px">${this._t('connection_label')}:</span>
            <ha-entity-picker id="connected_sensor_pv" allow-custom-entity></ha-entity-picker>
          </div>
        </ha-expansion-panel>

        <ha-expansion-panel outlined>
          <span slot="header">${this._t('battery_power')}</span>
          <div style="padding: 0 16px;">
            <div>${this._t('battery_soc')}</div>
            <div class="sensor-row" style="padding-left: 0; padding-right: 0;">
              <ha-entity-picker id="battery_soc" allow-custom-entity></ha-entity-picker>
              <div class="unit-toggle">
                <ha-switch id="show_units_battery_soc" ${this._config.show_units_battery_soc !== false ? 'checked' : ''}></ha-switch>
                <span>${this._t('show_units_label')}</span>
              </div>
            </div>

            <div>${this._t('battery_power')}</div>
            <div class="sensor-row" style="padding-left: 0; padding-right: 0;">
              <ha-entity-picker id="battery_power" allow-custom-entity></ha-entity-picker>
              <div class="unit-toggle">
                <ha-switch id="show_units_battery_power" ${this._config.show_units_battery_power !== false ? 'checked' : ''}></ha-switch>
                <span>${this._t('show_units_label')}</span>
              </div>
            </div>
            <div class="sensor-row">
              <span style="min-width:90px">${this._t('activity_label')}:</span>
              <ha-entity-picker id="active_sensor_battery" allow-custom-entity></ha-entity-picker>
            </div>
            <div class="sensor-row">
              <span style="min-width:90px">${this._t('connection_label')}:</span>
              <ha-entity-picker id="connected_sensor_battery" allow-custom-entity></ha-entity-picker>
            </div>
          </div>
        </ha-expansion-panel>

        <ha-expansion-panel outlined>
          <span slot="header">${this._t('grid_power')}</span>
          <div class="sensor-row">
            <ha-entity-picker id="grid_power" allow-custom-entity></ha-entity-picker>
            <div class="unit-toggle">
              <ha-switch id="show_units_grid_power" ${this._config.show_units_grid_power !== false ? 'checked' : ''}></ha-switch>
              <span>${this._t('show_units_label')}</span>
            </div>
          </div>
          <div class="sensor-row">
            <span style="min-width:90px">${this._t('activity_label')}:</span>
            <ha-entity-picker id="active_sensor_grid" allow-custom-entity></ha-entity-picker>
          </div>
          <div class="sensor-row">
            <span style="min-width:90px">${this._t('connection_label')}:</span>
            <ha-entity-picker id="connected_sensor_grid" allow-custom-entity></ha-entity-picker>
          </div>
        </ha-expansion-panel>

        <ha-expansion-panel outlined>
          <span slot="header">${this._t('load_power')}</span>
          <div class="sensor-row">
            <ha-entity-picker id="load_power" allow-custom-entity></ha-entity-picker>
            <div class="unit-toggle">
              <ha-switch id="show_units_load_power" ${this._config.show_units_load_power !== false ? 'checked' : ''}></ha-switch>
              <span>${this._t('show_units_label')}</span>
            </div>
          </div>
          <div class="sensor-row">
            <span style="min-width:90px">${this._t('activity_label')}:</span>
            <ha-entity-picker id="active_sensor_load" allow-custom-entity></ha-entity-picker>
          </div>
          <div class="sensor-row">
            <span style="min-width:90px">${this._t('connection_label')}:</span>
            <ha-entity-picker id="connected_sensor_load" allow-custom-entity></ha-entity-picker>
          </div>
        </ha-expansion-panel>
      </div>
    `;
    this.attachListeners();
    this._rendered = true;
    this._loadHaElements().then(() => this.setupEntityPickers());
  }

  // Override pickers stay empty unless set explicitly; the card then falls back to the main sensor
  setupEntityPickers() {
    if (!this._hass || !this._elementsLoaded) return;
    [...this._sensorKeys, ...OVERRIDE_KEYS].forEach(id => {
      const picker = this.shadowRoot.getElementById(id);
      if (picker) {
        picker.hass = this._hass;
        picker.value = this._config[id] || '';
        picker.includeDomains = OVERRIDE_KEYS.includes(id) ? ['sensor', 'binary_sensor'] : ['sensor'];
      }
    });
  }

  attachListeners() {
    const resetBtn = this.shadowRoot.getElementById('reset_sensors');
    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        if (this._deviceInverter) {
          this._applyInverterSensors(this._deviceInverter);
        }
      });
    }
    const update = () => {
      this._config = {
        ...this._config,
        title: this.shadowRoot.getElementById('title').value,
        pv_power: this.shadowRoot.getElementById('pv_power').value ?? this._config.pv_power,
        grid_power: this.shadowRoot.getElementById('grid_power').value ?? this._config.grid_power,
        battery_power: this.shadowRoot.getElementById('battery_power').value ?? this._config.battery_power,
        battery_soc: this.shadowRoot.getElementById('battery_soc').value ?? this._config.battery_soc,
        load_power: this.shadowRoot.getElementById('load_power').value ?? this._config.load_power,
        show_units_pv_power: this.shadowRoot.getElementById('show_units_pv_power')?.checked ?? true,
        show_units_grid_power: this.shadowRoot.getElementById('show_units_grid_power')?.checked ?? true,
        show_units_battery_power: this.shadowRoot.getElementById('show_units_battery_power')?.checked ?? true,
        show_units_battery_soc: this.shadowRoot.getElementById('show_units_battery_soc')?.checked ?? true,
        show_units_load_power: this.shadowRoot.getElementById('show_units_load_power')?.checked ?? true,
      };
      OVERRIDE_KEYS.forEach(key => {
        const value = this.shadowRoot.getElementById(key)?.value;
        if (value) this._config[key] = value;
        else delete this._config[key];
      });
      this.configChanged(this._config);
    };
    this.shadowRoot.querySelectorAll('input, ha-switch').forEach(el => {
      el.addEventListener('change', update);
    });
    this.shadowRoot.querySelectorAll('ha-entity-picker').forEach(el => {
      el.addEventListener('value-changed', (e) => {
        el.value = e.detail?.value || '';
        update();
      });
    });

    const inverterSelect = this.shadowRoot.getElementById('inverter_select');
    if (inverterSelect) {
      inverterSelect.addEventListener('change', () => {
        const id = inverterSelect.value;
        this._deviceInverter = id;
        if (id) {
          this._applyInverterSensors(id);
        }
      });
    }
  }
}

if (!customElements.get('livoltek-power-card-editor')) {
  customElements.define('livoltek-power-card-editor', LivoltekPowerCardEditor);
}
