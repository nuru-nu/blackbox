# Shan Deliar's blackbox

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
sudo rabbitmqctl set_permissions 'blackbox' '' '.*' '.*'
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
