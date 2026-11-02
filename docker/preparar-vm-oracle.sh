#!/bin/bash
# Prepara una VM Micro de Oracle: swap, firewall (iptables) y Docker.
# Uso: preparar_vm.sh "80 443"     (puertos TCP a abrir hacia afuera)
#      preparar_vm.sh "8000@10.0.0.0/16"  (puerto abierto solo a un origen)
set -e
PUERTOS="$1"

if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

for p in $PUERTOS; do
  puerto="${p%@*}"
  origen=""
  [ "$p" != "$puerto" ] && origen="-s ${p#*@}"
  if ! sudo iptables -C INPUT -p tcp $origen --dport "$puerto" -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 5 -p tcp $origen --dport "$puerto" -j ACCEPT
  fi
done
sudo mkdir -p /etc/iptables
sudo sh -c 'iptables-save > /etc/iptables/rules.v4'

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh >/dev/null 2>&1
  sudo usermod -aG docker ubuntu
fi
sudo systemctl enable --now docker >/dev/null 2>&1
echo "LISTO: $(docker --version) | $(docker compose version 2>/dev/null | head -1) | swap=$(free -m | awk '/Swap/{print $2}')MB"
