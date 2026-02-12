import re
import os
import logging
import requests
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# --- CONFIGURATION ---
TELEGRAM_TOKEN = '8556710977:AAEz5sBHsH8Rt3xEA6UuyiF_6-1-EcLvW6A'
RENDER_API_KEY = 'rnd_FvfIjIejEsKjFC8dn4oxawV6PRnq'
RENDER_URL = "https://api.render.com/v1"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DUMMY SERVER FOR RENDER HEALTH CHECK ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active.")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# --- RENDER API HELPERS ---
def get_headers():
    return {"Authorization": f"Bearer {RENDER_API_KEY}", "Accept": "application/json"}

# --- LOGIC FUNCTIONS (The "Small Functions") ---

async def get_service_info(svc_id):
    r = requests.get(f"{RENDER_URL}/services/{svc_id}", headers=get_headers())
    if r.status_code == 200:
        svc = r.json()
        details = svc.get('serviceDetails', {})
        
        # Formatting the response based on your example
        info = (
            f"<b>📄 Service Info: {svc['name']}</b>\n" + "—" * 15 + "\n"
            f"<b>Status:</b> {'🟢 Active' if svc['suspended'] == 'not_suspended' else '🔴 Suspended'}\n"
            f"<b>Plan:</b> <code>{details.get('plan', 'N/A')}</code>\n"
            f"<b>Region:</b> <code>{details.get('region', 'N/A')}</code>\n"
            f"<b>Runtime:</b> <code>{details.get('runtime', 'N/A')}</code>\n"
            f"<b>Branch:</b> <code>{svc.get('branch', 'main')}</code>\n"
            f"<b>Auto-Deploy:</b> <code>{svc.get('autoDeploy', 'yes')}</code>\n\n"
            f"<b>🛠 Build Command:</b>\n<code>{details.get('envSpecificDetails', {}).get('buildCommand', 'N/A')}</code>\n\n"
            f"<b>🚀 Start Command:</b>\n<code>{details.get('envSpecificDetails', {}).get('startCommand', 'N/A')}</code>\n\n"
            f"<b>📅 Updated:</b> <code>{svc['updatedAt'][:10]}</code>"
        )
        return info
    return f"❌ Error: {r.status_code}"

async def trigger_deploy(svc_id):
    r = requests.post(f"{RENDER_URL}/services/{svc_id}/deploys", headers=get_headers())
    return "🚀 <b>Deploy triggered!</b>" if r.status_code == 201 else f"❌ Error: {r.text}"

async def cancel_last_deploy(svc_id):
    # Step 1: Get the last deploy ID
    list_url = f"{RENDER_URL}/services/{svc_id}/deploys?limit=1"
    res = requests.get(list_url, headers=get_headers())
    
    if res.status_code == 200:
        deploys = res.json()
        if not deploys:
            return "❌ No deployment found to cancel."
        
        deploy_id = deploys[0]['deploy']['id']
        current_status = deploys[0]['deploy']['status']
        
        # Optional check: If it's already finished, we can't cancel it
        if current_status in ["live", "build_failed", "canceled"]:
            return f"⚠️ Cannot cancel. Last deploy is already <code>{current_status}</code>."

        # Step 2: Trigger the cancel request
        cancel_url = f"{RENDER_URL}/services/{svc_id}/deploys/{deploy_id}/cancel"
        cancel_res = requests.post(cancel_url, headers=get_headers())
        
        if cancel_res.status_code == 200:
            return f"🛑 <b>Deploy Cancelled!</b>\nID: <code>{deploy_id}</code>"
        else:
            return f"❌ Failed to cancel"
            
    return f"❌ Error fetching deploy ID: {res.status_code}"
    
