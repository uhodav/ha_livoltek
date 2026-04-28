
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


class LivoltekPowerCardEditor extends HTMLElement {
  _buildInverterMap() {
    if (!this._hass) return {};
    const entities = this._hass.entities || {};
    const map = {};
    
    // Entity ID format: sensor.{device_sn}_{group_transliterated}_{sensor_key}
    for (const [entityId, entry] of Object.entries(entities)) {
      if (entry.platform !== 'ha_livoltek') continue;
      if (!entityId.startsWith('sensor.')) continue;
      
      // Strip "sensor." prefix
      const uid = entityId.slice(7);
      
      for (const key of this._sensorKeys) {
        const suffix = '_' + key;
        if (uid.endsWith(suffix)) {
          // Extract device SN (first segment before first underscore that looks like a serial)
          const match = uid.match(/^([a-zA-Z]{2}\d+[a-zA-Z0-9]*)/i);
          if (match) {
            const inverterId = match[1].toLowerCase();
            if (!map[inverterId]) map[inverterId] = {};
            map[inverterId][key] = entityId;
          }
          break;
        }
      }
    }
    return map;
  }

  _applyInverterSensors(inverterId) {
    if (!inverterId || !this._hass) return;
    const sensors = this._inverterMap[inverterId] || {};
    this._sensorKeys.forEach(key => {
      const entityId = sensors[key];
      if (entityId && this._hass.states[entityId]) {
        this._config[key] = entityId;
        const picker = this.shadowRoot.getElementById(key);
        if (picker) picker.value = entityId;
      }
    });
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
    this._platformEntityIds = new Set();
    this._rendered = false;
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
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (this._config && !this._hassSet) {
      this._hassSet = true;
      this._findInverters();
      if (!this._rendered) {
        this.render();
      } else {
        this.setupEntityPickers();
      }
    }
  }
  _findInverters() {
    if (!this._hass) return;

    this._inverterMap = this._buildInverterMap();
    this._deviceds = Object.keys(this._inverterMap);

    // Build set of all entity_ids belonging to ha_livoltek for entity picker filter
    this._platformEntityIds = new Set();
    const entities = this._hass.entities || {};
    for (const [entityId, entry] of Object.entries(entities)) {
      if (entry.platform === 'ha_livoltek') this._platformEntityIds.add(entityId);
    }

    if (this._deviceInverter) return;

    // Try to detect current inverter from existing config
    if (this._config && this._config.pv_power) {
      const cfgEntity = this._config.pv_power;
      for (const [invId, sensors] of Object.entries(this._inverterMap)) {
        if (sensors.pv_power === cfgEntity) {
          this._deviceInverter = invId;
          this._applyInverterSensors(invId);
          const select = this.shadowRoot && this.shadowRoot.getElementById('inverter_select');
          if (select) select.value = invId;
          return;
        }
      }
    }
    if (this._deviceds.length) {
      this._deviceInverter = this._deviceds[0];
      this._applyInverterSensors(this._deviceInverter);
      const select = this.shadowRoot && this.shadowRoot.getElementById('inverter_select');
      if (select) select.value = this._deviceInverter;
    }
  }

