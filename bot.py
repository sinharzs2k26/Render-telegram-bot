import re
import os
import logging
import requests
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
# --- CONFIGURATION ---
TOKEN = os.environ.get("TOKEN")
RENDER_URL = "https://api.render.com/v1"
ADMIN_ID = [7728700576, 7753358925]

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
# --- DUMMY SERVER FOR RENDER HEALTH CHECK ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active.")

def run_health_server():
    httpd = HTTPServer(('0.0.0.0', 10000), HealthCheckHandler)
    httpd.serve_forever()
# --- RENDER API HELPERS ---
def get_headers(context: ContextTypes.DEFAULT_TYPE):
    api_key = context.user_data.get("api_key")
    if not api_key:
        return None
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
# --- COMMAND HANDLERS ---
def save_user(user_id):
    with open("users.txt", "a+") as f:
        f.seek(0)
        lines = f.readlines()
        if f"{user_id}\n" not in lines:
            f.write(f"{user_id}\n")

def count_users():
    with open("users.txt", "r") as f:
        return len(f.readlines())

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_ID:
        return
    try:
        bot_status_txt = (f"Total users: {count_users()}")
    except:
        bot_status_txt = "No User ID saved in the server. Users have not sent /start yet after updating the bot."
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast a message", callback_data="broadcast")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh")],
        [InlineKeyboardButton("🆔 Get all IDs", callback_data="get_ids")],
        [InlineKeyboardButton("📝 Update users.txt", callback_data="update_users")]
    ]
    if update.message:
        await update.message.reply_text(bot_status_txt, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        try:
            await update.callback_query.edit_message_text(bot_status_txt, reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            pass

async def broadcast(user_input, update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_to_send = user_input
    with open("users.txt", "r") as f:
        user_ids = f.readlines()
    success = 0
    failed = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid.strip(), text=f"{message_to_send}", parse_mode="HTML")
            success += 1
        except Exception:
            failed += 1
    user_s = "users" if success > 1 else "user"
    fail_msg = f"\n❌ Failed {failed}" if failed > 1 else ""
    return f"✅ Broadcast message sent to {success} {user_s}.\n{fail_msg}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id)
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
    help_text = (
        "📌 This bot is made to control Render's <b>web services</b> only.\n\n"
        "<b>🛠 Available Commands & Usage</b>\n\n"
        "• /accountinfo - See your Render account information.\n\n"
        "<b>📋 Services</b>\n"
        "• /services - List all services with details.\n"
        "• /rename - Change name of a service.\n"
        "• /changestartcmd - Change start command of a service.\n"
        "• /changebuildcmd - Change build command of a service.\n"
        "• /updatebuildfilter - Add ignored paths whose changes will not trigger a new build.\n"
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
    if "api_key" in context.user_data:
        await update.message.reply_text("You were logged in already!")
    else:
        await update.message.reply_html(
            "<b>🔑 Login to Render</b>\n"
            "Please provide your API key to use the bot: <code>rnd_xxxxxxxxxxxx</code>",
            reply_markup=ForceReply(selective=True)
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
    if "api_key" in context.user_data:
        keyboard = [
            [InlineKeyboardButton("⚠️ Yes, I'm sure!", callback_data="logout_ok")],
            [InlineKeyboardButton("❌ Cancel", callback_data="logout_cancel")]
        ]
        await update.message.reply_html(
            "<b>Are you sure you really want to logout?</b>",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("You weren't logged in!")

async def services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    headers = get_headers(context)
    if not headers:
        await update.message.reply_text("❌ You are not logged in.\nSend /login")
    res = requests.get(f"{RENDER_URL}/services?limit=50", headers=headers)
    if res.status_code == 200:
        keyboard = []
        for item in res.json():
            svc = item['service']
            status_emoji = "🟢" if svc['suspended'] == "not_suspended" else "🔴"
            keyboard.append([InlineKeyboardButton(f"{status_emoji} {svc['name']}", callback_data=f"view_{svc['name']}_{svc['id']}")])
        text = "<b>📋 Render Services List</b>\n"
        if update.message:
            await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
# --- FUNCTIONS ---
async def get_service_info(context, svc_id, svc_name):
    r = requests.get(f"{RENDER_URL}/services/{svc_id}", headers=get_headers(context))
    text = f"<b>📄 Service Info: {svc_name}</b>\n" + "—" * 20 + "\n"
    if r.status_code == 200:
        svc = r.json()
        details = svc.get('serviceDetails', {})
        text += (
            f"<b>🔗 Service url: </b><code>{details.get('url')}</code>\n"
            f"<b>Service ID: </b><code>{svc['id']}</code>\n"
            f"<b>Status:</b> {'🟢 Active' if svc['suspended'] == 'not_suspended' else '🔴 Suspended'}\n"
            f"<b>Plan:</b> <code>{details.get('plan', 'N/A')}</code>\n"
            f"<b>Region:</b> <code>{details.get('region', 'N/A')}</code>\n"
            f"<b>Runtime:</b> <code>{details.get('runtime', 'N/A')}</code>\n"
            f"<b>Branch:</b> <code>{svc.get('branch', 'main')}</code>\n"
            f"<b>Auto-Deploy:</b> <code>{svc.get('autoDeploy', 'yes')}</code>\n\n"
            f"<b>🛠 Build Command:</b>\n<code>{details.get('envSpecificDetails', {}).get('buildCommand', 'N/A')}</code>\n\n"
            f"<b>🚀 Start Command:</b>\n<code>{details.get('envSpecificDetails', {}).get('startCommand', 'N/A')}</code>\n\n"
            f"<b>📅 Updated:</b> <code>{svc['updatedAt'][:10]}</code>\n\n"
            f"👉 <a href='https://dashboard.render.com/web/{svc['id']}'>Tap here to view on <b>Render Dashboard</b></a>"
        )
    else:
        text += "❌ Error fetching service info."
    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to services list", callback_data="back_services")]])
    return text, reply_markup

async def trigger_deploy(context, svc_id, svc_name):
    r = requests.post(f"{RENDER_URL}/services/{svc_id}/deploys", headers=get_headers(context))
    text = f"<b>Service name: {svc_name}</b>\n\n"
    if r.status_code == 201:
        text += "🚀 <b>Deploy triggered!</b>\nSend /logs to see runtime logs."
    else:
        text += f"❌ Error triggering a deploy: {r.status_code}"
    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to services list", callback_data="back_deploy")]])
    return text, reply_markup

async def cancel_last_deploy(context, svc_id, svc_name):
    list_url = f"{RENDER_URL}/services/{svc_id}/deploys?limit=1"
    res = requests.get(list_url, headers=get_headers(context))
    text = f"<b>Service name: {svc_name}</b>\n\n"
    if res.status_code == 200:
        deploys = res.json()
        if not deploys:
            text += "❌ No deployment found to cancel."
        deploy_id = deploys[0]['deploy']['id']
        current_status = deploys[0]['deploy']['status']
        if current_status in ["live", "build_failed", "canceled"]:
            text += f"⚠️ Cannot cancel. Last deploy is already <code>{current_status}</code>."
        cancel_url = f"{RENDER_URL}/services/{svc_id}/deploys/{deploy_id}/cancel"
        cancel_res = requests.post(cancel_url, headers=get_headers(context))
        if cancel_res.status_code == 200:
            text += f"🛑 <b>Deploy Cancelled!</b>"
        else:
            text += f"❌ Failed to cancel"
    else:
        text += f"❌ Error fetching deploy ID: {res.status_code}"
    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to services list", callback_data="back_canceldeploy")]])
    return text, reply_markup
    
async def get_last_deploy(context, svc_id, svc_name):
    r = requests.get(f"{RENDER_URL}/services/{svc_id}/deploys?limit=1", headers=get_headers(context))
    text = f"<b>Service name: {svc_name}</b>\n\n"
    if r.status_code == 200:
        deploy = r.json()
        if not deploy:
            text += "No deployment history found for this service."
        d = deploy[0]['deploy']
        commit = d.get('commit', {})
        status_emoji = "✅" if d['status'] == "live" else "❌" if d['status'] in ["update_failed", "build_failed", "canceled"] else "⏳"
        text += (
            f"<b>🚀 Last Deploy Info</b>\n" + "—" * 12 + "\n"
            f"<b>Status:</b> {status_emoji} <code>{d['status']}</code>\n"
            f"<b>ID:</b> <code>{d['id']}</code>\n"
            f"<b>Trigger:</b> <code>{d['trigger']}</code>\n\n"
            f"<b>📝 Commit Message:</b>\n<i>{commit.get('message', 'N/A')}</i>\n\n"
            f"<b>🆔 Commit ID:</b>\n<code>{commit.get('id', 'N/A')[:7]}</code>\n\n"
            f"<b>⏱ Finished:</b> <code>{d.get('finishedAt', 'N/A')}</code>"
        )
    else:
        text += f"❌ Error fetching deploy info: {r.status_code}"
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh info", callback_data=f"refresh_deploy_{svc_name}_{svc_id}")],
        [InlineKeyboardButton("⬅️ Back to services list", callback_data="back_deployinfo")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return text, reply_markup

async def toggle_auto_deploy(context, svc_id, svc_name, status):
    payload = {"autoDeploy": "yes" if status == "on" else "no"}
    url = f"{RENDER_URL}/services/{svc_id}"
    r = requests.patch(url, json=payload, headers=get_headers(context))
    text = f"<b>Service name: {svc_name}</b>\n\n"
    if r.status_code == 200:
        icon = "✅" if status == "on" else "🛑"
        text += f"{icon} <b>Auto-Deploy</b> is now <b>{status.upper()}</b> for your service."
    else:
        text += f"❌ Failed to update: {r.text}"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"toggleautodeploy_{svc_name}_{svc_id}")]])
    return text, reply_markup

async def get_service_logs(context, svc_id, svc_name):
    text = f"**Service name:** {svc_name}\n"
    owner_res = requests.get(f"{RENDER_URL}/owners", headers=get_headers(context))
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
        "limit": 10
    }
    log_res = requests.get(log_url, headers=get_headers(context), params=params)
    if log_res.status_code == 200:
        logs_json = log_res.json()
        log_entries = logs_json.get("logs", [])
        if not log_entries:
            return "📭 No logs found for this service."
        formatted_logs = ""
        for log in log_entries:
            msg = log.get("message", "").strip()
            formatted_logs += f"• `{msg}`\n\n"
        text += f"📋 **Recent Logs:**\n\n{formatted_logs}"
    else:
        text += f"❌ Failed to fetch logs: {log_res.text}"
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Logs", callback_data=f"refresh_logs_{svc_name}_{svc_id}")],
        [InlineKeyboardButton("⬅️ Back to services list", callback_data="back_logs")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return text, reply_markup
        
async def fetch_env_vars(context, svc_id, svc_name):
    text = f"<b>Service name: {svc_name}</b>\n\n"
    r = requests.get(f"{RENDER_URL}/services/{svc_id}/env-vars", headers=get_headers(context))
    if r.status_code == 200:
        vars_list = "\n".join([f"<b>{v['envVar']['key']}</b> = <code>{v['envVar']['value']}</code>\n" for v in r.json()])
        text += f"<b>🔑 Env Vars:</b>\n" + "—" * 7 + "\n" f"{vars_list}" if vars_list else "No variables found."
    else:
        text += f"❌ Error fetching env: {r.status_code}"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to services list", callback_data="back_listenv")]])
    return text, reply_markup

async def update_env_variable(context, svc_id, user_input):
    if "=" not in user_input:
        return "❌ Invalid format. Please use: <code>KEY = VALUE</code>"
    key, value = [x.strip() for x in user_input.split("=", 1)]
    url = f"{RENDER_URL}/services/{svc_id}/env-vars/{key}"
    payload = {"value": value}
    r = requests.put(url, json=payload, headers=get_headers(context))
    if r.status_code == 200:
        return f"✅ Successfully set <code>{value}</code> to <code>{key}</code>"
    else:
        return f"❌ Failed to update: {r.text}"

async def update_full_env(context, svc_id, user_input):
    lines = user_input.split('\n')
    payload = []
    for line in lines:
        if "=" in line:
            k, v = [x.strip() for x in line.split("=", 1)]
            payload.append({"key": k, "value": v})
    if not payload:
        return "❌ No valid <code>KEY = VALUE</code> pairs found."
    url = f"{RENDER_URL}/services/{svc_id}/env-vars"
    r = requests.put(url, json=payload, headers=get_headers(context))
    if r.status_code == 200:
        var_nmbr = int(len(payload))
        if var_nmbr > 1: var_s = "variables"
        else: var_s = "variable"
        return f"✅ Successfully replaced all variables for your service ({var_nmbr} {var_s})."
    else:
        return f"❌ Bulk update failed: {r.text}"
        
async def delete_env_variable(context, svc_id, key):
    url = f"{RENDER_URL}/services/{svc_id}/env-vars/{key}"
    r = requests.delete(url, headers=get_headers(context))
    if r.status_code == 204:
        text = f"🗑 <b>Deleted:</b> variable <code>{key}</code> from web service."
    elif r.status_code == 404:
        text = f"❌ Variable <code>{key}</code> not found on this service."
    else:
        text = f"❌ Failed to delete: {r.text}"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"deletenv_‌_{svc_id}")]])
    return text, reply_markup

