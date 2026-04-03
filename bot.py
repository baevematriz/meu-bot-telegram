import os
import logging
import io
import json
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
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY", "")
DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET", "")
DROPBOX_REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN", "")

conversation_history: dict[int, list] = {}
dropbox_dir: dict[int, str] = {}

SYSTEM_PROMPT = """Você é o CBCAP, assistente pessoal inteligente no Telegram.
Responda sempre em português brasileiro, de forma amigável e direta.
Seja conciso — evite respostas longas demais no Telegram.

Você tem acesso ao Dropbox do usuário através de ferramentas. Quando o usuário pedir para ver arquivos, abrir pastas, ler documentos, baixar ou enviar arquivos, use as ferramentas disponíveis automaticamente — sem pedir para o usuário digitar comandos.

Data e hora atual: {datetime}
"""

# ─── Dropbox Tools ───────────────────────────────────────────────

TOOLS = [
    {
        "name": "listar_arquivos",
        "description": "Lista arquivos e pastas no Dropbox. Use quando o usuário quiser ver seus arquivos, abrir o Dropbox, ver o que tem em uma pasta, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho da pasta no Dropbox. Use string vazia '' para a raiz. Exemplo: '/Documentos' ou ''"
                }
            },
            "required": ["caminho"]
        }
    },
    {
        "name": "ler_arquivo",
        "description": "Lê o conteúdo de um arquivo de texto no Dropbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho completo do arquivo no Dropbox. Exemplo: '/Documentos/notas.txt'"
                }
            },
            "required": ["caminho"]
        }
    },
    {
        "name": "baixar_arquivo",
        "description": "Baixa um arquivo do Dropbox e envia para o usuário no Telegram.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho completo do arquivo no Dropbox."
                }
            },
            "required": ["caminho"]
        }
    },
    {
        "name": "criar_pasta",
        "description": "Cria uma nova pasta no Dropbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho completo da nova pasta. Exemplo: '/Projetos/Novo'"
                }
            },
            "required": ["caminho"]
        }
    },
    {
        "name": "deletar_item",
        "description": "Deleta um arquivo ou pasta do Dropbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho completo do arquivo ou pasta a deletar."
                }
            },
            "required": ["caminho"]
        }
    },
    {
        "name": "mover_item",
        "description": "Move ou renomeia um arquivo ou pasta no Dropbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "origem": {
                    "type": "string",
                    "description": "Caminho de origem."
                },
                "destino": {
                    "type": "string",
                    "description": "Caminho de destino."
                }
            },
            "required": ["origem", "destino"]
        }
    },
    {
        "name": "gerar_link",
        "description": "Gera um link de compartilhamento para um arquivo no Dropbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho completo do arquivo."
                }
            },
            "required": ["caminho"]
        }
    },
    {
        "name": "buscar_arquivos",
        "description": "Busca arquivos ou pastas no Dropbox pelo nome.",
        "input_schema": {
            "type": "object",
            "properties": {
                "termo": {
                    "type": "string",
                    "description": "Termo de busca."
                }
            },
            "required": ["termo"]
        }
    }
]

# ─── Execução das Tools ──────────────────────────────────────────

def get_dbx():
    return dropbox.Dropbox(
        app_key=DROPBOX_APP_KEY,
        app_secret=DROPBOX_APP_SECRET,
        oauth2_refresh_token=DROPBOX_REFRESH_TOKEN
    )

def execute_tool(tool_name: str, tool_input: dict) -> str:
    try:
        dbx = get_dbx()

        if tool_name == "listar_arquivos":
            caminho = tool_input.get("caminho", "")
            res = dbx.files_list_folder(caminho)
            pastas = [f"📁 {e.name}" for e in res.entries if isinstance(e, dropbox.files.FolderMetadata)]
            arquivos = [f"📄 {e.name}" for e in res.entries if isinstance(e, dropbox.files.FileMetadata)]
            label = caminho or "/"
            conteudo = "\n".join(pastas + arquivos) or "(vazio)"
            return f"Pasta: {label}\n\n{conteudo}"

        elif tool_name == "ler_arquivo":
            caminho = tool_input["caminho"]
            _, res = dbx.files_download(caminho)
            text = res.content.decode("utf-8", errors="replace")
            return text[:3000] + ("...(cortado)" if len(text) > 3000 else "")

        elif tool_name == "criar_pasta":
            caminho = tool_input["caminho"]
            dbx.files_create_folder_v2(caminho)
            return f"Pasta criada: {caminho}"

        elif tool_name == "deletar_item":
            caminho = tool_input["caminho"]
            dbx.files_delete_v2(caminho)
            return f"Deletado: {caminho}"

        elif tool_name == "mover_item":
            dbx.files_move_v2(tool_input["origem"], tool_input["destino"])
            return f"Movido: {tool_input['origem']} → {tool_input['destino']}"

        elif tool_name == "gerar_link":
            caminho = tool_input["caminho"]
            try:
                res = dbx.sharing_create_shared_link_with_settings(caminho)
                return f"Link: {res.url}"
            except ApiError:
                res = dbx.sharing_list_shared_links(path=caminho, direct_only=True)
                if res.links:
                    return f"Link: {res.links[0].url}"
                return "Não foi possível gerar o link."

        elif tool_name == "buscar_arquivos":
            termo = tool_input["termo"]
            res = dbx.files_search_v2(termo)
            if not res.matches:
                return f"Nada encontrado para '{termo}'."
            lista = []
            for m in res.matches[:20]:
                meta = m.metadata.get_metadata()
                icon = "📁" if isinstance(meta, dropbox.files.FolderMetadata) else "📄"
                lista.append(f"{icon} {meta.path_display}")
            return "\n".join(lista)

        return "Ferramenta não reconhecida."

    except ApiError as e:
        return f"Erro no Dropbox: {e}"
    except Exception as e:
        return f"Erro: {e}"

