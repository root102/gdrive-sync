# gdrive-sync — Google Drive → HDD z wersjonowaniem

Skrypt synchronizuje wybrany folder Google Drive na lokalny dysk HDD.
- Uruchamia się automatycznie jako usługa systemd
- Synchronizuje co **10 minut**
- Każda zmiana pliku zapisuje poprzednią wersję z datą w `versions/`
- Obsługuje pliki Google Docs/Sheets/Slides (eksportuje do .docx/.xlsx/.pptx)

## Struktura katalogów na HDD

```
/mnt/hdd/akn/
├── files/          ← aktualne wersje plików (odwzorowuje strukturę Drive)
├── versions/       ← historia wersji
│   └── Plik.docx/
│       ├── 2025-05-01T14-30-00.docx
│       └── 2025-05-03T09-12-45.docx
├── .state.json     ← cache stanu (nie edytuj ręcznie)
└── sync.log        ← logi
```

## Szybki start

### 1. Klonuj repo

```bash
git clone https://github.com/<twój-user>/gdrive-sync.git
cd gdrive-sync
```

### 2. Pobierz `credentials.json` z Google Cloud Console

1. Wejdź na <https://console.cloud.google.com/>
2. Utwórz projekt lub użyj istniejącego
3. **APIs & Services → Library** → wyszukaj **Google Drive API** → Enable
4. **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
   - Typ aplikacji: **Desktop app**
5. Pobierz JSON → zapisz jako `credentials.json` w katalogu projektu

### 3. Uruchom setup

```bash
chmod +x setup.sh
./setup.sh
```

### 4. Pierwsze uruchomienie (autoryzacja Google)

```bash
source venv/bin/activate
python sync.py
```

Przeglądarka otworzy się automatycznie — zaloguj się i zatwierdź dostęp.
`token.json` zostanie zapisany lokalnie (nie commituj go!).

### 5. Instalacja jako usługa systemd

```bash
sudo cp gdrive-sync.service /etc/systemd/system/gdrive-sync@$USER.service
sudo systemctl daemon-reload
sudo systemctl enable --now gdrive-sync@$USER
sudo systemctl status gdrive-sync@$USER
```

Logi:
```bash
journalctl -u gdrive-sync@$USER -f
# lub
tail -f /mnt/hdd/akn/sync.log
```

## Konfiguracja (`config.yaml`)

| Klucz | Domyślnie | Opis |
|---|---|---|
| `folder_id` | ID folderu AKN | ID folderu Google Drive |
| `dest_dir` | `/mnt/hdd/akn/files` | Katalog docelowy |
| `versions_dir` | `/mnt/hdd/akn/versions` | Katalog wersji |
| `sync_interval_seconds` | `600` | Interwał synchronizacji (sekundy) |

## Wymagania

- Python 3.10+
- Konto Google z dostępem do folderu
- Dysk HDD zamontowany pod `/mnt/hdd`
