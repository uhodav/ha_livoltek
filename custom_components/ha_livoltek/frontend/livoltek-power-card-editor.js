
const LABELS = {
  en: {
    title: "Livoltek",
    pv_power: "PV Power",
    grid_power: "Grid Power",
    battery_power: "Battery Power",
    battery_soc: "Battery SoC",
    load_power: "Load Power",
    updatedAt: "Updated",
    unavailable: "Unavailable",
    configure: "Configure sensor entities",
  },
  uk: {
    title: "Livoltek",
    pv_power: "PV Потужність",
    grid_power: "Мережа",
    battery_power: "Акумулятор",
    battery_soc: "Заряд акумулятора",
    load_power: "Споживання",
    updatedAt: "Оновлено",
    unavailable: "Недоступно",
    configure: "Вкажіть сенсори в конфігурації",
  },
};


class LivoltekPowerCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hassSet = false;
  }

  setConfig(config) {
    this._config = { ...config };
    this.render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._config && !this._hassSet) {
      this._hassSet = true;
      this.render();
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
        .option input { width: 100%; padding: 8px; box-sizing: border-box; }
      </style>
      <div class="card-config">
        <div class="option">
          <label>${this._t('title')}</label>
          <input type="text" id="title" value="${this._config.title || ''}" placeholder="${this._t('title')}" />
        </div>
        <div class="option">
          <label>${this._t('pv_power')}</label>
          <ha-entity-picker id="pv_power" allow-custom-entity></ha-entity-picker>
        </div>
        <div class="option">
          <label>${this._t('grid_power')}</label>
          <ha-entity-picker id="grid_power" allow-custom-entity></ha-entity-picker>
        </div>
        <div class="option">
          <label>${this._t('battery_power')}</label>
          <ha-entity-picker id="battery_power" allow-custom-entity></ha-entity-picker>
        </div>
        <div class="option">
          <label>${this._t('battery_soc')}</label>
          <ha-entity-picker id="battery_soc" allow-custom-entity></ha-entity-picker>
        </div>
        <div class="option">
          <label>${this._t('load_power')}</label>
          <ha-entity-picker id="load_power" allow-custom-entity></ha-entity-picker>
        </div>
      </div>
    `;
    this.setupEntityPickers();
    this.attachListeners();
  }

  setupEntityPickers() {
    if (!this._hass) return;
    const pickers = [
      { id: 'pv_power', value: this._config.pv_power },
      { id: 'grid_power', value: this._config.grid_power },
      { id: 'battery_power', value: this._config.battery_power },
      { id: 'battery_soc', value: this._config.battery_soc },
      { id: 'load_power', value: this._config.load_power },
    ];
    pickers.forEach(({ id, value }) => {
      const picker = this.shadowRoot.getElementById(id);
      if (picker) {
        picker.hass = this._hass;
        picker.value = value || '';
        picker.includeDomains = ['sensor'];
        picker.entityFilter = (entity) => {
          const entityId = typeof entity === 'string' ? entity : entity.entity_id;
          return entityId && entityId.startsWith('sensor.livoltek_');
        };
      }
    });
  }

  attachListeners() {
    const update = () => {
      this._config = {
        ...this._config,
        title: this.shadowRoot.getElementById('title').value,
        pv_power: this.shadowRoot.getElementById('pv_power').value,
        grid_power: this.shadowRoot.getElementById('grid_power').value,
        battery_power: this.shadowRoot.getElementById('battery_power').value,
        battery_soc: this.shadowRoot.getElementById('battery_soc').value,
        load_power: this.shadowRoot.getElementById('load_power').value,
      };
      this.configChanged(this._config);
    };
    this.shadowRoot.querySelectorAll('input, ha-entity-picker').forEach(el => {
      el.addEventListener('change', update);
      el.addEventListener('blur', update);
    });
  }
}

customElements.define('livoltek-power-card-editor', LivoltekPowerCardEditor);
