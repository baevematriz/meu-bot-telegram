import os
import logging
import io
import dropbox
from dropbox.exceptions import ApiError
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
DROPBOX_ACCESS_TOKEN = os.environ.get("DROPBOX_ACCESS_TOKEN", "")

# Memória de conversa por usuário
conversation_history: dict[int, list] = {}

# Pasta atual do Dropbox por usuário
dropbox_dir: dict[int, str] = {}

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

# ─── Helpers Dropbox ─────────────────────────────────────────────

def get_dbx():
    return dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)

def get_db_dir(user_id: int) -> str:
    return dropbox_dir.get(user_id, "")

def db_full_path(user_id: int, name: str) -> str:
    d = get_db_dir(user_id)
    return f"/{name}" if d == "" else f"{d}/{name}"

def format_entries(entries) -> str:
    pastas = [f"📁 {e.name}" for e in entries if isinstance(e, dropbox.files.FolderMetadata)]
    arquivos = [f"📄 {e.name}" for e in entries if isinstance(e, dropbox.files.FileMetadata)]
    return "\n".join(pastas + arquivos) or "(vazio)"

# ─── Handlers ────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conversation_history[user.id] = []
    await update.message.reply_text(
        f"Olá, {user.first_name}! 👋\n\n"
        "Sou seu assistente pessoal com IA.\n\n"
        "— GERAL —\n"
        "/ajuda — ver todos os comandos\n"
        "/limpar — limpar histórico\n\n"
        "— DROPBOX ☁️ —\n"
        "/dropbox — acessar raiz\n"
        "/dls — listar pasta atual\n"
        "/dcd <pasta> — navegar\n"
        "/dpwd — ver pasta atual\n"
        "/dread <arquivo> — ler arquivo\n"
        "/dget <arquivo> — baixar arquivo\n"
        "/dmkdir <nome> — criar pasta\n"
        "/drm <nome> — deletar\n"
        "/dmv <origem> > <destino> — mover/renomear\n"
        "/dlink <arquivo> — link de compartilhamento\n"
        "/dfind <nome> — buscar\n"
        "📎 Envie um arquivo → salva na pasta atual"
    )


async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Comandos disponíveis:*\n\n"
        "*Geral:*\n"
        "/start — Reiniciar o bot\n"
        "/limpar — Limpar histórico\n"
        "/ajuda — Esta mensagem\n\n"
        "*Dropbox ☁️:*\n"
        "/dropbox — Raiz do Dropbox\n"
        "/dls — Listar pasta atual\n"
        "/dcd <pasta> — Navegar\n"
        "/dpwd — Pasta atual\n"
        "/dread <arquivo> — Ler arquivo\n"
        "/dget <arquivo> — Baixar arquivo\n"
        "/dmkdir <nome> — Criar pasta\n"
        "/drm <nome> — Deletar\n"
        "/dmv <origem> > <destino> — Mover/renomear\n"
        "/dlink <arquivo> — Link de compartilhamento\n"
        "/dfind <nome> — Buscar\n"
        "📎 Envie um arquivo → upload para pasta atual",
        parse_mode="Markdown",
    )


async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("🧹 Histórico apagado!")


# ─── Dropbox Commands ─────────────────────────────────────────────

async def cmd_dropbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    dropbox_dir[user_id] = ""
    try:
        dbx = get_dbx()
        res = dbx.files_list_folder("")
        texto = f"☁️ Dropbox — Raiz\n\n{format_entries(res.entries)}"
        await update.message.reply_text(texto[:4000])
    except ApiError as e:
        await update.message.reply_text(f"❌ Erro: {e}")


async def cmd_dls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    d = get_db_dir(user_id)
    try:
        dbx = get_dbx()
        res = dbx.files_list_folder(d)
        label = "/" if d == "" else d
        texto = f"☁️ {label}\n\n{format_entries(res.entries)}"
        await update.message.reply_text(texto[:4000])
    except ApiError as e:
        await update.message.reply_text(f"❌ Erro: {e}")


async def cmd_dpwd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    d = get_db_dir(user_id)
    await update.message.reply_text(f"☁️ {d or '/ (raiz)'}")


async def cmd_dcd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = " ".join(context.args).strip()
    if not args:
        return await update.message.reply_text("Use: /dcd <nome da pasta>")

    d = get_db_dir(user_id)
    if args == "..":
        new_dir = "" if "/" not in d.lstrip("/") else d.rsplit("/", 1)[0]
    elif args == "/":
        new_dir = ""
    else:
        new_dir = f"/{args}" if d == "" else f"{d}/{args}"

    try:
        dbx = get_dbx()
        dbx.files_get_metadata(new_dir)
        dropbox_dir[user_id] = new_dir
        res = dbx.files_list_folder(new_dir)
        label = new_dir or "/"
        texto = f"☁️ {label}\n\n{format_entries(res.entries)}"
        await update.message.reply_text(texto[:4000])
    except ApiError:
        await update.message.reply_text(f"❌ Pasta não encontrada: {args}")