async def get_last_deploy(svc_id):
    r = requests.get(f"{RENDER_URL}/services/{svc_id}/deploys?limit=1", headers=get_headers())
    if r.status_code == 200:
        deploy = r.json()
        if not deploy:
            return "No deployment history found for this service."
        
        # Accessing the first item based on your API example
        d = deploy[0]['deploy']
        commit = d.get('commit', {})
        
        status_emoji = "✅" if d['status'] == "live" else "⏳" if d['status'] in ["build in progress", "pre_deploying"] else "❌"
        
        info = (
            f"<b>🚀 Last Deploy Info</b>\n" + "—" * 15 + "\n"
            f"<b>Status:</b> {status_emoji} <code>{d['status']}</code>\n"
            f"<b>ID:</b> <code>{d['id']}</code>\n"
            f"<b>Trigger:</b> <code>{d['trigger']}</code>\n\n"
            f"<b>📝 Commit Message:</b>\n<i>{commit.get('message', 'N/A')}</i>\n\n"
            f"<b>🆔 Commit ID:</b>\n<code>{commit.get('id', 'N/A')[:7]}</code>\n\n"
            f"<b>⏱ Finished:</b> <code>{d.get('finishedAt', 'N/A')}</code>"
        )
        return info
    return f"❌ Error fetching deploy info: {r.status_code}"

async def fetch_env_vars(svc_id):
    r = requests.get(f"{RENDER_URL}/services/{svc_id}/env-vars", headers=get_headers())
    if r.status_code == 200:
        vars_list = "\n".join([f"<b>{v['envVar']['key']}:</b> <code>{v['envVar']['value']}</code>\n" for v in r.json()])
        return f"<b>🔑 Env Vars:</b>\n\n{vars_list}" if vars_list else "No variables found."
    return f"❌ Error fetching env: {r.status_code}"

async def update_env_variable(svc_id, text_input):
    # Expected format: "KEY = VALUE"
    if "=" not in text_input:
        return "❌ Invalid format. Please use: <code>KEY = VALUE</code>"
    
    key, value = [x.strip() for x in text_input.split("=", 1)]
    
    # Render API path for a specific key
    url = f"{RENDER_URL}/services/{svc_id}/env-vars/{key}"
    
    payload = {"value": value}
    
    # We add Content-Type: application/json here
    headers = get_headers()
    headers["Content-Type"] = "application/json"
    
    r = requests.put(url, json=payload, headers=headers)
    
    if r.status_code == 200:
        return f"✅ Successfully set <code>{key}</code> to <code>{value}</code>"
    else:
        return f"❌ Failed to update: {r.text}"
async def delete_env_variable(svc_id, key):
    # Remove whitespace just in case
    key = key.strip()
    url = f"{RENDER_URL}/services/{svc_id}/env-vars/{key}"
    
    r = requests.delete(url, headers=get_headers())
    
    if r.status_code == 204:
        return f"🗑 <b>Deleted:</b> <code>{key}</code> from <code>{svc_id}</code>"
    elif r.status_code == 404:
        return f"❌ Variable <code>{key}</code> not found on this service."
    else:
        return f"❌ Failed to delete: {r.text}"
                  
async def toggle_suspension(svc_id, action):
    # action is either 'suspend' or 'resume'
    r = requests.post(f"{RENDER_URL}/services/{svc_id}/{action}", headers=get_headers())
    status_text = "Suspended ⏸" if action == "suspend" else "Resumed ▶️"
    return f"✅ Service {status_text}" if r.status_code == 202 else f"❌ {action} failed: {r.text}"

async def handle_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return

    prompt_text = update.message.reply_to_message.text
    
    # Extract Service ID
    import re
    match = re.search(r"srv-[a-z0-9]+", prompt_text)
    if not match:
        return
    
    svc_id = match.group(0)
    user_input = update.message.text

    # Logic for Updating
    if "variables" in prompt_text:
        result_msg = await update_env_variable(svc_id, user_input)
        await update.message.reply_text(result_msg, parse_mode="HTML")
        
    # Logic for Deleting
    elif "DELETE" in prompt_text:
        result_msg = await delete_env_variable(svc_id, user_input)
        await update.message.reply_text(result_msg, parse_mode="HTML")