async def toggle_suspension(context, svc_id, svc_name, action):
    text = f"<b>Service name: {svc_name}</b>\n\n"
    r = requests.post(f"{RENDER_URL}/services/{svc_id}/{action}", headers=get_headers(context))
    status_text = "Suspended ⏸" if action == "suspend" else "Resumed ▶️"
    text += f"Service {status_text}" if r.status_code == 202 else f"❌ {action} failed {r.text}"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to services list", callback_data=f"back_{action}")]])
    return text, reply_markup

async def change_service_name(context, svc_id, user_input):
    payload = {"name": user_input}
    url = f"{RENDER_URL}/services/{svc_id}"
    r = requests.patch(url, json=payload, headers=get_headers(context))
    if r.status_code == 200:
        return f"✨ <b>Name Updated!</b>\nNew Name: <code>{user_input}</code>"
    else:
        return f"❌ Failed to change name: {r.text}"
        
async def update_start_command(context, svc_id, user_input):
    payload = { "serviceDetails": {
            "envSpecificDetails": { "startCommand": user_input.strip() }
        } }
    url = f"{RENDER_URL}/services/{svc_id}"
    r = requests.patch(url, json=payload, headers=get_headers(context))
    if r.status_code == 200:
        return f"🚀 <b>Start Command Updated!</b>\nNew Command: <code>{user_input}</code>"
    else:
        return f"❌ Failed to update start command: {r.text}"