async def cmd_dread(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = " ".join(context.args).strip()
    if not args:
        return await update.message.reply_text("Use: /dread <nome do arquivo>")

    file_path = db_full_path(user_id, args)
    try:
        dbx = get_dbx()
        _, res = dbx.files_download(file_path)
        text = res.content.decode("utf-8", errors="replace")
        preview = text[:3800]
        await update.message.reply_text(f"📄 {args}:\n\n{preview}{'...(cortado)' if len(text) > 3800 else ''}")
    except ApiError as e:
        await update.message.reply_text(f"❌ Erro: {e}")


async def cmd_dget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = " ".join(context.args).strip()
    if not args:
        return await update.message.reply_text("Use: /dget <nome do arquivo>")

    file_path = db_full_path(user_id, args)
    await update.message.reply_text(f"⬇️ Baixando \"{args}\"...")
    try:
        dbx = get_dbx()
        _, res = dbx.files_download(file_path)
        await update.message.reply_document(
            document=io.BytesIO(res.content),
            filename=args
        )
    except ApiError as e:
        await update.message.reply_text(f"❌ Erro: {e}")


async def cmd_dmkdir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = " ".join(context.args).strip()
    if not args:
        return await update.message.reply_text("Use: /dmkdir <nome da pasta>")

    folder_path = db_full_path(user_id, args)
    try:
        dbx = get_dbx()
        dbx.files_create_folder_v2(folder_path)
        await update.message.reply_text(f"✅ Pasta criada: {folder_path}")
    except ApiError as e:
        await update.message.reply_text(f"❌ Erro: {e}")


async def cmd_drm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = " ".join(context.args).strip()
    if not args:
        return await update.message.reply_text("Use: /drm <nome>")

    target = db_full_path(user_id, args)
    try:
        dbx = get_dbx()
        dbx.files_delete_v2(target)
        await update.message.reply_text(f"🗑️ Deletado: {target}")
    except ApiError as e:
        await update.message.reply_text(f"❌ Erro: {e}")


async def cmd_dmv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.split(" ", 1)[1] if len(update.message.text.split(" ", 1)) > 1 else ""
    parts = text.split(">")
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        return await update.message.reply_text("Use: /dmv <origem> > <destino>")

    from_path = db_full_path(user_id, parts[0].strip())
    to_path = db_full_path(user_id, parts[1].strip())
    try:
        dbx = get_dbx()
        dbx.files_move_v2(from_path, to_path)
        await update.message.reply_text(f"✅ Movido: {parts[0].strip()} → {parts[1].strip()}")
    except ApiError as e:
        await update.message.reply_text(f"❌ Erro: {e}")


async def cmd_dlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = " ".join(context.args).strip()
    if not args:
        return await update.message.reply_text("Use: /dlink <nome do arquivo>")

    file_path = db_full_path(user_id, args)
    try:
        dbx = get_dbx()
        try:
            res = dbx.sharing_create_shared_link_with_settings(file_path)
            await update.message.reply_text(f"🔗 Link: {res.url}")
        except ApiError:
            res = dbx.sharing_list_shared_links(path=file_path, direct_only=True)
            if res.links:
                await update.message.reply_text(f"🔗 Link: {res.links[0].url}")
            else:
                await update.message.reply_text("❌ Não foi possível gerar o link.")
    except ApiError as e:
        await update.message.reply_text(f"❌ Erro: {e}")


async def cmd_dfind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = " ".join(context.args).strip()
    if not args:
        return await update.message.reply_text("Use: /dfind <nome>")

    await update.message.reply_text(f"🔍 Buscando \"{args}\" no Dropbox...")
    try:
        dbx = get_dbx()
        res = dbx.files_search_v2(args)
        matches = res.matches
        if not matches:
            return await update.message.reply_text(f"❌ Nada encontrado para \"{args}\".")
        lista = []
        for m in matches[:30]:
            meta = m.metadata.get_metadata()
            icon = "📁" if isinstance(meta, dropbox.files.FolderMetadata) else "📄"
            lista.append(f"{icon} {meta.path_display}")
        await update.message.reply_text(f"🔍 Resultados:\n\n" + "\n".join(lista))
    except ApiError as e:
        await update.message.reply_text(f"❌ Erro: {e}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    doc = update.message.document
    d = get_db_dir(user_id)
    dest = f"/{doc.file_name}" if d == "" else f"{d}/{doc.file_name}"

    await update.message.reply_text(f"⬆️ Enviando \"{doc.file_name}\" para o Dropbox...")
    try:
        file = await context.bot.get_file(doc.file_id)
        content = await file.download_as_bytearray()
        dbx = get_dbx()
        dbx.files_upload(bytes(content), dest, mode=dropbox.files.WriteMode.overwrite)
        await update.message.reply_text(f"✅ Salvo em: {dest}")
    except ApiError as e:
        await update.message.reply_text(f"❌ Erro no upload: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": user_text})

    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

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

        conversation_history[user_id].append(
            {"role": "assistant", "content": assistant_reply}
        )

        await update.message.reply_text(assistant_reply)

    except Exception as e:
        logger.error(f"Erro ao chamar a API: {e}")
        await update.message.reply_text(
            "⚠️ Ops, tive um problema ao processar sua mensagem. Tente novamente."
        )


# ─── Main ────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(CommandHandler("limpar", limpar))

    # Dropbox
    app.add_handler(CommandHandler("dropbox", cmd_dropbox))
    app.add_handler(CommandHandler("dls", cmd_dls))
    app.add_handler(CommandHandler("dpwd", cmd_dpwd))
    app.add_handler(CommandHandler("dcd", cmd_dcd))
    app.add_handler(CommandHandler("dread", cmd_dread))
    app.add_handler(CommandHandler("dget", cmd_dget))
    app.add_handler(CommandHandler("dmkdir", cmd_dmkdir))
    app.add_handler(CommandHandler("drm", cmd_drm))
    app.add_handler(CommandHandler("dmv", cmd_dmv))
    app.add_handler(CommandHandler("dlink", cmd_dlink))
    app.add_handler(CommandHandler("dfind", cmd_dfind))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot iniciado! Aguardando mensagens...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