# --- COMMAND HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point command."""
    await update.message.reply_html(
        "<b>🌐 Render Manager Bot</b>\n\n"
        "• /services - List all services & URLs\n"
        "• /deploy - Select a service to deploy\n"
        "• /suspend - Select a service to suspend\n"
        "• /resume - Select a service to resume\n"
        "• /env - View service environment variables"
    )
    
async def list_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = requests.get(f"{RENDER_URL}/services?limit=50", headers=get_headers())
    if res.status_code == 200:
        full_message = "<b>📋 Render Services List</b>\n\n"
        for item in res.json():
            svc = item['service']
            details = svc.get('serviceDetails', {})
            public_url = details.get('url', 'No public URL')
            dash_url = svc.get('serviceDetailsUrl', f"https://dashboard.render.com/web/{svc['id']}")
            status_emoji = "🟢" if svc['suspended'] == "not_suspended" else "🔴"
            
            full_message += (f"{status_emoji} <b>{svc['name']}</b>\n"
                            f"ID: <code>{svc['id']}</code>\n"
                            f"🔗 Service url: {public_url}\n"
                            f"🔗 <a href='{dash_url}'>View on Render</a>\n\n")
                            
        await update.message.reply_text(full_message, parse_mode="HTML", disable_web_page_preview=True)

async def action_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command = update.message.text.replace("/", "").lower()
    res = requests.get(f"{RENDER_URL}/services", headers=get_headers())
    if res.status_code == 200:
        keyboard = [[InlineKeyboardButton(item['service']['name'], callback_data=f"{command}_{item['service']['id']}")] for item in res.json()]
        await update.message.reply_text("<b>Select service:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# --- MAIN INTERACTION ROUTER ---

async def handle_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, svc_id = query.data.split("_", 1)
    
    # Route to the appropriate small function
    if action == "serviceinfo":
        msg = await get_service_info(svc_id)
    elif action == "deploy":
        msg = await trigger_deploy(svc_id)
    elif action == "canceldeploy":
        msg = await cancel_last_deploy(svc_id)
    elif action == "lastdeploy":
        msg = await get_last_deploy(svc_id)
    elif action in ["suspend", "resume"]:
        msg = await toggle_suspension(svc_id, action)
    elif action == "env":
        msg = await fetch_env_vars(svc_id)
    elif action == "updatenv":
        # We define msg here so the 'await query.message.reply_text(msg...)' at the bottom doesn't crash
        msg = "If you want to add or update more than one variable, you have to do it one by one by sending\n/updatenv\n\n<b>⚠️ N.B. </b>After updating the environment variables via API, your web service won't be deployed automatically even if auto deploy is turned on. So, you have to do it manually."        
        # We use ForceReply so the user's phone automatically opens the keyboard to reply
        await query.message.reply_text(
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n✍️ Reply to this message with the <b>environment variables</b> you want to add or update.\n<b>Format: </b>KEY = VALUE",
            reply_markup=ForceReply(selective=True),
            parse_mode="HTML"
        )
    elif action == "deletenv":
        msg = ""
        await query.message.reply_text(
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n✍️ Reply to this message with the <b>KEY</b> you want to <b>DELETE</b>.",
            reply_markup=ForceReply(selective=True),
            parse_mode="HTML"
        )
    else:
        msg = "Unknown action."

    await query.message.reply_text(msg, parse_mode="HTML")

# --- MAIN RUNNER ---

def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("services", list_services))
    for cmd in ["serviceinfo", "deploy", "canceldeploy", "lastdeploy", "suspend", "resume", "env", "updatenv", "deletenv"]:
        app.add_handler(CommandHandler(cmd, action_picker))
    # Add this with your other handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply_text))
    app.add_handler(CallbackQueryHandler(handle_interaction))
    app.run_polling()

if __name__ == "__main__":
    main()