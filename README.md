# 📡 LoTW Satellite Monitor & Bot

Este projeto é um assistente pessoal para **Radioamadores Operadores de Satélite**. Ele monitora sua conta no **Logbook of The World (LoTW)** em busca de novas confirmações (QSLs) de satélite e envia alertas em tempo real via **Telegram**.

Além de monitorar QSLs, o bot oferece ferramentas úteis para o dia-a-dia da operação via satélite.

## 🎯 Objetivos

- **Monitoramento Automático**: Verifica periodicamente se novos grids foram confirmados no LoTW.
- **Alertas Instantâneos**: Avisa no Telegram assim que um grid novo ("new one") é confirmado.
- **Visualização de Progresso**: Gera mapas visuais mostrando as áreas que você já tem confirmadas.
- **Utilidade**: Verifica atualização de elementos keplerianos (TLE) e permite consultas rápidas de indicativos.

## 🚀 Funcionalidades

- **`/grids`**: Exibe relatório estatístico dos grids confirmados.
- **`/map`**: Mapa visual. 🟩 **Verde**: Confirmado. 🔲 **Borda**: Gridmaster.
- **`/check <CALL>`**: Verifica rapidamente se você já trabalhou um indicativo.
- **`/tle`**: Verifica se o arquivo de TLE do PU4ELT foi atualizado.
- **`/sync`**: Sincronização inteligente (rápida/incremental).
- **`/sync full`**: Força uma sincronização completa (baixa todo histórico).
- **`/stats`**: Dashboard completo de estatísticas (Grids, Sats, DXCC, etc).
- **`/help`**: Exibe a lista de comandos.

## 🛠️ Instalação

### Pré-requisitos
- Python 3.7 ou superior.
- Uma conta no [LoTW (ARRL)](https://lotw.arrl.org/).
- Um Bot no Telegram (fale com o @BotFather para criar um e pegar o Token).

### Passo a Passo

1. **Clone o repositório**:
   ```bash
   git clone https://github.com/seu-usuario/lotw-monitor.git
   cd lotw-monitor
   ```



2. **Instale as dependências**:
   ```bash
   pip install -r requirements.txt
   ```
   *(Nota: Se der erro de permissão ou ambiente gerenciado, tente usar `sudo pip install -r requirements.txt --break-system-packages`)*

3. **Configure as credenciais**:
   - Renomeie o arquivo de exemplo:
     ```bash
     cp .env.example .env
     ```
   - Edite o arquivo `.env` com seus dados:
     ```ini
     TELEGRAM_BOT_TOKEN="SEU_TOKEN_DO_TELEGRAM"
     TELEGRAM_CHAT_ID="SEU_ID_NUMERICO"
     LOTW_USERNAME="SEU_CALLSIGN"
     LOTW_PASSWORD="SUA_SENHA_LOTW"
     ```

> **Nota Importante**: O arquivo `.env` contém suas senhas e por isso é ignorado pelo Git (não sobe para o GitHub) por segurança. Use o `.env.example` como modelo para criar o seu.

## ▶️ Como Rodar


O programa possui dois modos de operação:

### 1. Modo Bot (Recomendado)
Deixa o programa rodando continuamente. Ele responde aos comandos do Telegram e faz verificações periódicas.

```bash
python3 main.py --mode bot
```

### 2. Modo Verificação Única (Cron)
Roda apenas uma vez, verifica se há novidades, envia o alerta (se houver) e encerra. Ideal para ser agendado no `crontab` se você não quiser um bot interativo.

```bash
python3 main.py --mode check
```

---
**Nota**: Na primeira execução do comando `/map`, o bot fará o download de uma imagem base do mapa-múndi, o que pode levar alguns segundos. As execuções seguintes serão instantâneas.
