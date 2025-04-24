# Vacuum Fluorescent Display

## Set up as service

Make sure to execute this in the repo, after verifying that `./env/bin/python vfd_generate.py` works

```bash
cat <<EOF | sudo tee /etc/systemd/system/vfd_generate.service
[Unit]
Description=VFD Generator Service
After=network.target

[Service]
Nice=-10
ExecStart=$(pwd)/env/bin/python $(pwd)/vfd_generate.py --ip=vfd
WorkingDirectory=$(pwd)
User=$USER
Restart=always
RestartSec=3
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=vfd_generate
PAMName=login

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable vfd_generate.service
sudo systemctl start vfd_generate.service
```
