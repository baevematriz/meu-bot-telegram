# 🤖 Agente IA no Telegram

Assistente pessoal com IA (Claude) no Telegram. Responde perguntas, faz resumos, ajuda com tarefas do dia a dia.

---

## 🚀 Passo a Passo para Colocar no Ar

### 1. Criar o bot no Telegram (BotFather)

1. Abra o Telegram e pesquise por **@BotFather**
2. Envie `/newbot`
3. Escolha um nome para o bot (ex: "Meu Assistente IA")
4. Escolha um username (ex: `meu_assistente_ia_bot`) — precisa terminar em `bot`
5. O BotFather vai te dar um **TOKEN** — guarde ele!

---

### 2. Pegar sua chave da API do Claude (Anthropic)

1. Acesse: https://console.anthropic.com
2. Crie uma conta (gratuita para começar)
3. Vá em **API Keys** e crie uma nova chave
4. Guarde a chave!

---

### 3. Hospedar no Railway (grátis)

1. Acesse: https://railway.app e crie uma conta
2. Clique em **New Project → Deploy from GitHub repo**
3. Faça upload dos arquivos deste projeto (ou conecte um repositório GitHub)
4. Vá em **Variables** e adicione:
   - `TELEGRAM_TOKEN` → o token do BotFather
   - `ANTHROPIC_API_KEY` → sua chave da Anthropic
5. O Railway vai iniciar o bot automaticamente!

---

### 4. Testar localmente (opcional)

```bash
# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
export TELEGRAM_TOKEN="seu_token_aqui"
export ANTHROPIC_API_KEY="sua_chave_aqui"

# Rodar o bot
python bot.py
```

---

## 💬 Comandos do Bot

| Comando | Descrição |
|---------|-----------|
| `/start` | Iniciar / reiniciar o bot |
| `/ajuda` | Ver todos os comandos |
| `/limpar` | Apagar histórico da conversa |

---

## 🛠️ Personalizar o Agente

Para mudar o comportamento do bot, edite o `SYSTEM_PROMPT` no arquivo `bot.py`.

Exemplos de personalização:
- Mudar o nome do assistente
- Focar em um tema específico (ex: receitas, finanças, fitness)
- Mudar o tom (mais formal, mais divertido, etc.)