async def update_build_command(context, svc_id, user_input):
    payload = { "serviceDetails": {
            "envSpecificDetails": { "buildCommand": user_input.strip() }
        } }
    url = f"{RENDER_URL}/services/{svc_id}"
    r = requests.patch(url, json=payload, headers=get_headers(context))
    if r.status_code == 200:
        return f"🛠 <b>Build Command Updated!</b>\nNew Command: <code>{user_input}</code>"
    else:
        return f"❌ Failed to update build command: {r.text}"

async def update_build_filter(context, svc_id, user_input):
    paths = [p.strip() for p in re.split(r'[,\n]', user_input) if p.strip()]    
    if not paths:
        return "❌ No valid paths provided."
    payload = { "buildFilter": { "ignoredPaths": paths } }
    url = f"{RENDER_URL}/services/{svc_id}"
    r = requests.patch(url, json=payload, headers=get_headers(context))    
    if r.status_code == 200:
        path_list = ", ".join([f"<code>{p}</code>" for p in paths])
        return f"🔍 <b>Build Filter Updated!</b>\nIgnored Paths: {path_list}"
    else:
        return f"❌ Failed to update filter: {r.text}"

async def delete_render_service(context, svc_id, svc_name, status):
    text = f"<b>Service name: {svc_name}</b>\n\n"
    if status == "ok":
        url = f"{RENDER_URL}/services/{svc_id}"
        r = requests.delete(url, headers=get_headers(context))
        if r.status_code == 204:
            text += f"🗑 <b>Service Deleted.</b>"
        elif r.status_code == 404:
            text += "❌ Service not found. It may have already been deleted."
        else:
            text += f"❌ Failed to delete service: {r.text}"
    else:
        text += "🚫 Deletion cancelled by you!"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"deleteservice_{svc_name}_{svc_id}")]])
    return text, reply_markup

