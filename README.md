[![Stand With Ukraine](https://raw.githubusercontent.com/vshymanskyy/StandWithUkraine/main/badges/StandWithUkraine.svg)](https://stand-with-ukraine.pp.ua)

#### Ukraine is still suffering from Russian aggression, [please consider supporting Red Cross Ukraine with a donation](https://redcross.org.ua/en/).

[![Stand With Ukraine](https://raw.githubusercontent.com/vshymanskyy/StandWithUkraine/main/banner2-direct.svg)](https://stand-with-ukraine.pp.ua)

---

# Livoltek system for Home Assistant

[![Add to HACS](https://img.shields.io/badge/HACS-Add%20This%20Integration-blue?logo=home-assistant&style=for-the-badge)](https://my.home-assistant.io/redirect/hacs_repository/?owner=uhodav&repository=ha_livoltek&category=integration)

[Українською нижче ⬇️]


Custom Home Assistant integration for Livoltek inverters and BESS via Livoltek cloud API.

## English

### Features
- UI setup via Config Flow (no YAML required)
- 5-step setup wizard:
  1. API credentials (`server`, `secuid`, `key`, `token`)
  2. Site selection
  3. Device selection + update interval
  4. Data group selection (choose endpoint groups to enable)
  5. Optional BESS control credentials (`account`, `password`)
- Selective data collection by endpoint groups (13 groups)
- **116 sensors** total (measurements + diagnostics), plus optional portal data
- Human-readable enum values for statuses (PV, Grid, Load, Battery, Charging Pile, Running Status, Alarm Type, Battery Type)
- API rate limit enforcement (min 5 min interval, energy reports 1x/hour)
- BESS control entities:
  - 5 buttons (start/stop/restart/BMS restart/emergency charging)
  - 1 work mode select entity
- Service for setting work mode with optional schedule:
  - `ha_livoltek.set_work_mode_schedule`
- Multi-language UI (English/Ukrainian)

### Installation
#### Option 1: HACS
1. Open HACS
2. Add this repository as a custom integration (if needed)
3. Install **Livoltek system**
4. Restart Home Assistant

#### Option 2: Manual
1. Copy `custom_components/ha_livoltek` to your Home Assistant config directory:
   - `custom_components/ha_livoltek`
2. Restart Home Assistant

### Configuration values
#### Main setup (Config Flow)
- `server_type` — Livoltek server region (`international` / `european`)
- `secuid` — Security ID
- `key` — API key
- `token` — User token
- `account` (optional) — account for BESS control
- `password` (optional) — password for BESS control (stored as MD5)

#### Options (after setup) — 3-step wizard with pre-filled values
1. **API Credentials**: `server_type`, `secuid`, `key`, `token` — validates login on save
2. **Interval & Groups**: `update_interval` (min 5 min), `enabled_groups`
3. **BESS Control**: `account`, `password` (optional)

After saving, the integration fully reloads with fresh credentials.

### How to get SECUID / KEY / TOKEN
1. Go to: https://www.livoltek-portal.com/
2. Sign in to your Livoltek account
3. Open **My Profile** (top-right)
4. Click **Generate Token** to create/get your user token (`token`)
5. Click **Secure ID** to get:
   - `secuid` (Security ID)
   - `key` (API key)

### Data groups and sensors
You can enable/disable data groups during setup and in options.

1. **Power Flow** (`power_flow`)  
   PV/grid/load/battery power and statuses, battery SoC, EV charger status, update timestamp.

2. **Site Overview** (`overview`)  
   Current power, daily/monthly/yearly/lifetime generation, online devices, update timestamp.

3. **Site Details** (`site_details`)  
   Site type/status, PV capacity, alarm presence, country, timezone, update timestamp.

4. **Device Details** (`device_details`)  
   Serial number, product type, running status, firmware, manufacturer, work mode, update timestamp.

5. **Battery Storage** (`storage`)  
   BMS capacity, SoC, cycle count, battery serial.

6. **Device Electricity** (`device_electricity`)  
   Lifetime PV production and load consumption.

7. **Social Contribution** (`social`)  
   CO₂ reduction, trees saved, coal saved.

8. **Alarms** (`alarms`)  
   Alarm count, latest alarm name/time, top alarm details in attributes.

9. **Realtime** (`realtime`)  
   MPPT channels (PV1..PV12 voltage/current), AC phases, grid power/frequency, battery, EPS, timestamp.

10. **Daily Energy Report** (`daily_energy`)  
    Daily PV yield, load consumption, grid import/export, battery charge/discharge, EPS output, diesel generation, EV consumption.

11. **Site Installer** (`site_installer`)  
    Installer company name, organization code.

12. **Site Owner** (`site_owner`)  
    Owner name, email, login account, country.

13. **Device Basic Data** (`device_basic`)  
    Communication status, running status, registration time, daily power generation/grid export/import/charge/discharge/load.

### Sensor summary
- Total sensors: **116** (+14 sensors and 1 binary sensor with portal data)
- Each data group is a **separate HA device** (e.g. `HPXXXXXHYYMMNNN (⚡ Power Flow)`)
- Includes measurement and diagnostic entities
- Every sensor has `data_group` attribute showing its source group
- Disabling a group in options automatically removes its device

### Energy dashboard
Lifetime totals that never decrease, built from the daily counters of **Device Basic Data** (`device_basic`, updated every poll). Use them in Settings → Dashboards → Energy:

| Energy dashboard field | Sensor |
|---|---|
| Grid consumption | `grid_import_total_energy` |
| Return to grid | `grid_export_total_energy` |
| Solar production | `pv_total_energy` |
| Battery: energy going in | `battery_charge_total_energy` |
| Battery: energy coming out | `battery_discharge_total_energy` |
| Individual device (optional) | `load_total_energy` |

The `device_basic` group must be enabled. Values are restored after a restart.

With portal data enabled (see below) you can use the inverter's own lifetime counters instead: `portal_pv_energy_total`, `portal_grid_import_total`, `portal_grid_export_total`, `portal_battery_charge_total`, `portal_battery_discharge_total`, `portal_load_total`. Pick one set and do not mix them in the Energy dashboard.

### Portal data (optional, unofficial API)
Options → step 3 → **Use Livoltek portal data**. Uses the same account and password as BESS control to read the Livoltek web portal every minute:
- battery max/min temperature, inverter temperature, cell voltage max/min, battery state of health, battery capacity, discharge end SoC
- lifetime energy counters (see above)
- `binary_sensor` **Active Alarm**: on while an Important or Urgent alarm is active
- the actual inverter work mode: the work mode sensor and select are enabled and show the real mode
- battery capacity and discharge end SoC are used for the battery time estimates

The portal API is not documented by Livoltek and may change without notice. If it fails, only the portal entities become unavailable; everything else keeps working.

### Battery time estimates
- `battery_time_to_full`: minutes until 100% while charging, otherwise unknown
- `battery_time_to_empty`: minutes until the reserve SoC while discharging, otherwise unknown

The estimate uses the current battery power, SoC and battery capacity. The capacity is estimated as BMS capacity (Ah) × battery voltage, or you can set it in the integration options (**Battery capacity**, kWh). **Battery reserve SoC** (default 10%) is the level the inverter stops discharging at. Attributes show the capacity used and its source.

### Control entities
#### Buttons (BESS control)
- `button.inverter_start`
- `button.inverter_stop`
- `button.inverter_restart`
- `button.bms_restart`
- `button.emergency_charging`

#### Select
- `select.work_mode_select` — sets inverter work mode (disabled by default without portal data: the public API does not report the current mode, so the shown value can be stale; the `work_mode` sensor is disabled for the same reason)

### Service: set work mode with schedule
Service name: `ha_livoltek.set_work_mode_schedule`

Fields:
- `device_sn` (required)
- `work_mode` (required)
- `schedule_list` (optional, JSON array)

Example:
```yaml
service: ha_livoltek.set_work_mode_schedule
data:
  device_sn: "HPXXXXXHYYMMNNN"
  work_mode: 2
  schedule_list:
    - chargeType: 1
      startHour: 11
      startMin: 0
      endHour: 18
      endMin: 0
      chargingDays: [0, 1, 2, 3, 4]
```


## 🖼️ Livoltek Power Card (Lovelace)
A custom Lovelace card for Home Assistant to visualize Livoltek inverter and BESS power flow in a schematic, animated style.

![Power Card Preview](custom_components/ha_livoltek/frontend/images/preview.png)

### Features
- Schematic power flow: PV, Grid, Battery, Load, Inverter
- Animated SVG lines with moving dots for each flow
- Multi-language labels (EN/UA)
- Responsive design
- Visual editor for easy configuration in Lovelace UI

### Installation
1. The card is set up automatically, no manual copy or Lovelace resource is needed. On start the integration copies it to `config/www/ha_livoltek/` and keeps the dashboard resource `/local/ha_livoltek/livoltek-power-card.js?v=<version>` up to date, so the card is available right after a Home Assistant restart, before the integration itself has loaded (otherwise a dashboard opened during startup shows "Custom element doesn't exist"). Dashboards in YAML mode get the card from `/ha_livoltek/livoltek-power-card.js`. If you added the card as a resource manually before (any other URL), remove that resource.
2. Add the card via UI: "Add Card" → "Custom: Livoltek Power Card". Use the visual editor to select your sensors.

See full details and usage: [frontend/README.md](custom_components/ha_livoltek/frontend/README.md)

---

# Livoltek system для Home Assistant

[English above ⬆️]

Кастомна інтеграція Home Assistant для інверторів Livoltek та BESS через хмарний API Livoltek.

## Українська

### Можливості
- Налаштування через Config Flow (без YAML)
- Майстер налаштування з 5 кроків:
  1. API-дані (`server`, `secuid`, `key`, `token`)
  2. Вибір сайту
  3. Вибір пристрою + інтервал оновлення
  4. Вибір груп даних (endpoint groups)
  5. Опційні дані для керування BESS (`account`, `password`)
- Вибіркове отримання даних по 13 групах
- **116 сенсорів** (основні + діагностичні), плюс опційні дані порталу
- Читабельні значення статусів (PV, мережа, навантаження, батарея, EV, статус роботи, тип тривоги, тип батареї)
- Дотримання лімітів API (мін. 5 хв інтервал, звіти енергії 1 раз/годину)
- Сутності керування BESS:
  - 5 кнопок (start/stop/restart/BMS restart/emergency charging)
  - 1 select-сутність режиму роботи
- Сервіс для встановлення режиму з розкладом:
  - `ha_livoltek.set_work_mode_schedule`
- Багатомовний UI (англійська/українська)

### Встановлення
#### Варіант 1: HACS
1. Відкрийте HACS
2. Додайте цей репозиторій як custom integration (за потреби)
3. Встановіть **Livoltek system**
4. Перезапустіть Home Assistant

#### Варіант 2: вручну
1. Скопіюйте `custom_components/ha_livoltek` у директорію конфігурації Home Assistant:
   - `custom_components/ha_livoltek`
2. Перезапустіть Home Assistant

### Параметри налаштування
#### Основне налаштування (Config Flow)
- `server_type` — регіон сервера Livoltek (`international` / `european`)
- `secuid` — Security ID
- `key` — API key
- `token` — токен користувача
- `account` (опційно) — обліковий запис для BESS-керування
- `password` (опційно) — пароль для BESS-керування (зберігається як MD5)

#### Опції (після додавання) — 3-кроковий майстер із передзаповненими значеннями
1. **API-дані**: `server_type`, `secuid`, `key`, `token` — перевірка логіну при збереженні
2. **Інтервал і групи**: `update_interval` (мін. 5 хв), `enabled_groups`
3. **BESS-керування**: `account`, `password` (опційно)

Після збереження інтеграція повністю перезавантажується з оновленими обліковими даними.

### Як отримати SECUID / KEY / TOKEN
1. Перейдіть на: https://www.livoltek-portal.com/
2. Увійдіть у ваш акаунт Livoltek
3. Відкрийте **My Profile** (правий верхній кут)
4. Натисніть **Generate Token** для отримання токена користувача (`token`)
5. Натисніть **Secure ID** для отримання:
   - `secuid` (Security ID)
   - `key` (API key)

### Групи даних і сенсори
Групи можна вмикати/вимикати під час налаштування та в опціях.

1. **Power Flow** (`power_flow`)  
   Потужності PV/мережі/навантаження/батареї, статуси, SoC батареї, статус EV, час оновлення.

2. **Site Overview** (`overview`)  
   Поточна потужність, генерація за день/місяць/рік/весь час, online-пристрої, час оновлення.

3. **Site Details** (`site_details`)  
   Тип/статус станції, PV-потужність, наявність тривог, країна, часовий пояс, час оновлення.

4. **Device Details** (`device_details`)  
   Серійний номер, тип продукту, статус роботи, прошивка, виробник, режим роботи, час оновлення.

5. **Battery Storage** (`storage`)  
   Місткість BMS, SoC, цикли батареї, серійний номер батареї.

6. **Device Electricity** (`device_electricity`)  
   Загальна генерація PV і споживання навантаження.

7. **Social Contribution** (`social`)  
   Зекономлений CO₂, дерева, вугілля.

8. **Alarms** (`alarms`)  
   Кількість тривог, остання тривога (назва/час), деталі тривог в атрибутах.

9. **Realtime** (`realtime`)  
   Канали MPPT (PV1..PV12 напруга/струм), AC-фази, потужність/частота мережі, батарея, EPS, timestamp.

10. **Daily Energy Report** (`daily_energy`)  
    Добові значення генерації/споживання, імпорт/експорт мережі, заряд/розряд батареї, вихід EPS, дизельна генерація, споживання EV.

11. **Site Installer** (`site_installer`)  
    Назва компанії-інсталятора, код організації.

12. **Site Owner** (`site_owner`)  
    Ім'я власника, email, акаунт, країна.

13. **Device Basic Data** (`device_basic`)  
    Статус зв'язку, статус роботи, час реєстрації, добова генерація/експорт/імпорт/заряд/розряд/навантаження.

### Підсумок по сенсорах
- Усього сенсорів: **116** (+14 сенсорів і 1 бінарний сенсор з даними порталу)
- Кожна група даних — **окремий пристрій HA** (наприклад, `HPXXXXXHYYMMNNN (⚡ Потоки енергії)`)
- Є вимірювальні та діагностичні сутності
- Кожен сенсор має атрибут `data_group` з назвою групи-джерела
- Вимкнення групи в налаштуваннях автоматично видаляє її пристрій

### Енергетична панель
Загальні лічильники, які ніколи не зменшуються, побудовані з добових лічильників **Device Basic Data** (`device_basic`, оновлюються при кожному опитуванні). Підключайте їх у Налаштування → Панелі → Енергія:

| Поле енергетичної панелі | Сенсор |
|---|---|
| Споживання з мережі | `grid_import_total_energy` |
| Повернення в мережу | `grid_export_total_energy` |
| Сонячна генерація | `pv_total_energy` |
| Батарея: енергія, що надходить | `battery_charge_total_energy` |
| Батарея: енергія, що віддається | `battery_discharge_total_energy` |
| Окремий пристрій (опційно) | `load_total_energy` |

Група `device_basic` має бути увімкнена. Значення відновлюються після перезапуску.

З увімкненими даними порталу (див. нижче) можна використовувати власні загальні лічильники інвертора: `portal_pv_energy_total`, `portal_grid_import_total`, `portal_grid_export_total`, `portal_battery_charge_total`, `portal_battery_discharge_total`, `portal_load_total`. Оберіть один набір і не змішуйте їх в енергетичній панелі.

### Дані порталу (опційно, неофіційний API)
Налаштування → крок 3 → **Використовувати дані порталу Livoltek**. Використовує той самий акаунт і пароль, що й керування BESS, і читає веб-портал Livoltek щохвилини:
- макс./мін. температура батареї, температура інвертора, макс./мін. напруга комірки, стан батареї (SOH), ємність батареї, поріг розряду
- загальні лічильники енергії (див. вище)
- `binary_sensor` **Активна аварія**: увімкнений, поки активна важлива або термінова аварія
- реальний режим роботи інвертора: сенсор і select режиму вмикаються та показують справжній режим
- ємність батареї та поріг розряду використовуються для оцінки часу роботи батареї

API порталу не документований Livoltek і може змінитися без попередження. Якщо він не працює, недоступними стають лише сутності порталу, решта працює як раніше.

### Оцінка часу роботи батареї
- `battery_time_to_full`: хвилини до 100% під час заряду, інакше невідомо
- `battery_time_to_empty`: хвилини до резервного заряду під час розряду, інакше невідомо

Оцінка використовує поточну потужність батареї, SoC та ємність. Ємність оцінюється як ємність BMS (Ah) × напруга батареї, або її можна задати в налаштуваннях інтеграції (**Ємність батареї**, кВт·год). **Резервний заряд батареї** (за замовчуванням 10%) — рівень, на якому інвертор припиняє розряд. В атрибутах видно використану ємність і її джерело.

### Сутності керування
#### Кнопки (BESS control)
- `button.inverter_start`
- `button.inverter_stop`
- `button.inverter_restart`
- `button.bms_restart`
- `button.emergency_charging`

#### Select
- `select.work_mode_select` — вибір режиму роботи інвертора (без даних порталу вимкнено за замовчуванням: публічний API не повідомляє поточний режим, тому показане значення може бути застарілим; сенсор `work_mode` вимкнено з тієї ж причини)

### Сервіс: встановлення режиму з розкладом
Назва сервісу: `ha_livoltek.set_work_mode_schedule`

Поля:
- `device_sn` (обов'язково)
- `work_mode` (обов'язково)
- `schedule_list` (опційно, JSON-масив)

Приклад:
```yaml
service: ha_livoltek.set_work_mode_schedule
data:
  device_sn: "HPXXXXXHYYMMNNN"
  work_mode: 2
  schedule_list:
    - chargeType: 1
      startHour: 11
      startMin: 0
      endHour: 18
      endMin: 0
      chargingDays: [0, 1, 2, 3, 4]
```

## 🖼️ Livoltek Power Card (Lovelace) [UA]
Кастомна картка Lovelace для Home Assistant для візуалізації потоків енергії Livoltek у вигляді схеми з анімацією.

![Power Card Preview](custom_components/ha_livoltek/frontend/images/preview.png)

### Можливості
- Схематичний потік енергії: PV, Мережа, Акумулятор, Навантаження, Інвертор
- Анімовані SVG-лінії з рухомими точками
- Багатомовні підписи (UA/EN)
- Адаптивний дизайн
- Візуальний редактор для налаштування прямо в Lovelace

### Встановлення
1. Картка підключається автоматично, копіювати файли чи додавати ресурс Lovelace не потрібно. Під час запуску інтеграція копіює її в `config/www/ha_livoltek/` і підтримує ресурс панелей `/local/ha_livoltek/livoltek-power-card.js?v=<версія>`, тож картка доступна одразу після перезапуску Home Assistant, ще до завантаження самої інтеграції (інакше панель, відкрита під час старту, показує «Custom element doesn't exist»). Панелі в YAML-режимі отримують картку з адреси `/ha_livoltek/livoltek-power-card.js`. Якщо раніше ви додали картку як ресурс вручну (з іншою адресою), видаліть цей ресурс.
2. Додайте картку через UI: "Додати картку" → "Custom: Livoltek Power Card". Виберіть сенсори через візуальний редактор.

---

[![Stand With Ukraine](https://raw.githubusercontent.com/vshymanskyy/StandWithUkraine/main/banner2-direct.svg)](https://stand-with-ukraine.pp.ua)