  configChanged(newConfig) {
    const event = new Event('config-changed', {
      bubbles: true,
      composed: true,
    });
    event.detail = { config: newConfig };
    this.dispatchEvent(event);
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
          <input type="text" id="title" value="${this._config.title || ''}" placeholder="${this._t('title_label')}" />
        </div>
        ${this._deviceds.length ? `
        <div class="option">
          <label>${this._t('device_label')}</label>
          <div style="display: flex; gap: 8px;">
            <select id="inverter_select" style="flex:1;">
              <option value="null" ${!this._deviceInverter ? 'selected' : ''}>${this._t('none_label')}</option>
              ${this._deviceds.map(id => `<option value="${id}" ${id === this._deviceInverter ? 'selected' : ''}>${id}</option>`).join('')}
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
    this.setupEntityPickers();
    this.attachListeners();
    this._rendered = true;
  }

  setupEntityPickers() {
    if (!this._hass) return;
    const pickers = [
      { id: 'pv_power', value: this._config.pv_power },
      { id: 'grid_power', value: this._config.grid_power },
      { id: 'battery_power', value: this._config.battery_power },
      { id: 'battery_soc', value: this._config.battery_soc },
      { id: 'load_power', value: this._config.load_power },
      { id: 'active_sensor_pv', value: this._config.active_sensor_pv || this._config.pv_power },
      { id: 'active_sensor_battery', value: this._config.active_sensor_battery || this._config.battery_power },
      { id: 'active_sensor_grid', value: this._config.active_sensor_grid || this._config.grid_power },
      { id: 'active_sensor_load', value: this._config.active_sensor_load || this._config.load_power },
      { id: 'connected_sensor_pv', value: this._config.connected_sensor_pv || this._config.pv_power },
      { id: 'connected_sensor_battery', value: this._config.connected_sensor_battery || this._config.battery_soc },
      { id: 'connected_sensor_grid', value: this._config.connected_sensor_grid || this._config.grid_power },
      { id: 'connected_sensor_load', value: this._config.connected_sensor_load || this._config.load_power },
    ];
    pickers.forEach(({ id, value }) => {
      const picker = this.shadowRoot.getElementById(id);
      if (picker) {
        picker.hass = this._hass;
        picker.value = value || '';
        picker.includeDomains = ['sensor'];
        picker.entityFilter = () => true;
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
        pv_power: this.shadowRoot.getElementById('pv_power').value,
        grid_power: this.shadowRoot.getElementById('grid_power').value,
        battery_power: this.shadowRoot.getElementById('battery_power').value,
        battery_soc: this.shadowRoot.getElementById('battery_soc').value,
        load_power: this.shadowRoot.getElementById('load_power').value,
        show_units_pv_power: this.shadowRoot.getElementById('show_units_pv_power')?.checked ?? true,
        show_units_grid_power: this.shadowRoot.getElementById('show_units_grid_power')?.checked ?? true,
        show_units_battery_power: this.shadowRoot.getElementById('show_units_battery_power')?.checked ?? true,
        show_units_battery_soc: this.shadowRoot.getElementById('show_units_battery_soc')?.checked ?? true,
        show_units_load_power: this.shadowRoot.getElementById('show_units_load_power')?.checked ?? true,
        active_sensor_pv: this.shadowRoot.getElementById('active_sensor_pv')?.value || this.shadowRoot.getElementById('pv_power')?.value,
        active_sensor_battery: this.shadowRoot.getElementById('active_sensor_battery')?.value || this.shadowRoot.getElementById('battery_power')?.value,
        active_sensor_grid: this.shadowRoot.getElementById('active_sensor_grid')?.value || this.shadowRoot.getElementById('grid_power')?.value,
        active_sensor_load: this.shadowRoot.getElementById('active_sensor_load')?.value || this.shadowRoot.getElementById('load_power')?.value,
        connected_sensor_pv: this.shadowRoot.getElementById('connected_sensor_pv')?.value || this.shadowRoot.getElementById('pv_power')?.value,
        connected_sensor_battery: this.shadowRoot.getElementById('connected_sensor_battery')?.value || this.shadowRoot.getElementById('battery_power')?.value,
        connected_sensor_grid: this.shadowRoot.getElementById('connected_sensor_grid')?.value || this.shadowRoot.getElementById('grid_power')?.value,
        connected_sensor_load: this.shadowRoot.getElementById('connected_sensor_load')?.value || this.shadowRoot.getElementById('load_power')?.value,
      };
      this.configChanged(this._config);
    };
    this.shadowRoot.querySelectorAll('input, ha-entity-picker, ha-switch').forEach(el => {
      el.addEventListener('change', update);
      el.addEventListener('blur', update);
    });

    const inverterSelect = this.shadowRoot.getElementById('inverter_select');
    if (inverterSelect) {
      inverterSelect.addEventListener('change', (e) => {
        const id = inverterSelect.value;
        this._deviceInverter = id;
        if (id) {
          this._applyInverterSensors(id);
        }
      });
    }
  }
}

customElements.define('livoltek-power-card-editor', LivoltekPowerCardEditor);