# ─── Handlers ────────────────────────────────────────────────────

async def cmd_autorizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from dropbox import DropboxOAuth2FlowNoRedirect
    auth_flow = DropboxOAuth2FlowNoRedirect(
        DROPBOX_APP_KEY,
        DROPBOX_APP_SECRET,
        token_access_type='offline'
    )
    url = auth_flow.start()
    context.user_data["auth_flow"] = auth_flow
    await update.message.reply_text(
        f"🔐 *Autorizar Dropbox*\n\n"
        f"1. Acessa este link:\n{url}\n\n"
        f"2. Clica em *Permitir*\n"
        f"3. Copia o código que aparecer\n"
        f"4. Envia aqui: `/ativar CODIGO`",
        parse_mode="Markdown"
    )


async def cmd_ativar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from dropbox import DropboxOAuth2FlowNoRedirect
    codigo = " ".join(context.args).strip()
    if not codigo:
        return await update.message.reply_text("Use: /ativar <codigo>")

    auth_flow = context.user_data.get("auth_flow")
    if not auth_flow:
        auth_flow = DropboxOAuth2FlowNoRedirect(
            DROPBOX_APP_KEY,
            DROPBOX_APP_SECRET,
            token_access_type='offline'
        )

    try:
        result = auth_flow.finish(codigo)
        refresh_token = result.refresh_token
        await update.message.reply_text(
            f"✅ Dropbox autorizado!\n\n"
            f"Agora adicione esta variável no Railway:\n\n"
            f"`DROPBOX_REFRESH_TOKEN`\n`{refresh_token}`\n\n"
            f"Depois faça um redeploy e o Dropbox funcionará permanentemente! 🎉",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao ativar: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conversation_history[user.id] = []
    await update.message.reply_text(
        f"Olá, {user.first_name}! 👋\n\n"
        "Sou o CBCAP, seu assistente pessoal com acesso ao Dropbox.\n\n"
        "Pode falar naturalmente:\n"
        "• \"Mostra meus arquivos do Dropbox\"\n"
        "• \"Abre a pasta Documentos\"\n"
        "• \"Lê o arquivo notas.txt\"\n"
        "• \"Busca por contratos\"\n"
        "• \"Gera um link para o relatório.pdf\"\n\n"
        "Ou envie um arquivo aqui para salvar no Dropbox! 📎"
    )


async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("🧹 Histórico apagado!")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    await update.message.reply_text(f"⬆️ Enviando \"{doc.file_name}\" para o Dropbox...")
    try:
        file = await context.bot.get_file(doc.file_id)
        content = await file.download_as_bytearray()
        dbx = get_dbx()
        dest = f"/{doc.file_name}"
        dbx.files_upload(bytes(content), dest, mode=dropbox.files.WriteMode.overwrite)
        await update.message.reply_text(f"✅ Salvo em: {dest}")
    except Exception as e:
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
        system = SYSTEM_PROMPT.format(datetime=datetime.now().strftime("%d/%m/%Y %H:%M"))
        messages = list(conversation_history[user_id])

        # Loop de tool use
        while True:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                system=system,
                tools=TOOLS,
                messages=messages,
            )

            # Se parou por tool_use, executa as ferramentas
            if response.stop_reason == "tool_use":
                # Adiciona resposta do assistente ao histórico
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        await context.bot.send_chat_action(
                            chat_id=update.effective_chat.id, action="typing"
                        )
                        result = execute_tool(block.name, block.input)

                        # Se for download, envia o arquivo separadamente
                        if block.name == "baixar_arquivo":
                            try:
                                dbx = get_dbx()
                                caminho = block.input["caminho"]
                                _, res = dbx.files_download(caminho)
                                nome = caminho.split("/")[-1]
                                await update.message.reply_document(
                                    document=io.BytesIO(res.content),
                                    filename=nome
                                )
                                result = f"Arquivo '{nome}' enviado com sucesso."
                            except Exception as e:
                                result = f"Erro ao baixar: {e}"

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "user", "content": tool_results})

            else:
                # Resposta final em texto
                final_reply = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_reply += block.text

                if final_reply:
                    # Salva no histórico apenas a resposta de texto
                    conversation_history[user_id].append(
                        {"role": "assistant", "content": final_reply}
                    )
                    await update.message.reply_text(final_reply)
                break

    except Exception as e:
        logger.error(f"Erro: {e}")
        await update.message.reply_text("⚠️ Ops, tive um problema. Tente novamente.")


# ─── Main ────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("limpar", limpar))
    app.add_handler(CommandHandler("autorizar", cmd_autorizar))
    app.add_handler(CommandHandler("ativar", cmd_ativar))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot iniciado! Aguardando mensagens...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