async def handle_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt_msg = update.message.reply_to_message
    if not prompt_msg:
        return
    prompt_text = prompt_msg.text
    user_input = update.message.text.strip()
    if "broadcast" in prompt_text:
        result_msg = await broadcast(user_input, update, context)
        await update.message.reply_text(result_msg)
        return
    elif "API" in prompt_text:
        test_res = requests.get(
            "https://api.render.com/v1/owners", 
            headers={"Authorization": f"Bearer {user_input}"}
        )
        if test_res.status_code == 200:
            context.user_data["api_key"] = user_input
            await update.message.reply_html(
                "✅ <b>Login successful!</b> You can now use management commands.\n\n"
                "<i>📌 You have to re-login if the bot gets updates and so your API key gets cleared.</i>\n\n"
                "If you want to logout, send /logout and your API key will be cleared.",
            )
        else:
            await update.message.reply_html("❌ <b>Invalid Key.</b> Please try /login again.")
        return
    match = re.search(r"srv-[a-z0-9]+", prompt_text)
    if not match:
        return
    svc_id = match.group(0)
    if "add or update" in prompt_text:
        result_msg = await update_env_variable(context, svc_id, user_input)
    elif "list" in prompt_text:
        result_msg = await update_full_env(context, svc_id, user_input)
    elif "NEW name" in prompt_text:
        result_msg = await change_service_name(context, svc_id, user_input)
    elif "Start" in prompt_text:
        result_msg = await update_start_command(context, svc_id, user_input)
    elif "Build" in prompt_text:
        result_msg = await update_build_command(context, svc_id, user_input)
    elif "IGNORE" in prompt_text:
        result_msg = await update_build_filter(context, svc_id, user_input)
    await update.message.reply_html(result_msg)

