#!/usr/bin/env bash
# Installs the bot as an always-on service on a Debian/Ubuntu server (e.g. Google Cloud e2-micro).
# Usage (from the unzipped project folder):  bash deploy/install.sh
set -euo pipefail
APP=/opt/meme-smart-money
sudo apt-get update -qq && sudo apt-get install -y -qq python3 nano >/dev/null
sudo mkdir -p "$APP" /var/lib/meme-smart-money
sudo cp -r msm "$APP/"
[ -f wallets.json ] && sudo cp wallets.json "$APP/" || true
if [ ! -f "$APP/.env" ]; then
  sudo cp .env.example "$APP/.env"
  echo ">>> Paste your keys into the .env file that opens now. Save: Ctrl+O, Enter. Exit: Ctrl+X."
  read -r -p "Press Enter to open it..." _
  sudo nano "$APP/.env"
fi
sudo chmod 600 "$APP/.env"
sudo sed -i 's#^DB_PATH=.*#DB_PATH=/var/lib/meme-smart-money/msm.sqlite3#' "$APP/.env"
sudo tee /etc/systemd/system/meme-smart-money.service >/dev/null <<UNIT
[Unit]
Description=Meme Smart Money bot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$APP
ExecStart=/usr/bin/python3 -m msm run
Restart=always
RestartSec=30
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now meme-smart-money
echo
echo "Installed. Useful commands:"
echo "  sudo journalctl -u meme-smart-money -f      # live logs"
echo "  sudo systemctl restart meme-smart-money     # after editing $APP/.env"
echo "  sudo nano $APP/.env                         # change settings (e.g. DRY_RUN=false)"
