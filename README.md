# Shan Deliar's blackbox

## Setup

Prerequisites on raspbian bullseye:

```bash
sudo apt install libsdl2-mixer-2.0-0 libsdl2-dev libsdl2-image-2.0-0 libsdl2-ttf-2.0-0 -y
```

Installation:

```bash
python -m venv env
. env/bin/activate
pip install -r requirements.txt
```

Running RabbitMQ on raspbian bullseye (~250 MiB)

```bash
sudo apt install rabbitmq-server -y
sudo systemctl enable rabbitmq-server
sudo systemctl start rabbitmq-server
sudo systemctl status rabbitmq-server

# control via http://localhost:15672/
sudo rabbitmq-plugins enable rabbitmq_management
sudo rabbitmq-plugins enable rabbitmq_mqtt

sudo rabbitmqctl add_user 'blackbox'  # password: blackbox
sudo rabbitmqctl set_permissions -p / blackbox ".*" ".*" ".*"

# if something is not working check:
# /var/log/rabbitmq/rabbit@*.log
```

Similar commands on OS X

```bash
brew install rabbitmq
/opt/homebrew/opt/rabbitmq/sbin/rabbitmq-plugins enable rabbitmq_mqtt
# start server
CONF_ENV_FILE="/opt/homebrew/etc/rabbitmq/rabbitmq-env.conf" /opt/homebrew/opt/rabbitmq/sbin/rabbitmq-server
# set up users (server already running)
rabbitmqctl add_user 'blackbox'  # password: blackbox
rabbitmqctl set_permissions 'blackbox' '' '.*' '.*'
```

## Troubleshooting

1. connect to the web UI at :8080
2. check mqtt connection in UI
3. `ssh nuru@unuru.local -L15673:localhost:15672` and then check mqtt server at http://localhost/15673 (guest/guest)


## Set up as service

Make sure to execute this in the repo, after verifying that `./env/bin/python blackbox.py` works

```bash
cat <<EOF | sudo tee /etc/systemd/system/blackbox.service
[Unit]
Description=Blackbox Service
After=network.target

[Service]
Nice=-10
ExecStart=$(pwd)/env/bin/python $(pwd)/blackbox.py
WorkingDirectory=$(pwd)
User=$USER
Restart=always
RestartSec=3
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=blackbox
PAMName=login

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable blackbox.service
sudo systemctl start blackbox.service
```

Then follow logs with `sudo journalctl -f -u blackbox`

## raspbian hotspot

```bash
# https://chatgpt.com/share/be8eca39-1151-4418-87ee-1b1700fc24e7

sudo apt install hostapd dnsmasq -y

# safety copies !
test -f /etc/dhcpcd.conf.no_hotspot || sudo cp /etc/dhcpcd.conf /etc/dhcpcd.conf.no_hotspot
test -f /etc/dnsmasq.conf.no_hotspot || sudo cp /etc/dnsmasq.conf /etc/dnsmasq.conf.no_hotspot

sudo systemctl stop hostapd
sudo systemctl stop dnsmasq

# reset configs
sudo cp /etc/dhcpcd.conf.no_hotspot /etc/dhcpcd.conf.hotspot
sudo cp /etc/dnsmasq.conf.no_hotspot /etc/dnsmasq.conf.hotspot

# update configs
cat <<EOF | sudo tee -a /etc/dhcpcd.conf.hotspot > /dev/null
interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
EOF
cat <<EOF | sudo tee -a /etc/dnsmasq.conf.hotspot > /dev/null
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
EOF
cat <<EOF | sudo tee /etc/hostapd/hostapd.conf > /dev/null
interface=wlan0
driver=nl80211
ssid=unuru
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=opensecret
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF
grep /etc/hostapd/hostapd.conf /etc/default/hostapd || ( echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' | sudo tee -a /etc/default/hostapd > /dev/null )

# scripts
cat <<EOF > ~/stop_hotspot.sh
#!/bin/bash
sudo cp /etc/dhcpcd.conf.no_hotspot /etc/dhcpcd.conf
sudo cp /etc/dnsmasq.conf.no_hotspot /etc/dnsmasq.conf
sudo systemctl disable hostapd
sudo systemctl disable dnsmasq
sudo systemctl restart dhcpcd
sudo systemctl stop hostapd
sudo systemctl stop dnsmasq
sudo reboot
EOF
chmod a+x stop_hotspot.sh

cat <<EOF > ~/start_hotspot.sh
#!/bin/bash
sudo cp /etc/dhcpcd.conf.hotspot /etc/dhcpcd.conf
sudo cp /etc/dnsmasq.conf.hotspot /etc/dnsmasq.conf
sudo systemctl unmask hostapd
sudo systemctl unmask dnsmasq
sudo systemctl enable hostapd
sudo systemctl enable dnsmasq
sudo systemctl restart dhcpcd
sudo systemctl restart hostapd
sudo systemctl restart dnsmasq
EOF
chmod a+x start_hotspot.sh
```