async def action_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    headers = get_headers(context)
    if not headers:
        await update.message.reply_text("❌ You are not logged in.\nSend /login")
    if update.message:
        command = update.message.text.replace("/", "").lower()
    else:
        command = update.callback_query.data.split("_")[1]
    res = requests.get(f"{RENDER_URL}/services", headers=headers)
    if res.status_code == 200:
        text = "<b>Select a service:</b>"
        keyboard = [[InlineKeyboardButton(item['service']['name'], callback_data=f"{command}_{item['service']['name']}_{item['service']['id']}")] for item in res.json()]
        if update.message:
            await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
# --- MAIN INTERACTION ROUTER ---
async def handle_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "broadcast":
        await query.answer()
        await query.message.reply_text(
            "Enter a message to broadcast 📢:",
            reply_markup=ForceReply(selective=True)
        )
        return
    elif data == "refresh":
        await query.answer()
        await admin(update, context)
        return
    elif data == "get_ids":
        await query.answer()
        if os.path.exists("users.txt"):
            await query.message.reply_document("users.txt", caption="Here is the current user list.")
        else:
            await query.answer("File not found!", show_alert=True)
        return
    elif data.startswith("refresh"):
        _, type, svc_name, svc_id = data.split("_")
        if type == "logs":
            text, markup = await get_service_logs(context, svc_id, svc_name)
        else:
            text, markup = await get_last_deploy(context, svc_id, svc_name)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="MARKDOWN" if type == "logs" else "HTML")
            await query.answer("Refreshed! ✨", show_alert=True)
        except Exception as e:
            await query.answer("🔔 No new updates yet.", show_alert=True)
        return
    elif data.startswith("back"):
        await query.answer()
        action = data.split("_")[1]
        if action == "services":
            await services(update, context)
        else:
            await action_picker(update, context)
        return
    elif data.startswith("logout"):
        await query.answer()
        status = data.split("_")[1]
        if status == "ok":
            del context.user_data["api_key"]
            await query.message.delete()
            await query.message.reply_html("🔒 <b>Logged out.</b> Your API key has been cleared.")
        else:
            await query.message.delete()
            await query.message.reply_text("🚫 Logout cancelled by you!")
        return
    elif data.startswith("adset"):
        await query.answer()
        _, status, svc_id, svc_name = data.split("_")
        msg, markup= await toggle_auto_deploy(context, svc_id, svc_name, status)
        await query.edit_message_text(msg, reply_markup=markup, parse_mode="HTML")
        return
    elif data.startswith("delenv"):
        await query.answer()
        delwht, key, svc_id = data.split("__")
        msg, markup = await delete_env_variable(context, svc_id, key)
        await query.edit_message_text(msg, reply_markup=markup, parse_mode="HTML")
        return
    elif data.startswith("delsvc"):
        await query.answer()
        _, status, svc_id, svc_name = data.split("_")
        msg, markup = await delete_render_service(context, svc_id, svc_name, status)
        await query.edit_message_text(msg, reply_markup=markup, parse_mode="HTML")
        return
    action, svc_name, svc_id = data.split("_")
    if action == "deploy":
        await query.answer()
        msg, markup = await trigger_deploy(context, svc_id, svc_name)
    elif action == "canceldeploy":
        await query.answer()
        msg, markup = await cancel_last_deploy(context, svc_id, svc_name)
    elif action == "deployinfo":
        await query.answer()
        msg, markup = await get_last_deploy(context, svc_id, svc_name)
    elif action == "toggleautodeploy":
        await query.answer()
        keyboard = [
            [
                InlineKeyboardButton("✅ Turn ON", callback_data=f"adset_on_{svc_id}_{svc_name}"),
                InlineKeyboardButton("🛑 Turn OFF", callback_data=f"adset_off_{svc_id}_{svc_name}")
            ],
            [InlineKeyboardButton("⬅️ Back to services list", callback_data="back_toggleautodeploy")]
        ]
        await query.edit_message_text(
            f"⚙️ <b>Auto-Deploy Settings</b>\nChoose an action:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return
    elif action == "logs":
        await query.answer()
        msg, markup = await get_service_logs(context, svc_id, svc_name)
    elif action in ["suspend", "resume"]:
        await query.answer()
        msg, markup = await toggle_suspension(context, svc_id, svc_name, action)
    elif action == "listenv":
        await query.answer()
        msg, markup = await fetch_env_vars(context, svc_id, svc_name)
    elif action == "updatenv":
        await query.answer()
        msg = (
            "📌 If you want to add or update more variables, tap on the service's button above again. ⬆️\n"
            "Or send /updatefullenv to replace all environment variables with a new list.\n\n"
            "<b>N.B. </b>After updating the environment variables via API, your web service won't be deployed automatically even if auto deploy is turned on. So, you have to do it manually."
        )
        await query.message.reply_html(
            f"<b>Service name:</b> {svc_name}\n"
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n"
            "✍️ Please reply to this message with the <b>environment variable</b> you want to add or update.\n\n<b>Format: </b>KEY = VALUE",
            reply_markup=ForceReply(selective=True)
        )
        return
    elif action == "updatefullenv":
        await query.answer()
        msg = (
            "⚠️ <b>Warning:</b> This replaces EVERYTHING.\n\n"
            "<b>N.B. </b>After updating the environment variables via API, your web service won't be deployed automatically even if auto deploy is turned on. So, you have to do it manually."
        )
        await query.message.reply_html(
            f"<b>Service name:</b> {svc_name}\n"
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n"
            "✍️ Please reply to this message with your new <b>environment variables</b> list.\n<b>Format</b> (one per line):\n<code>KEY1 = VALUE1\nKEY2 = VALUE2</code>\n\n",
            reply_markup=ForceReply(selective=True)
        )
        return
    elif action == "deletenv":
        await query.answer()
        r = requests.get(f"{RENDER_URL}/services/{svc_id}/env-vars", headers=get_headers(context))
        if r.status_code == 200:
            keyboard = [
                [InlineKeyboardButton(v['envVar']['key'], callback_data=f"delenv__{v['envVar']['key']}__{svc_id}") for v in r.json()],
                [InlineKeyboardButton("⬅️ Back to services list", callback_data="back_deletenv")]
            ]
            await query.edit_message_text(
                "<b>📌 N.B. </b>After deleting a environment variable via API, your web service won't be deployed automatically even if auto deploy is turned on. So, you have to do it manually.\n\n"
                "Select a <b>environment variable</b> to delete:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        else:
            query.message.reply_text("❌ Error loading env vars")
        return
    elif action == "rename":
        await query.answer()
        await query.message.reply_html(
            f"<b>Service name:</b> {svc_name}\n"
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n"
            "✍️ Please reply to this message with the <b>NEW name</b> you want to set.\n\n"
            "<i>Use lowercase, numbers, and hyphens only.</i>",
            reply_markup=ForceReply(selective=True)
        )
        return
    elif action == "changestartcmd":
        await query.answer()
        await query.message.reply_html(
            f"<b>Service name:</b> {svc_name}\n"
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n"
            f"✍️ Please reply to this message with the <b>NEW Start Command</b> you want to set.\n\n"
            "Example: <code>python main.py</code> or <code>npm start</code>",
            reply_markup=ForceReply(selective=True)
        )
        return
    elif action == "changebuildcmd":
        await query.answer()
        await query.message.reply_html(
            f"<b>Service name:</b> {svc_name}\n"
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n"
            f"✍️ Please reply to this message with the <b>NEW Build Command</b> you want to set.\n\n"
            "Example: <code>npm install && npm run build</code>",
            reply_markup=ForceReply(selective=True)
        )
        return
    elif action == "updatebuildfilter":
        await query.answer()
        await query.message.reply_html(
            f"<b>Service name:</b> {svc_name}\n"
            f"<b>Service ID: </b><code>{svc_id}</code>\n\n"
            "✍️ Please reply to this message with the <b>paths</b> to IGNORE for your service.\n"
            "Separate them with commas or new lines.\n\n"
            "Example:\n<code>README.md, docs/*, .gitignore</code>",
            reply_markup=ForceReply(selective=True)
        )
        return
    elif action == "deleteservice":
        await query.answer()
        keyboard = [
            [
                InlineKeyboardButton("⚠️ Yes, I'm sure!", callback_data=f"delsvc_ok_{svc_id}_{svc_name}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"delsvc_cancel_{svc_id}_{svc_name}")
            ],
            [InlineKeyboardButton("⬅️ Back to services list", callback_data="back_deleteservice")]
        ]
        await query.edit_message_text(
            "<b>Are you sure you really want to delete this web service?</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return
    elif action.startswith("view"):
        await query.answer()
        msg, markup = await get_service_info(context, svc_id, svc_name)
    else:
        msg = "Unknown action."
    await query.edit_message_text(msg, reply_markup=markup, parse_mode="MARKDOWN" if action == "logs" else "HTML")
# --- MAIN RUNNER ---
def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("logout", logout))
    app.add_handler(CommandHandler("services", services))
    app.add_handler(CommandHandler("accountinfo", get_account_info))
    for cmd in ["deploy", "deployinfo", "canceldeploy", "toggleautodeploy", "logs", "suspend", "resume", "listenv", "updatenv", "deletenv", "updatefullenv", "rename", "changestartcmd", "changebuildcmd", "updatebuildfilter", "deleteservice"]:
        app.add_handler(CommandHandler(cmd, action_picker))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply_text))
    app.add_handler(CallbackQueryHandler(handle_interaction))
    app.run_polling()
if __name__ == "__main__":
    main()