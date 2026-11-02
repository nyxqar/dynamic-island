# Dynamic Island

Виджет «динамического острова» для Windows: часы, текущий трек из SMTC, тексты песен, эквалайзер, погода.

## Установка

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Настройка

1. Скопируйте `island/.env.example` в `island/.env` и вставьте свои ключи (необязательно):
   - `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` — ключи приложения с [Spotify Developer Dashboard](https://developer.spotify.com/dashboard). Нужны для поиска трека в Spotify.
   - `SPICY_LYRICS_SECRET_KEY` — ключ для Spicy Lyrics.
   Файл `.env` не попадает в git. Переменные окружения с такими же именами имеют приоритет.
2. При необходимости отредактируйте `island/config.json` (язык, цвет акцента, модули, город для погоды и т.д.). Если файла нет, он создастся с настройками по умолчанию.

## Запуск

```powershell
cd island
python main.py
```

Для сборки `.exe` файлы `config.json` и `.env` кладутся рядом с исполняемым файлом.
