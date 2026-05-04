#!/usr/bin/env bash
# Instalacja zależności i pierwsza konfiguracja
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== 1/4  Tworzenie virtualenv ==="
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "      OK"

echo "=== 2/4  Tworzenie folderów na HDD ==="
mkdir -p /mnt/hdd/akn/files
mkdir -p /mnt/hdd/akn/versions
echo "      OK  →  /mnt/hdd/akn/"

echo ""
echo "=== 3/4  credentials.json ==="
if [ ! -f credentials.json ]; then
  echo ""
  echo "  WYMAGANY: umieść plik credentials.json w katalogu:"
  echo "    $SCRIPT_DIR/credentials.json"
  echo ""
  echo "  Jak go zdobyć:"
  echo "  1. Wejdź na https://console.cloud.google.com/"
  echo "  2. Utwórz projekt (lub użyj istniejącego)"
  echo "  3. APIs & Services → Enable APIs → Google Drive API"
  echo "  4. APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID"
  echo "     Typ aplikacji: Desktop app"
  echo "  5. Pobierz JSON i zapisz jako credentials.json tutaj"
  echo ""
else
  echo "      OK  (credentials.json już istnieje)"
fi

echo "=== 4/4  Pierwsze uruchomienie ==="
echo ""
echo "  Uruchom raz ręcznie, żeby zalogować się do Google:"
echo "    cd $SCRIPT_DIR && source venv/bin/activate && python sync.py"
echo ""
echo "  Przeglądarka otworzy się automatycznie – zatwierdź dostęp."
echo "  Po autoryzacji skrypt zacznie synchronizować i działa co 10 min."
echo ""
echo "=== Instalacja jako usługa systemd (auto-start) ==="
echo ""
echo "  sudo cp gdrive-sync.service /etc/systemd/system/gdrive-sync@\$USER.service"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now gdrive-sync@\$USER"
echo "  sudo systemctl status gdrive-sync@\$USER"
echo ""
