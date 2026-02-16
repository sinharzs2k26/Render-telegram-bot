import re
import os
import logging
import requests
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
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
    httpd = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    httpd.serve_forever()

# --- RENDER API HELPERS ---
def get_headers(context: ContextTypes.DEFAULT_TYPE):
    """Retrieves the API key stored for this specific user."""
    api_key = context.user_data.get("api_key")
    if not api_key:
        return None
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

# --- COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcomes the user and introduces the bot."""
    user = update.effective_user
    welcome_text = (
        "<b>🤖 Render Management Bot</b>\n\n"
        f"<b>👋 Hello, {user.first_name}!</b> I am your mobile command center for Render.com, a cloud application hosting platform.\n\n"
        "<b>🔻 I can help you directly from Telegram -</b>\n"
        "• Manage and update services\n"
        "• Update environment variables\n"
        "• Monitor deployments.\n"
        "• See service logs.\n\n"
        "👉 Send /help to see the available commands and their usages.\n\n"
        "<i>📌 You have to <b>/login</b> with your <b>Render API key</b> first, otherwise the management commands won't work.</i>"
    )
    await update.message.reply_html(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all commands and how to use them."""
    help_text = (
        "📌 This bot is made to control Render's <b>web services</b> only.\n\n"
        "<b>🛠 Available Commands & Usage</b>\n\n"
        "• /accountinfo - See your Render account information.\n\n"
        "<b>📋 Services</b>\n"
        "• /services - List all services with status and URLs.\n"
        "• /serviceinfo - View deep-dive details of a service.\n"
        "• /rename - Change name of a service.\n"
        "• /changestartcmd - Change start command of a service.\n"
        "• /changebuildcmd - Change build command of a service.\n"
        "• /buildfilter - Add ignored paths whose changes will not trigger a new build.\n"
        "• /deleteservice - Permanently delete a service.\n\n"
        "<b>🚀 Deployments</b>\n"
        "• /deploy - Trigger a new manual deployment.\n"
        "• /deployinfo - Show the status of the most recent deploy.\n"
        "• /canceldeploy - Stop an in-progress deployment.\n"
        "• /toggleautodeploy - Turn ON or OFF auto deploy of a service.\n"
        "• /logs - See logs of a deployed service.\n"
        "• /suspend - Pause a running service.\n"
        "• /resume - Start a suspended service.\n\n"
        "<b>🔑 Environment (Env) Vars</b>\n"
        "• /listenv - View all keys and values for a service.\n"
        "• /updatenv - Add or update a variable.\n"
        "• /deletenv - Delete a specific variable by its key.\n"
        "• /updatefullenv - Add multiple variables or bulk replace all with a new list.\n\n"
        "<i>Note: Most commands will ask you to select a service first.</i>"
    )
    await update.message.reply_html(help_text)
    
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates the login process by asking for the key."""
    if "api_key" in context.user_data:
        await update.message.reply_text("You were logged in already!")
    else:
        await update.message.reply_text(
            "<b>🔑 Login to Render</b>\n"
            "Please provide your API key to use the bot: <code>rnd_xxxxxxxxxxxx</code>\n\n"
            "📌 <i>Your API key will be pinned for your quick access if the bot server restarts and so your key gets cleared.</i>",
            reply_markup=ForceReply(selective=True),
            parse_mode="HTML"
        )

async def get_account_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    headers = get_headers(context)
    if not headers:
        await update.message.reply_text("❌ You are not logged in.\nSend /login")
        
    url = f"{RENDER_URL}/users"
    r = requests.get(url, headers=headers)
    
    if r.status_code == 200:
        data = r.json()
        name = data.get("name", "N/A")
        email = data.get("email", "N/A")
        
        info_message = ("👤 <b>Render Account Info</b>\n\n"
                        f"<b>Name:</b> {name}\n"
                        f"<b>Email:</b> <code>{email}</code>\n\n")
        await update.message.reply_html(info_message)
        
async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clears the key and unpins the quick-access message."""
    if "api_key" in context.user_data:
        del context.user_data["api_key"]
        try:
            await context.bot.unpin_all_chat_messages(chat_id=update.effective_chat.id)
        except:
            pass
        await update.message.reply_text("🔒 <b>Logged out.</b> Key cleared and unpinned.", parse_mode="HTML")
    else:
        await update.message.reply_text("You weren't logged in!")

async def list_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    headers = get_headers(context)
    if not headers:
        await update.message.reply_text("❌ You are not logged in.\nSend /login")
        
    res = requests.get(f"{RENDER_URL}/services?limit=50", headers=headers)
    if res.status_code == 200:
        full_message = "<b>📋 Render Services List</b>\n" + "—" * 14 + "\n"
        for item in res.json():
            svc = item['service']
            details = svc.get('serviceDetails', {})
            public_url = details.get('url', 'No public URL')
            dash_url = svc.get('serviceDetailsUrl', f"https://dashboard.render.com/web/{svc['id']}")
            status_emoji = "🟢" if svc['suspended'] == "not_suspended" else "🔴"
            
            full_message += (f"<u>{status_emoji} <b>{svc['name']}</b></u>\n"
                            f"<b>Service ID: </b><code>{svc['id']}</code>\n\n"
                            f"<b>🔗 Service url: </b>{public_url}\n\n"
                            f"👉 <a href='{dash_url}'>Tap here to view on <b>Render Dashboard</b></a>\n\n\n")
        await update.message.reply_text(full_message, parse_mode="HTML", disable_web_page_preview=True)
        
# --- FUNCTIONS ---
async def get_service_info(svc_id, context):
    headers = get_headers(context)
    r = requests.get(f"{RENDER_URL}/services/{svc_id}", headers=headers)
    if r.status_code == 200:
        svc = r.json()
        details = svc.get('serviceDetails', {})
        
        info = (
            f"<b>📄 Service Info: {svc['name']}</b>\n" + "—" * 20 + "\n"
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

async def trigger_deploy(svc_id, context):
    headers = get_headers(context)
    r = requests.post(f"{RENDER_URL}/services/{svc_id}/deploys", headers=headers)
    return "🚀 <b>Deploy triggered!</b>\nSend /logs to see runtime logs." if r.status_code == 201 else f"❌ Error: {r.text}"

async def cancel_last_deploy(svc_id, context):
    headers = get_headers(context)
    list_url = f"{RENDER_URL}/services/{svc_id}/deploys?limit=1"
    res = requests.get(list_url, headers=headers)
    
    if res.status_code == 200:
        deploys = res.json()
        if not deploys:
            return "❌ No deployment found to cancel."
        
        deploy_id = deploys[0]['deploy']['id']
        current_status = deploys[0]['deploy']['status']

        if current_status in ["live", "build_failed", "canceled"]:
            return f"⚠️ Cannot cancel. Last deploy is already <code>{current_status}</code>."
            
        cancel_url = f"{RENDER_URL}/services/{svc_id}/deploys/{deploy_id}/cancel"
        cancel_res = requests.post(cancel_url, headers=headers)
        
        if cancel_res.status_code == 200:
            return f"🛑 <b>Deploy Cancelled!</b>\nID: <code>{deploy_id}</code>"
        else:
            return f"❌ Failed to cancel"
            
    return f"❌ Error fetching deploy ID: {res.status_code}"
    
async def get_last_deploy(svc_id, context):
    headers = get_headers(context)
    r = requests.get(f"{RENDER_URL}/services/{svc_id}/deploys?limit=1", headers=headers)
    if r.status_code == 200:
        deploy = r.json()
        if not deploy:
            return "No deployment history found for this service."
            
        d = deploy[0]['deploy']
        commit = d.get('commit', {})
        
        status_emoji = "✅" if d['status'] == "live" else "❌" if d['status'] in ["build_failed", "canceled"] else "⏳"
        
        info = (
            f"<b>🚀 Last Deploy Info</b>\n" + "—" * 10 + "\n"
            f"<b>Status:</b> {status_emoji} <code>{d['status']}</code>\n"
            f"<b>ID:</b> <code>{d['id']}</code>\n"
            f"<b>Trigger:</b> <code>{d['trigger']}</code>\n\n"
            f"<b>📝 Commit Message:</b>\n<i>{commit.get('message', 'N/A')}</i>\n\n"
            f"<b>🆔 Commit ID:</b>\n<code>{commit.get('id', 'N/A')[:7]}</code>\n\n"
            f"<b>⏱ Finished:</b> <code>{d.get('finishedAt', 'N/A')}</code>"
        )
        return info
    return f"❌ Error fetching deploy info: {r.status_code}"

async def toggle_auto_deploy(svc_id, status, context):
    headers = get_headers(context)
    payload = {"autoDeploy": "yes" if status == "on" else "no"}
    url = f"{RENDER_URL}/services/{svc_id}"
    r = requests.patch(url, json=payload, headers=headers)
    
    if r.status_code == 200:
        icon = "✅" if status == "on" else "🛑"
        return f"{icon} <b>Auto-Deploy</b> is now <b>{status.upper()}</b> for your service."
    else:
        return f"❌ Failed to update: {r.text}"
        
async def get_service_logs(svc_id, context):
    headers = get_headers(context)
    owner_res = requests.get(f"{RENDER_URL}/owners", headers=headers)
    if owner_res.status_code != 200:
        return "❌ Failed to retrieve Owner ID."
    
    owners_data = owner_res.json()
    if not owners_data:
        return "❌ No owner found for this account."
    owner_id = owners_data[0]['owner']['id']
    log_url = f"{RENDER_URL}/logs"
    params = {
        "ownerId": owner_id,
        "direction": "backward",
        "resource": svc_id,
        "limit": 5
    }
    
    log_res = requests.get(log_url, headers=headers, params=params)
    
    if log_res.status_code == 200:
        logs_json = log_res.json()
        log_entries = logs_json.get("logs", [])
        
        if not log_entries:
            return "📭 No logs found for this service."

        formatted_logs = ""
        for log in log_entries:
            msg = log.get("message", "").strip()
            formatted_logs += f"• <code>{msg}</code>\n\n"
        return f"📋 <b>Recent Logs:</b>\n\n{formatted_logs}📌 If want to see new logs, tap again your service's button above again.⬆️"
    else:
        return f"❌ Failed to fetch logs: {log_res.text}"
        
async def fetch_env_vars(svc_id, context):
    headers = get_headers(context)
    r = requests.get(f"{RENDER_URL}/services/{svc_id}/env-vars", headers=headers)
    if r.status_code == 200:
        vars_list = "\n".join([f"<b>{v['envVar']['key']}:</b> <code>{v['envVar']['value']}</code>\n" for v in r.json()])
        return f"<b>🔑 Env Vars:</b>\n" + "—" * 7 + "\n" f"{vars_list}" if vars_list else "No variables found."
    return f"❌ Error fetching env: {r.status_code}"

async def update_env_variable(svc_id, context, user_input):
    if "=" not in user_input:
        return "❌ Invalid format. Please use: <code>KEY = VALUE</code>"
    
    key, value = [x.strip() for x in user_input.split("=", 1)]
    url = f"{RENDER_URL}/services/{svc_id}/env-vars/{key}"
    payload = {"value": value}
    headers = get_headers(context)
    r = requests.put(url, json=payload, headers=headers)
    
    if r.status_code == 200:
        return f"✅ Successfully set <code>{key}</code> to <code>{value}</code>"
    else:
        return f"❌ Failed to update: {r.text}"

async def update_full_env(svc_id, context, user_input):
    headers = get_headers(context)
    lines = user_input.split('\n')
    payload = []
    
    for line in lines:
        if "=" in line:
            k, v = [x.strip() for x in line.split("=", 1)]
            payload.append({"key": k, "value": v})
    
    if not payload:
        return "❌ No valid <code>KEY = VALUE</code> pairs found."

    url = f"{RENDER_URL}/services/{svc_id}/env-vars"
    headers = headers
    r = requests.put(url, json=payload, headers=headers)
    
    if r.status_code == 200:
        return f"✅ Successfully replaced all variables for your service ({len(payload)} vars)."
    else:
        return f"❌ Bulk update failed: {r.text}"
        
async def delete_env_variable(svc_id, context, user_input):
    headers = get_headers(context)
    key = user_input
    url = f"{RENDER_URL}/services/{svc_id}/env-vars/{key}"
    r = requests.delete(url, headers=headers)
    
    if r.status_code == 204:
        return f"🗑 <b>Deleted:</b> <code>{key}</code> from web service."
    elif r.status_code == 404:
        return f"❌ Variable <code>{key}</code> not found on this service."
    else:
        return f"❌ Failed to delete: {r.text}"
                  
async def toggle_suspension(svc_id, context, action):
    headers = get_headers(context)
    r = requests.post(f"{RENDER_URL}/services/{svc_id}/{action}", headers=headers)
    status_text = "Suspended ⏸" if action == "suspend" else "Resumed ▶️"
    return f"✅ Service {status_text}" if r.status_code == 202 else f"❌ {action} failed: {r.text}"

async def change_service_name(svc_id, context, user_input):
    headers = get_headers(context)
    payload = {"name": user_input}
    url = f"{RENDER_URL}/services/{svc_id}"
    r = requests.patch(url, json=payload, headers=headers)
    
    if r.status_code == 200:
        return f"✨ <b>Name Updated!</b>\nNew Name: <code>{user_input}</code>"
    else:
        return f"❌ Failed to change name: {r.text}"
        
async def update_start_command(svc_id, context, user_input):
    headers = get_headers(context)
    payload = { "serviceDetails": {
            "envSpecificDetails": { "startCommand": user_input.strip() }
        } }
    url = f"{RENDER_URL}/services/{svc_id}"
    r = requests.patch(url, json=payload, headers=headers)
    
    if r.status_code == 200:
        return f"🚀 <b>Start Command Updated!</b>\nNew Command: <code>{user_input}</code>"
    else:
        return f"❌ Failed to update start command: {r.text}"
        
async def update_build_command(svc_id, context, user_input):
    headers = get_headers(context)
    payload = { "serviceDetails": {
            "envSpecificDetails": { "buildCommand": user_input.strip() }
        } }
    url = f"{RENDER_URL}/services/{svc_id}"
    r = requests.patch(url, json=payload, headers=headers)
    
    if r.status_code == 200:
        return f"🛠 <b>Build Command Updated!</b>\nNew Command: <code>{user_input}</code>"
    else:
        return f"❌ Failed to update build command: {r.text}"
        
async def update_build_filter(svc_id, user_input, context):
    headers = get_headers(context)
    paths = [p.strip() for p in re.split(r'[,\n]', user_input) if p.strip()]
    
    if not paths:
        return "❌ No valid paths provided."

    payload = { "buildFilter": { "ignoredPaths": paths } }
    
    url = f"{RENDER_URL}/services/{svc_id}"
    r = requests.patch(url, json=payload, headers=headers)
    
    if r.status_code == 200:
        path_list = ", ".join([f"<code>{p}</code>" for p in paths])
        return f"🔍 <b>Build Filter Updated!</b>\nIgnored Paths: {path_list}"
    else:
        return f"❌ Failed to update filter: {r.text}"
        
async def delete_render_service(svc_id, context):
    headers = get_headers(context)
    url = f"{RENDER_URL}/services/{svc_id}"
    r = requests.delete(url, headers=headers)
    
    if r.status_code == 204:
        return f"🗑 <b>Service Deleted.</b>"
    elif r.status_code == 404:
        return "❌ Service not found. It may have already been deleted."
    else:
        return f"❌ Failed to delete service: {r.text}"
   
async def handle_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return
        
    prompt_text = update.message.reply_to_message.text
    user_input = update.message.text.strip()    
    
    if "API" in prompt_text:
        test_res = requests.get(
            "https://api.render.com/v1/owners", 
            headers={"Authorization": f"Bearer {user_input}"}
        )
        if test_res.status_code == 200:
            context.user_data["api_key"] = user_input
            await update.message.reply_text(
                "✅ <b>Login successful!</b> You can now use management commands.\n\n"
                "If you want to logout, send /logout and your API key will be cleared and unpinned.",
                parse_mode="HTML"
            )
            try:
                await context.bot.pin_chat_message(
                    chat_id=update.effective_chat.id,
                    message_id=update.message.message_id,
                    disable_notification=True
                )
            except Exception as e:
                print(f"Pin failed: {e}")
        else:
            await update.message.reply_text("❌ <b>Invalid Key.</b> Please try /login again.")
            
    match = re.search(r"srv-[a-z0-9]+", prompt_text)
    if not match:
        return
    
    svc_id = match.group(0)
    
    if "add or update" in prompt_text:
        result_msg = await update_env_variable(svc_id, context, user_input)
        await update.message.reply_text(result_msg, parse_mode="HTML")
        
    elif "to DELETE" in prompt_text:
        result_msg = await delete_env_variable(svc_id, context, user_input)
        await update.message.reply_text(result_msg, parse_mode="HTML")
    
    elif "list" in prompt_text:
        result_msg = await update_full_env(svc_id, context, user_input)
        await update.message.reply_text(result_msg, parse_mode="HTML")

    elif "name" in prompt_text:
        result_msg = await change_service_name(svc_id, context, user_input)
        await update.message.reply_text(result_msg, parse_mode="HTML")

    if "Start" in prompt_text:
        result_msg = await update_start_command(svc_id, context, user_input)
        await update.message.reply_text(result_msg, parse_mode="HTML")
        
    elif "Build" in prompt_text:
        result_msg = await update_build_command(svc_id, context, user_input)
        await update.message.reply_text(result_msg, parse_mode="HTML")
        
    elif "IGNORE" in prompt_text:
        result_msg = await update_build_filter(svc_id, user_input, context)
        await update.message.reply_text(result_msg, parse_mode="HTML")
        
    elif "PERMANENTLY DELETE" in prompt_text:
        if update.message.text.strip().upper() == "CONFIRM":
            result_msg = await delete_render_service(svc_id, context)
            await update.message.reply_text(result_msg, parse_mode="HTML")
        else:
            await update.message.reply_text("❌ Deletion cancelled. Confirmation word did not match.")

async def action_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    headers = get_headers(context)
    if not headers:
        await update.message.reply_text("❌ You are not logged in.\nSend /login")
        
    command = update.message.text.replace("/", "").lower()
    res = requests.get(f"{RENDER_URL}/services", headers=headers)
    if res.status_code == 200:
        keyboard = [[InlineKeyboardButton(item['service']['name'], callback_data=f"{command}_{item['service']['id']}")] for item in res.json()]
        await update.message.reply_text("<b>Select service:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# --- MAIN INTERACTION ROUTER ---
async def handle_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, svc_id = query.data.split("_", 1)    

    if action == "serviceinfo":
        msg = await get_service_info(svc_id, context)
    elif action == "deploy":
        msg = await trigger_deploy(svc_id, context)
    elif action == "canceldeploy":
        msg = await cancel_last_deploy(svc_id, context)
    elif action == "deployinfo":
        msg = await get_last_deploy(svc_id, context)
    elif action == "toggleautodeploy":
        keyboard = [
            [
                InlineKeyboardButton("✅ Turn ON", callback_data=f"adset_on_{svc_id}"),
                InlineKeyboardButton("🛑 Turn OFF", callback_data=f"adset_off_{svc_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"⚙️ <b>Auto-Deploy Settings</b>\nChoose an action:",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        return
    elif action.startswith("adset"):
        _, status, svc_id = query.data.split("_", 2)
        msg = await toggle_auto_deploy(svc_id, status, context)
    elif action == "logs":
        msg = await get_service_logs(svc_id, context)
    elif action in ["suspend", "resume"]:
        msg = await toggle_suspension(svc_id, context, action)
    elif action == "listenv":
        msg = await fetch_env_vars(svc_id, context)
    elif action == "updatenv":
        msg = ("📌 If you want to add or update more variables, tap on the service's button above again. ⬆️\n"
        "Or send /updatefullenv to replace all environment variables with a new list.\n\n"
        "<b>N.B. </b>After updating the environment variables via API, your web service won't be deployed automatically even if auto deploy is turned on. So, you have to do it manually.")
        await query.message.reply_text(
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n"
            "✍️ Please reply to this message with the <b>environment variable</b> you want to add or update.\n<b>Format: </b>KEY = VALUE",
            reply_markup=ForceReply(selective=True),
            parse_mode="HTML"
        )
    elif action == "updatefullenv":
        msg = ("⚠️ <b>Warning:</b> This replaces EVERYTHING.\n\n"
        "<b>N.B. </b>After updating the environment variables via API, your web service won't be deployed automatically even if auto deploy is turned on. So, you have to do it manually.")
        await query.message.reply_text(
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n"
            "✍️ Please reply to this message with your new <b>environment variables</b> list.\n<b>Format</b> (one per line):\n<code>KEY1 = VALUE1\nKEY2 = VALUE2</code>\n\n",
            reply_markup=ForceReply(selective=True),
            parse_mode="HTML"
        )
    elif action == "deletenv":
        msg = "<b>N.B. </b>After deleting a environment variable via API, your web service won't be deployed automatically even if auto deploy is turned on. So, you have to do it manually."
        await query.message.reply_text(
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n"
            "✍️ Please reply to this message with the <b>KEY</b> of environment variable you want to <b>DELETE.</b>",
            reply_markup=ForceReply(selective=True),
            parse_mode="HTML"
        )
    elif action == "rename":
        msg = ""
        await query.message.reply_text(
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n"
            "✍️ Please reply to this message with the <b>NEW name</b> you want to set.\n\n"
            "<i>Use lowercase, numbers, and hyphens only.</i>",
            reply_markup=ForceReply(selective=True),
            parse_mode="HTML"
        )
    elif action == "changestartcmd":
        msg = ""
        await query.message.reply_text(
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n"
            f"✍️ Please reply to this message with the <b>NEW Start Command</b> you want to set.\n\n"
            "Example: <code>python main.py</code> or <code>npm start</code>",
            reply_markup=ForceReply(selective=True),
            parse_mode="HTML"
        )
    elif action == "changebuildcmd":
        msg = ""
        await query.message.reply_text(
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n"
            f"✍️ Please reply to this message with the <b>NEW Build Command</b> you want to set.\n\n"
            "Example: <code>npm install && npm run build</code>",
            reply_markup=ForceReply(selective=True),
            parse_mode="HTML"
        )
    elif action == "buildfilter":
        msg = ""
        await query.message.reply_text(
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n"
            "✍️ Please reply to this message with the <b>paths</b> to IGNORE for your service.\n"
            "Separate them with commas or new lines.\n\n"
            "Example:\n<code>README.md, docs/*, .gitignore</code>",
            reply_markup=ForceReply(selective=True),
            parse_mode="HTML"
        )
    elif action == "deleteservice":
        msg = "⚠️ <b>Warning:</b> This action is permanent."
        await query.message.reply_text(
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n"
            "⚠️ Are you sure you want to <b>PERMANENTLY DELETE</b> this service?\nTo confirm, reply to this message with the word: <b>CONFIRM</b>",
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
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("logout", logout))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("services", list_services))
    app.add_handler(CommandHandler("accountinfo", get_account_info))
    for cmd in ["serviceinfo", "deploy", "deployinfo", "canceldeploy", "toggleautodeploy", "logs", "suspend", "resume", "listenv", "updatenv", "deletenv", "updatefullenv", "rename", "changestartcmd", "changebuildcmd", "buildfilter", "deleteservice"]:
        app.add_handler(CommandHandler(cmd, action_picker))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply_text))
    app.add_handler(CallbackQueryHandler(handle_interaction))
    app.run_polling()

if __name__ == "__main__":
    main()