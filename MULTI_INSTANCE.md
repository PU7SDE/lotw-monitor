# Guia: Rodando Múltiplas Instâncias do Bot

Este guia explica como rodar uma segunda (ou terceira) cópia do LoTW Monitor no mesmo servidor para amigos ou diferentes indicativos, mantendo tudo separado.

## 1. Duplique a Pasta do Projeto
Vamos criar uma cópia da pasta original para o novo usuário (ex: `lotw-amigo`).

```bash
cd /home/ubuntu
cp -r lotw-monitor lotw-amigo
```

## 2. Configure as Credenciais do Novo Usuário
Entre na nova pasta e edite o arquivo `.env`.

```bash
cd lotw-amigo
nano .env
```

**Altere as seguintes linhas:**
*   `LOTW_USERNAME`: Login do LoTW do seu amigo.
*   `LOTW_PASSWORD`: Senha do LoTW dele.
*   `TELEGRAM_BOT_TOKEN`: Token do Bot (pode ser um novo bot ou o mesmo, mas recomenda-se um novo para não misturar chats).
*   `TELEGRAM_CHAT_ID`: **Quem vai receber os alertas?**
    *   Se for para o **seu amigo** receber: Coloque o ID do Telegram dele.
    *   Se for para **VOCÊ** receber (monitorar ele): Coloque o **SEU** ID do Telegram.

## 3. Crie o Serviço no Systemd (Para o Bot responder comandos)
Para que o bot fique online e responda no Telegram:

```bash
sudo nano /etc/systemd/system/lotw-amigo.service
```

Cole o conteúdo abaixo (ajuste caminhos se necessário):

```ini
[Unit]
Description=LoTW Monitor Bot - Instancia Amigo
After=network.target

[Service]
Type=simple
User=ubuntu
# IMPORTANTE: Pasta onde está a cópia do código
WorkingDirectory=/home/ubuntu/lotw-amigo

# Usamos o Python/Venv da pasta ORIGINAL para economizar espaço
ExecStart=/home/ubuntu/lotw-monitor/venv/bin/python3 main.py --mode bot

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Ative e inicie:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now lotw-amigo
```

## 4. Configure o Cron (Para checagem automática)
O bot precisa de um agendamento para verificar novos QSOs automaticamente a cada X horas. Você precisa adicionar uma linha nova no Cron para essa pasta nova.

Edite o crontab:
```bash
crontab -e
```

Adicione uma nova linha abaixo da original:

```cron
# Bot Original (Seu)
0 */4 * * * cd /home/ubuntu/lotw-monitor && venv/bin/python3 main.py --mode check >> cron.log 2>&1

# Bot do Amigo (Nova linha)
0 */4 * * * cd /home/ubuntu/lotw-amigo && ../lotw-monitor/venv/bin/python3 main.py --mode check >> cron.log 2>&1
```
*(Note que usamos `../lotw-monitor/venv/...` para usar o Python da pasta original, ou você pode usar o venv da pasta nova se tiver criado um)*

Se você apenas copiou a pasta, o `venv` pode não ter ido junto ou pode estar quebrado se for link simbólico. Recomendo usar o caminho absoluto do python original:
`/home/ubuntu/lotw-monitor/venv/bin/python3`

**Exemplo Final Recomendado:**
```cron
0 */4 * * * cd /home/ubuntu/lotw-amigo && /home/ubuntu/lotw-monitor/venv/bin/python3 main.py --mode check >> cron.log 2>&1
```

Salve e pronto! Agora ambos serão verificados a cada 4 horas.
