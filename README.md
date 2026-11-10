<div align="center">

# 🏝️ Dynamic Island for Windows

**A liquid “Dynamic Island” widget for the Windows 11 desktop: clock, now playing, word-synced lyrics, an audio-reactive wave, weather and notes.**

![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-Qt%206-41CD52?logo=qt&logoColor=white)
![Spicetify](https://img.shields.io/badge/Spicetify-optional-1DB954?logo=spotify&logoColor=white)

[English](#english) · [Русский](#русский)

<!-- TODO: add a screenshot or GIF as docs/demo.gif and put ![Demo](docs/demo.gif) here -->

</div>

---

## English

### ✨ Features

- **Liquid island**: a spring-driven shape that stretches, sticks to the top or side of the screen and can be dragged anywhere.
- **Now playing** from the Windows media session (SMTC): title, cover art, progress and playback controls. Works with any player, not only Spotify.
- **Lyrics**, karaoke-style:
  - [Spicy Lyrics](#-spicy-lyrics-optional) with word-by-word sync (optional, needs a key);
  - [LRCLIB](https://lrclib.net) with line sync, no key needed;
  - romanization for Korean and Japanese.
- **Audio wave**: the bottom edge dances to the music, captured from one app only (Spotify by default, process loopback on Windows 11) or from the whole output.
- **Weather** via Open-Meteo (no key), **notes** with pictures.
- Settings window, tray icon, multiple monitors, scale, opacity, accent color (or one taken from the album art), a starry background that follows your Spicetify theme, and a small pixel Claude dancing to the beat.

### 📋 Requirements

- Windows 10 or 11 (per-app audio capture needs Windows 11).
- Python 3.14 and the packages from `requirements.txt`.

No Spotify account, Premium or Spotify API key is required.

### 🚀 Getting started

```powershell
git clone https://github.com/clon4iik/dynamic-island.git
cd dynamic-island
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

cd island
python main.py      # pythonw main.py runs it without a console
```

Right-click the tray icon for notes, settings, show/hide and exit. Settings live in `island/config.json`, which is created with defaults on first run.

### 🎤 Spicy Lyrics (optional)

Spicy Lyrics gives the best lyrics (syllable sync, lots of tracks LRCLIB doesn't have), but it looks tracks up by their **Spotify track id**, which Windows doesn't expose. The island gets that id in one of two ways:

1. **Spicetify extension (automatic, recommended).** If you use [Spicetify](https://spicetify.app):
   ```powershell
   copy spicetify\island.js $env:APPDATA\spicetify\Extensions\
   spicetify config extensions island.js
   spicetify apply
   ```
   On every track change the extension posts the track id to the island at `127.0.0.1:38917`. The island accepts it only when title and length match what Windows reports. Re-run `spicetify apply` after Spotify updates.
2. **Copy the link (manual).** In Spotify choose *Share → Copy Song Link* on the playing track. The island picks the id up from the clipboard.

Either way the id is remembered per track in `cache/spotify_ids.json`, so it is needed only once.

To enable it, copy `island/.env.example` to `island/.env` and set `SPICY_LYRICS_SECRET_KEY`. Without a key, lyrics come from LRCLIB and neither the clipboard nor the port is used.

> 🔒 **Privacy.** Only a Spotify track link is ever read from the clipboard, and any other text is ignored. The port listens on `127.0.0.1` only and accepts requests from Spotify's own pages. `.env` is git-ignored.

### 📦 Building an .exe

```powershell
cd island
..\.venv\Scripts\python -m PyInstaller main.py --noconfirm --onefile --windowed --name DynamicIsland `
  --distpath ..\dist --collect-submodules winrt --collect-data soundcard --collect-data pykakasi `
  --hidden-import modules.media --hidden-import modules.lyrics --hidden-import modules.visualizer `
  --hidden-import modules.notes --hidden-import modules.dancer --hidden-import modules.process_audio `
  --hidden-import modules.weather --hidden-import modules.romaja --hidden-import modules.settings
```

The built app keeps its own `config.json`, `.env`, notes and cache next to `DynamicIsland.exe`.

### 🗂️ Project layout

```
island/
  main.py        # entry point, tray, rebuilding the island on settings changes
  window.py      # the island window, spring physics, hover and drag
  config.py      # config.json defaults, validation and UI strings
  modules/       # media, lyrics, visualizer, weather, notes, settings, dancer
  ui/            # liquid shape, card windows, widgets, theme, effects
spicetify/
  island.js      # Spicetify extension that reports the playing track id
```

<!-- TODO: choose a license (e.g. MIT) and add a LICENSE file -->

---

## Русский

### ✨ Возможности

- **«Жидкий» остров**: форма на пружинах тянется, прилипает к верхнему или боковому краю экрана, и её можно перетащить куда угодно.
- **Текущий трек** из системного медиаплеера Windows (SMTC): название, обложка, прогресс и управление. Работает с любым плеером, не только со Spotify.
- **Тексты песен** в стиле караоке:
  - [Spicy Lyrics](#-spicy-lyrics-необязательно) с пословной синхронизацией (необязательно, нужен ключ);
  - [LRCLIB](https://lrclib.net) с построчной синхронизацией, без ключей;
  - латиница для корейского и японского.
- **Волна по звуку**: нижний край острова танцует под музыку. Звук берётся только из одной программы (по умолчанию Spotify, process loopback в Windows 11) или со всего вывода.
- **Погода** через Open-Meteo (без ключа), **заметки** с картинками.
- Окно настроек, иконка в трее, несколько мониторов, масштаб, прозрачность, цвет акцента (в том числе из обложки), звёздный фон в цветах вашей темы Spicetify и маленький пиксельный Claude, который танцует в такт.

### 📋 Требования

- Windows 10 или 11 (захват звука одной программы — только Windows 11).
- Python 3.14 и пакеты из `requirements.txt`.

Аккаунт Spotify, Premium и ключ Spotify API не нужны.

### 🚀 Запуск

```powershell
git clone https://github.com/clon4iik/dynamic-island.git
cd dynamic-island
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

cd island
python main.py      # pythonw main.py — без консоли
```

Правый клик по иконке в трее: заметки, настройки, показать/скрыть, выход. Настройки лежат в `island/config.json`, при первом запуске он создаётся со значениями по умолчанию.

### 🎤 Spicy Lyrics (необязательно)

У Spicy Lyrics лучшие тексты: синхронизация по слогам и много треков, которых нет в LRCLIB. Но ищет он по **Spotify ID трека**, а Windows его не отдаёт. Остров получает ID одним из двух способов:

1. **Расширение Spicetify (автоматически, рекомендуется).** Если у вас стоит [Spicetify](https://spicetify.app):
   ```powershell
   copy spicetify\island.js $env:APPDATA\spicetify\Extensions\
   spicetify config extensions island.js
   spicetify apply
   ```
   При каждой смене трека расширение отправляет его ID острову на `127.0.0.1:38917`. Остров принимает ID, только если название и длительность совпадают с тем, что сообщает Windows. После обновления Spotify снова выполните `spicetify apply`.
2. **Копирование ссылки (вручную).** В Spotify на играющем треке нажмите «Поделиться → Копировать ссылку на трек», и остров заберёт ID из буфера обмена.

В обоих случаях ID запоминается для трека в `cache/spotify_ids.json`, так что нужен он только один раз.

Чтобы включить Spicy, скопируйте `island/.env.example` в `island/.env` и впишите `SPICY_LYRICS_SECRET_KEY`. Без ключа тексты берутся из LRCLIB, а буфер обмена и порт не используются.

> 🔒 **Приватность.** Из буфера обмена читается только ссылка на трек Spotify, любой другой текст игнорируется. Порт слушает только `127.0.0.1` и принимает запросы лишь со страниц самого Spotify. `.env` не попадает в git.

### 📦 Сборка .exe

Команда сборки — в [английском разделе](#-building-an-exe). У собранной версии свои `config.json`, `.env`, заметки и кеш: они лежат рядом с `DynamicIsland.exe`.

### 🗂️ Структура

```
island/
  main.py        # запуск, трей, пересборка острова при смене настроек
  window.py      # окно острова, физика пружин, наведение и перетаскивание
  config.py      # настройки по умолчанию, проверка config.json, строки интерфейса
  modules/       # медиа, тексты, визуализатор, погода, заметки, настройки, танцор
  ui/            # жидкая форма, окна-карточки, виджеты, тема, эффекты
spicetify/
  island.js      # расширение Spicetify, которое сообщает ID играющего трека
```
