const CARD_TAG = "livoltek-power-card";

const colorActive = '#00b7ee';
const colorInactive = '#e0e5e9ff';

class LivoltekCard extends HTMLElement {
      static getConfigElement() {
        return document.createElement('livoltek-power-card-editor');
      }
    _renderBlock({type, icon, values, svgId, sensorNum, svgStyle, extraStyle = '', isActive = true, isBack = true}) {
      return `
        <div class="powerflow-block ${type}" style="position:relative;${extraStyle}">
          <div class="icon">${icon}</div>
          ${values.map(v => v.text ? `
          <div class="value" style="${v.style}">
            <span style="${v.spanStyle}">${v.text}</span>
          </div>` : '').join('')}
          ${this._svgLine(svgId, sensorNum, svgStyle, !!isActive, !!isBack)}
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
    this._config = { ...config };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._card) {
      this._card = document.createElement("ha-card");
      this._card.style.overflow = "hidden";
      this.appendChild(this._card);
    }
    this._render();
  }

  getCardSize() {
    return 4;
  }

  static getStubConfig() {
    return {
      type: `custom:${CARD_TAG}`,
      title: "Livoltek",
      pv_power: "sensor.livoltek_XXXXXXXX_pv_power",
      grid_power: "sensor.livoltek_XXXXXXXX_grid_power",
      battery_power: "sensor.livoltek_XXXXXXXX_battery_power",
      battery_soc: "sensor.livoltek_XXXXXXXX_battery_soc",
      load_power: "sensor.livoltek_XXXXXXXX_load_power",
    };
  }

  _stateObj(entityId) {
    return entityId ? this._hass.states[entityId] : undefined;
  }

  _formatState(stateObj, fractionDigits = null) {
    if (!stateObj || ["unknown", "unavailable", null, undefined].includes(stateObj.state)) {
      return "—";
    }
    let value = stateObj.state;
    const numeric = Number(value);
    if (Number.isFinite(numeric) && fractionDigits !== null) {
      value = numeric.toFixed(fractionDigits);
    }
    const unit = stateObj.attributes.unit_of_measurement || "";
    return unit ? `${value} ${unit}` : `${value}`;
  }

  _metric(label, value, icon, accent = false) {
    return `
      <div class="metric ${accent ? "metric--accent" : ""}">
        <div class="metric__icon">${icon}</div>
        <div class="metric__body">
          <div class="metric__label">${label}</div>
          <div class="metric__value">${value}</div>
        </div>
      </div>
    `;
  }

  _render() {
    if (!this._config) return;
    const pv = this._stateObj(this._config.pv_power);
    const grid = this._stateObj(this._config.grid_power);
    const battery = this._stateObj(this._config.battery_power);
    const soc = this._stateObj(this._config.battery_soc);
    const load = this._stateObj(this._config.load_power);

    const pvVal = this._formatState(pv, 1).replace(' W', ' kW').replace('—', '0 kW');
    const gridVal = this._formatState(grid, 1).replace(' W', ' kW').replace('—', '0 kW');
    const batteryVal = this._formatState(battery, 1).replace(' W', ' kW').replace('—', '0 kW');
    const socVal = this._formatState(soc, 0).replace('—', '0').replace('%', '') + '%';
    const loadVal = this._formatState(load, 1).replace(' W', ' kW').replace('—', '0 kW');

    const svgIcon = (icon, sensorValue) => {
      const color = sensorValue !== 0 ? colorActive : colorInactive;
      if (!sensorValue) {
        icon = icon.replace(/<circle[^>]*fill="url\(#A\)"[^>]*>/g, '');
      }
      icon = icon.replace(/fill="(?!url\(#A\))[^"]*"/g, `fill="${color}"`);
      return icon;
    }

    const svgLine = (id, sensorValue, style = "") => {
      const color = sensorValue !== 0 ? colorActive : colorInactive;
      const isBack = sensorValue > 0 ? 'keyPoints="1;0" keyTimes="0;1"' : '';
      return `
        <svg style="${style}; position:absolute; z-index: 2; display: block;" viewBox="0 0 175 40">
          <path d="M.888 5.374h25.178l37.945 29.856h112.771" stroke="${color}" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round" id="${id}""></path>
          ${sensorValue !== 0 ? `<circle r="5" fill="${color}"><animateMotion dur="2s" ${isBack} repeatCount="indefinite"><mpath xlink:href="#${id}"></mpath></animateMotion></circle>` : ""}
        </svg>
      `;
    }

    const pvNum = Number(pv && !isNaN(Number(pv.state)) ? pv.state : 0);
    const batteryNum = Number(battery && !isNaN(Number(battery.state)) ? battery.state : 0);
    const socNum = Number(soc && !isNaN(Number(soc.state)) ? soc.state : 0);
    const gridNum = Number(grid && !isNaN(Number(grid.state)) ? grid.state : 0);
    const loadNum = Number(load && !isNaN(Number(load.state)) ? load.state : 0);

    this._card.innerHTML = `
      <div class="powerflow-card">
        <div class="powerflow-header">${this._config.title}</div>
        <div class="powerflow-body">
          <div class="powerflow-left">
            ${this._renderBlock({
              type: 'pv',
              icon: svgIcon(this._icons.pv, pvNum),
              values: [{
                style: 'position: absolute; left: calc(var(--icon-width) + 2px); top: calc((var(--icon-width) / 2) - 24px);',
                spanStyle: 'color:#0382cc; white-space: nowrap;',
                text: pvNum ? pvVal : ''
              }],
              svgId: 'pv-inverter',
              sensorNum: pvNum,
              svgStyle: 'transform: rotateX(180deg) rotateY(180deg); top: calc(var(--icon-width) / 2); left: var(--icon-width); right: 0;',
              isActive: !!pvNum,
              isBack: pvNum < 0
            })}
            ${this._renderBlock({
              type: 'battery',
              icon: svgIcon(this._icons.battery, batteryNum || socNum),
              values: [
                {
                  style: 'position: absolute; left: calc(var(--icon-width) + 2px); top: calc((var(--icon-width) / 2 - 28px));',
                  spanStyle: 'color:#21a240; white-space: nowrap; font-weight: 600;',
                  text: socVal
                },
                {
                  style: 'position: absolute; left: calc(var(--icon-width) + 2px); top: calc((var(--icon-width) / 2));',
                  spanStyle: 'color:#0382cc; white-space: nowrap;',
                  text: batteryNum ? batteryVal : ''
                }
              ],
              svgId: 'battery-inverter',
              sensorNum: batteryNum || socNum,
              svgStyle: 'left: 0; right: 0; transform: rotateY(180deg);bottom: calc(var(--icon-width) / 2);left: var(--icon-width);',
              extraStyle: 'align-items: start;',
              isActive: !!batteryNum,
              isBack: batteryNum > 0
            })}
          </div>
          <div class="powerflow-center">
            ${this._icons.inverter}
          </div>
          <div class="powerflow-right">
            ${this._renderBlock({
              type: 'grid',
              icon: svgIcon(this._icons.grid, gridNum),
              values: [{
                style: 'position: absolute; right: calc(var(--icon-width) + 2px); top: calc((var(--icon-width) / 2) - 24px);',
                spanStyle: 'color:#0382cc; white-space: nowrap;',
                text: gridNum ? gridVal : ''
              }],
              svgId: 'grid-inverter',
              sensorNum: gridNum,
              svgStyle: 'right: var(--icon-width);top: calc(var(--icon-width) / 2);left: 0; transform: rotateX(180deg);',
              extraStyle: 'display: flex; justify-content: flex-end; align-items: flex-start;',
              isActive: !!gridNum,
              isBack: gridNum < 0
            })}
            ${this._renderBlock({
              type: 'load',
              icon: svgIcon(this._icons.load, loadNum),
              values: [{
                style: 'position: absolute; right: calc(var(--icon-width) + 2px); top: calc((var(--icon-width) / 2));',
                spanStyle: 'color:#0382cc; white-space: nowrap;',
                text: loadNum ? loadVal : ''
              }],
              svgId: 'load-inverter',
              sensorNum: loadNum,
              svgStyle: 'right: var(--icon-width); bottom: calc(var(--icon-width) / 2);',
              extraStyle: 'display: flex; justify-content: flex-end; align-items: flex-start;',
              isActive: !!loadNum,
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
        .powerflow-card {
          --icon-width: 4vw;
          background: var(--ha-card-background, #fff);
          margin: 0 auto;
          border-radius: 10px;
          box-shadow: 0 2px 8px #0001;
        }
        .powerflow-header {
          font-size: 22px;
          font-weight: 700;
          padding: 16px 0 0 16px;
          color: var(--primary-text-color, #222);
        }
        .powerflow-body {
          display: grid;
          grid-template-columns: 
          minmax(calc(var(--icon-width) + 42px), calc(var(--icon-width) + 105px)) 
          auto 
          minmax(calc(var(--icon-width) + 42px), calc(var(--icon-width) + 105px));
          padding: 13px;
          justify-content: center;
        }
        .powerflow-left, .powerflow-right {
          z-index: 2;
        }
        .powerflow-left {
          text-align: left;
        }
        .powerflow-right {
          text-align: right;
        }

        .powerflow-block {
          .value {
            font-size: 14px;
            color: #0382cc;
            z-index: 3;
            background: var(--ha-card-background, #fff);
          }
          .icon {
            z-index: 2;
            width: var(--icon-width);
            height: var(--icon-width);
          }
          &.battery,
          &.load {
            margin-top: 8px;
          }
        }
          .powerflow-block .value {
            font-size: 14px;
            color: #0382cc;
            z-index: 3;
            background: var(--ha-card-background, #fff);
          }
          .powerflow-block .icon {
            z-index: 2;
            width: var(--icon-width);
            height: var(--icon-width);
          }
          .powerflow-block.battery,
          .powerflow-block.load {
            margin-top: 8px;
          }
        .powerflow-block.battery .value {
          font-size: 14px;
        }
        .powerflow-center {
          display: flex;
          justify-content: center;
          align-items: center;
          width: calc(var(--icon-width) + 14px);
        }
        @media (max-width: 900px) {
          .powerflow-card {
            --icon-width: 41px;
            width: calc(var(--icon-width) + 248px);
          }
          .powerflow-body {
            grid-template-columns: 1fr auto 1fr;
          }
          .powerflow-header {
            font-size: var(--ha-font-size-xl, 14px);
          }
          .powerflow-center {
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
window.customCards.push({
  type: CARD_TAG,
  name: "Livoltek Card",
  description: "Summary card for Livoltek sensors",
  preview: true,
});
