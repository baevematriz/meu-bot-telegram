import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import anthropic
from datetime import datetime

# ─── Configuração ────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# Memória de conversa por usuário (em memória simples)
conversation_history: dict[int, list] = {}

SYSTEM_PROMPT = """Você é um assistente pessoal inteligente no Telegram. 
Seu objetivo é ajudar o usuário com:
- Responder perguntas gerais de forma clara e objetiva
- Ajudar com tarefas do dia a dia
- Fazer resumos de textos que o usuário enviar
- Criar lembretes e listas de tarefas
- Dar dicas e sugestões úteis

Responda sempre em português brasileiro, de forma amigável e direta.
Seja conciso — evite respostas longas demais no Telegram.
Use emojis com moderação para deixar as respostas mais agradáveis.

Data e hora atual: {datetime}
"""

# ─── Handlers ────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conversation_history[user.id] = []
    await update.message.reply_text(
        f"Olá, {user.first_name}! 👋\n\n"
        "Sou seu assistente pessoal com IA. Posso te ajudar com:\n\n"
        "• 💬 Responder perguntas\n"
        "• 📝 Fazer resumos\n"
        "• ✅ Criar listas e lembretes\n"
        "• 💡 Dar dicas e sugestões\n\n"
        "É só me mandar uma mensagem! Use /ajuda para ver todos os comandos."
    )


async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Comandos disponíveis:*\n\n"
        "/start — Reiniciar o bot\n"
        "/limpar — Limpar histórico da conversa\n"
        "/resumir — Resumir o próximo texto que você enviar\n"
        "/ajuda — Mostrar esta mensagem\n\n"
        "Ou simplesmente me mande qualquer mensagem! 🚀",
        parse_mode="Markdown",
    )


async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("🧹 Histórico de conversa apagado! Podemos começar de novo.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    # Inicializa histórico se necessário
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    # Adiciona mensagem do usuário ao histórico
    conversation_history[user_id].append({"role": "user", "content": user_text})

    # Mantém no máximo 20 mensagens no histórico
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    # Indicador de digitando...
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        system = SYSTEM_PROMPT.format(
            datetime=datetime.now().strftime("%d/%m/%Y %H:%M")
        )

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system,
            messages=conversation_history[user_id],
        )

        assistant_reply = response.content[0].text

        # Adiciona resposta ao histórico
        conversation_history[user_id].append(
            {"role": "assistant", "content": assistant_reply}
        )

        await update.message.reply_text(assistant_reply)

    except Exception as e:
        logger.error(f"Erro ao chamar a API: {e}")
        await update.message.reply_text(
            "⚠️ Ops, tive um problema ao processar sua mensagem. Tente novamente em instantes."
        )


# ─── Main ────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(CommandHandler("limpar", limpar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot iniciado! Aguardando mensagens...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
