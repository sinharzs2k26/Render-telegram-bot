#!/usr/bin/env python3
"""
Render.com Management Telegram Bot
Updated with correct API endpoints from Render documentation
"""

import os
import logging
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ===================== CONFIGURATION =====================
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
RENDER_API_KEY = os.environ.get('RENDER_API_KEY')
ADMIN_USER_ID = os.environ.get('ADMIN_USER_ID', '')

# Render API configuration
RENDER_API_BASE = "https://api.render.com/v1"
HEADERS = {
    "Authorization": f"Bearer {RENDER_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

# ===================== LOGGING =====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== HELPER FUNCTIONS =====================
async def check_admin(update: Update) -> bool:
    """Check if user is authorized (admin)."""
    if not ADMIN_USER_ID:
        return True
    
    user_id = str(update.effective_user.id)
    if user_id == ADMIN_USER_ID:
        return True
    
    await update.message.reply_text("❌ You are not authorized to use this bot.")
    return False

async def make_render_request(method: str, endpoint: str, data: dict = None) -> Tuple[bool, dict]:
    """Make API request to Render."""
    url = f"{RENDER_API_BASE}/{endpoint}"
    
    try:
        if method.upper() == 'GET':
            response = requests.get(url, headers=HEADERS, params=data)
        elif method.upper() == 'POST':
            response = requests.post(url, headers=HEADERS, json=data)
        elif method.upper() == 'DELETE':
            response = requests.delete(url, headers=HEADERS)
        elif method.upper() == 'PATCH':
            response = requests.patch(url, headers=HEADERS, json=data)
        elif method.upper() == 'PUT':
            response = requests.put(url, headers=HEADERS, json=data)
        else:
            return False, {"error": f"Unsupported method: {method}"}
        
        response.raise_for_status()
        
        if response.status_code == 204:
            return True, {"message": "Operation successful"}
        
        return True, response.json()
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Render API error: {e}")
        try:
            error_msg = response.json().get('message', str(e))
        except:
            error_msg = str(e)
        return False, {"error": error_msg, "status_code": getattr(response, 'status_code', 0)}

def format_service_info(service: dict) -> str:
    """Format service information for display."""
    service_id = service.get('id', 'N/A')
    name = service.get('name', 'N/A')
    service_type = service.get('type', 'N/A')
    owner_id = service.get('ownerId', 'N/A')
    repo = service.get('repo', 'N/A')
    branch = service.get('branch', 'N/A')
    created_at = service.get('createdAt', 'N/A')
    updated_at = service.get('updatedAt', 'N/A')
    suspended = service.get('suspended', False)
    auto_deploy = service.get('autoDeploy', 'N/A')
    
    # Get service details
    env_vars = service.get('envVars', [])
    plan = service.get('plan', 'free')
    instance_type = service.get('instanceType', 'starter')
    
    # Get latest deployment
    deployments = service.get('deployments', [])
    latest_deploy = deployments[0] if deployments else {}
    deploy_status = latest_deploy.get('status', 'N/A')
    
    info = f"""
📦 <b>{name}</b>
━━━━━━━━━━━━━━━━━━━━━━━━
• ID: <code>{service_id}</code>
• Type: {service_type}
• Status: {deploy_status}
• Suspended: {'✅ Yes' if suspended else '❌ No'}
• Plan: {plan}
• Instance: {instance_type}
• Auto-deploy: {'✅ Enabled' if auto_deploy else '❌ Disabled'}
• Repository: {repo if repo else 'None'}
• Branch: {branch if branch else 'None'}
• Created: {created_at[:10] if created_at else 'N/A'}
• Env Variables: {len(env_vars)}
━━━━━━━━━━━━━━━━━━━━━━━━
"""
    return info

# ===================== BOT COMMAND HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message."""
    if not await check_admin(update):
        return
    
    welcome_text = """
🚀 <b>Render Management Bot</b>

Welcome! I can help you manage your Render.com services.

<b>Available Commands:</b>
• /services - List all services
• /service <code>id</code> - Get service details
• /deployments <code>service_id</code> - List deployments
• /env <code>service_id</code> - Show environment variables
• /domains <code>service_id</code> - List custom domains

<b>Service Actions:</b>
• /suspend <code>service_id</code> - Suspend a service
• /resume <code>service_id</code> - Resume a service
• /redeploy <code>service_id</code> - Redeploy a service
• /scale <code>service_id</code> <code>plan</code> - Change service plan

<b>Management:</b>
• /jobs - List background workers
• /databases - List managed databases
• /usage - Check usage statistics

Type /help for more information.
    """
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help message."""
    if not await check_admin(update):
        return
    
    help_text = """
🔍 <b>Detailed Help</b>

<b>Basic Commands:</b>
• /start - Welcome message
• /help - This help message
• /services - List all services

<b>Service Information:</b>
• /service <code>id</code> - Get detailed service info
• /deployments <code>service_id</code> - List service deployments
• /env <code>service_id</code> - Show environment variables
• /domains <code>service_id</code> - List custom domains

<b>Service Actions:</b>
• /suspend <code>service_id</code> - Suspend (pause) a service
• /resume <code>service_id</code> - Resume a suspended service
• /redeploy <code>service_id</code> - Trigger redeployment
• /scale <code>service_id</code> <code>plan</code> - Change service plan

<b>Management:</b>
• /jobs - List background workers
• /databases - List managed databases
• /usage - Get account usage statistics

<b>Examples:</b>
<code>/services</code>
<code>/service srv-abc123def456</code>
<code>/suspend srv-abc123def456</code>
<code>/redeploy srv-abc123def456</code>
    """
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def list_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all Render services."""
    if not await check_admin(update):
        return
    
    await update.message.reply_text("📡 Fetching your services...")
    
    success, response = await make_render_request('GET', 'services')
    
    if not success:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")
        return
    
    if not response:
        await update.message.reply_text("📭 No services found.")
        return
    
    services = response
    message = f"📋 <b>Your Services ({len(services)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    for i, service in enumerate(services, 1):
        service_id = service.get('id', 'N/A')
        name = service.get('name', 'N/A')
        service_type = service.get('type', 'N/A')
        suspended = service.get('suspended', False)
        plan = service.get('plan', 'starter')
        
        deployments = service.get('deployments', [])
        deploy_status = deployments[0].get('status', 'unknown') if deployments else 'unknown'
        
        status_emoji = "⏸️" if suspended else "▶️"
        
        message += f"{i}. {status_emoji} <b>{name}</b>\n"
        message += f"   ID: <code>{service_id}</code>\n"
        message += f"   Type: {service_type} | Plan: {plan} | Status: {deploy_status}\n"
        
        if i < len(services):
            message += "   ━\n"
    
    # Add quick action buttons
    keyboard = []
    for service in services[:5]:
        service_id = service.get('id')
        name = service.get('name')[:15]
        keyboard.append([
            InlineKeyboardButton(
                f"📊 {name}",
                callback_data=f"service_{service_id}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="refresh_services"),
        InlineKeyboardButton("📈 Usage", callback_data="show_usage")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if len(message) > 4000:
        message = message[:4000] + "\n... (truncated)"
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )

async def get_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get detailed information about a specific service."""
    if not await check_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Please provide a service ID.\nExample: /service srv-abc123def456")
        return
    
    service_id = context.args[0]
    await update.message.reply_text(f"🔍 Fetching service: {service_id}")
    
    success, response = await make_render_request('GET', f'services/{service_id}')
    
    if not success:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")
        return
    
    info_text = format_service_info(response)
    
    # Create action buttons
    is_suspended = response.get('suspended', False)
    keyboard = [
        [
            InlineKeyboardButton("🔄 Redeploy", callback_data=f"redeploy_{service_id}"),
            InlineKeyboardButton("⏸ Suspend" if not is_suspended else "▶️ Resume", 
                               callback_data=f"toggle_suspend_{service_id}")
        ],
        [
            InlineKeyboardButton("📜 Deployments", callback_data=f"deployments_{service_id}"),
            InlineKeyboardButton("⚙️ Env Vars", callback_data=f"env_{service_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back to Services", callback_data="refresh_services")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(info_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def service_deployments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List service deployments."""
    if not await check_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Please provide a service ID.\nExample: /deployments srv-abc123def456")
        return
    
    service_id = context.args[0]
    await update.message.reply_text(f"🚀 Fetching deployments for: {service_id}")
    
    success, response = await make_render_request('GET', f'services/{service_id}/deployments')
    
    if not success:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")
        return
    
    if not response:
        await update.message.reply_text("📭 No deployments found.")
        return
    
    deployments = response
    message = f"🚀 <b>Deployments ({len(deployments)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    for i, deploy in enumerate(deployments[:10], 1):
        deploy_id = deploy.get('id', 'N/A')
        status = deploy.get('status', 'N/A')
        commit_id = deploy.get('commit', {}).get('id', 'N/A')[:8] if deploy.get('commit') else 'N/A'
        commit_msg = deploy.get('commit', {}).get('message', 'N/A')[:50] if deploy.get('commit') else 'N/A'
        created_at = deploy.get('createdAt', 'N/A')
        
        status_emoji = {
            'live': '✅',
            'build_failed': '❌',
            'update_failed': '⚠️',
            'building': '🔨',
            'updating': '⚡',
            'pending': '⏳',
            'canceled': '🚫'
        }.get(status, '❓')
        
        message += f"{i}. {status_emoji} <b>{status.upper()}</b>\n"
        message += f"   ID: <code>{deploy_id}</code>\n"
        if commit_id != 'N/A':
            message += f"   Commit: {commit_id} - {commit_msg}\n"
        message += f"   Created: {created_at[:19] if created_at else 'N/A'}\n"
        
        if i < min(len(deployments), 10):
            message += "   ━\n"
    
    # Add action buttons
    keyboard = [
        [
            InlineKeyboardButton("🔄 Trigger Deploy", callback_data=f"trigger_deploy_{service_id}"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Service", callback_data=f"service_{service_id}")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if len(message) > 4000:
        message = message[:4000] + "\n... (truncated)"
    
    await update.message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def service_env_vars(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show service environment variables."""
    if not await check_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Please provide a service ID.\nExample: /env srv-abc123def456")
        return
    
    service_id = context.args[0]
    await update.message.reply_text(f"⚙️ Fetching env vars for: {service_id}")
    
    success, response = await make_render_request('GET', f'services/{service_id}')
    
    if not success:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")
        return
    
    env_vars = response.get('envVars', [])
    
    if not env_vars:
        await update.message.reply_text("📭 No environment variables found.")
        return
    
    message = f"⚙️ <b>Environment Variables ({len(env_vars)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    for i, env_var in enumerate(env_vars, 1):
        key = env_var.get('key', 'N/A')
        value = env_var.get('value', '')
        
        # Don't show actual values (security)
        if value:
            masked_value = "•" * 8 if len(value) > 3 else "•••"
        else:
            masked_value = "(empty)"
        
        message += f"{i}. <code>{key}</code> = {masked_value}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Service", callback_data=f"service_{service_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def suspend_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Suspend a service."""
    if not await check_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Please provide a service ID.\nExample: /suspend srv-abc123def456")
        return
    
    service_id = context.args[0]
    await update.message.reply_text(f"⏸ Suspending service: {service_id}")
    
    # According to Render API docs, we update the service with suspended: true
    data = {"suspended": True}
    success, response = await make_render_request('PATCH', f'services/{service_id}', data)
    
    if success:
        await update.message.reply_text(f"✅ Service {service_id} suspended successfully.")
    else:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")

async def resume_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resume a suspended service."""
    if not await check_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Please provide a service ID.\nExample: /resume srv-abc123def456")
        return
    
    service_id = context.args[0]
    await update.message.reply_text(f"▶️ Resuming service: {service_id}")
    
    # Update the service with suspended: false
    data = {"suspended": False}
    success, response = await make_render_request('PATCH', f'services/{service_id}', data)
    
    if success:
        await update.message.reply_text(f"✅ Service {service_id} resumed successfully.")
    else:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")

async def redeploy_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Redeploy a service."""
    if not await check_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Please provide a service ID.\nExample: /redeploy srv-abc123def456")
        return
    
    service_id = context.args[0]
    await update.message.reply_text(f"🔄 Triggering redeployment: {service_id}")
    
    # According to Render API, we create a new deployment
    success, response = await make_render_request('POST', f'services/{service_id}/deploys')
    
    if success:
        deploy_id = response.get('id', 'N/A')
        await update.message.reply_text(
            f"✅ Redeployment triggered!\nDeployment ID: <code>{deploy_id}</code>", 
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")

async def scale_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Change service plan."""
    if not await check_admin(update):
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Please provide service ID and plan.\nExample: /scale srv-abc123def456 starter\n\nAvailable plans: starter, standard, pro")
        return
    
    service_id = context.args[0]
    plan = context.args[1].lower()
    
    valid_plans = ['starter', 'standard', 'pro']
    if plan not in valid_plans:
        await update.message.reply_text(f"❌ Invalid plan. Choose from: {', '.join(valid_plans)}")
        return
    
    await update.message.reply_text(f"📊 Changing plan for {service_id} to {plan}")
    
    data = {"plan": plan}
    success, response = await make_render_request('PATCH', f'services/{service_id}', data)
    
    if success:
        await update.message.reply_text(f"✅ Service {service_id} plan changed to {plan}.")
    else:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")

async def show_usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show account usage statistics."""
    if not await check_admin(update):
        return
    
    await update.message.reply_text("📈 Fetching usage statistics...")
    
    # Note: Usage endpoint might be different or require organization context
    success, response = await make_render_request('GET', 'usage')
    
    if not success:
        # Try alternative endpoint
        success, response = await make_render_request('GET', 'organizations')
        if success and response:
            org_id = response[0].get('id') if isinstance(response, list) else response.get('id')
            if org_id:
                success, response = await make_render_request('GET', f'organizations/{org_id}/usage')
    
    if not success:
        await update.message.reply_text("⚠️ Usage statistics not available or API endpoint changed.")
        return
    
    if not response:
        await update.message.reply_text("📭 No usage data found.")
        return
    
    message = "📊 <b>Usage Statistics</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    if isinstance(response, list):
        for item in response[:10]:
            service_type = item.get('type', 'Unknown')
            usage_amount = item.get('usage', 0)
            limit = item.get('limit', 'Unlimited')
            unit = item.get('unit', 'units')
            
            message += f"• <b>{service_type}</b>: {usage_amount} {unit}"
            if limit != 'Unlimited':
                message += f" / {limit} {unit}"
            message += "\n"
    elif isinstance(response, dict):
        for key, value in response.items():
            if key not in ['id', 'createdAt', 'updatedAt']:
                message += f"• <b>{key}</b>: {value}\n"
    
    current_month = datetime.now().strftime("%B %Y")
    message += f"\n📅 <i>Period: {current_month}</i>"
    
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)

async def list_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List background workers (jobs)."""
    if not await check_admin(update):
        return
    
    await update.message.reply_text("⚙️ Fetching background jobs...")
    
    # Jobs are services with type 'worker' or 'cron'
    success, response = await make_render_request('GET', 'services')
    
    if not success:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")
        return
    
    if not response:
        await update.message.reply_text("📭 No services found.")
        return
    
    jobs = [s for s in response if s.get('type') in ['worker', 'cron', 'private']]
    
    if not jobs:
        await update.message.reply_text("📭 No background jobs found.")
        return
    
    message = f"⚙️ <b>Background Jobs ({len(jobs)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    for i, job in enumerate(jobs, 1):
        job_id = job.get('id', 'N/A')
        name = job.get('name', 'N/A')
        job_type = job.get('type', 'N/A')
        suspended = job.get('suspended', False)
        schedule = job.get('schedule', 'N/A') if job_type == 'cron' else 'Continuous'
        
        status = "⏸ Suspended" if suspended else "▶️ Running"
        
        message += f"{i}. <b>{name}</b> ({job_type})\n"
        message += f"   ID: <code>{job_id}</code>\n"
        message += f"   Schedule: {schedule} | {status}\n"
        
        if i < len(jobs):
            message += "   ━\n"
    
    if len(message) > 4000:
        message = message[:4000] + "\n... (truncated)"
    
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)

async def list_databases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List managed databases."""
    if not await check_admin(update):
        return
    
    await update.message.reply_text("🗄️ Fetching databases...")
    
    success, response = await make_render_request('GET', 'databases')
    
    if not success:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")
        return
    
    if not response:
        await update.message.reply_text("📭 No databases found.")
        return
    
    databases = response
    message = f"🗄️ <b>Managed Databases ({len(databases)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    for i, db in enumerate(databases, 1):
        db_id = db.get('id', 'N/A')
        name = db.get('name', 'N/A')
        db_type = db.get('databaseType', 'N/A')
        plan = db.get('plan', 'N/A')
        status = db.get('status', 'N/A')
        region = db.get('region', 'N/A')
        
        message += f"{i}. <b>{name}</b> ({db_type})\n"
        message += f"   ID: <code>{db_id}</code>\n"
        message += f"   Plan: {plan} | Status: {status}\n"
        message += f"   Region: {region}\n"
        
        if i < len(databases):
            message += "   ━\n"
    
    if len(message) > 4000:
        message = message[:4000] + "\n... (truncated)"
    
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)

# ===================== CALLBACK QUERY HANDLER =====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("service_"):
        service_id = data.replace("service_", "")
        success, response = await make_render_request('GET', f'services/{service_id}')
        if success:
            info_text = format_service_info(response)
            
            is_suspended = response.get('suspended', False)
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Redeploy", callback_data=f"redeploy_{service_id}"),
                    InlineKeyboardButton("⏸ Suspend" if not is_suspended else "▶️ Resume", 
                                       callback_data=f"toggle_suspend_{service_id}")
                ],
                [
                    InlineKeyboardButton("📜 Deployments", callback_data=f"deployments_{service_id}"),
                    InlineKeyboardButton("🔙 Back", callback_data="refresh_services")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(info_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        else:
            await query.edit_message_text(f"❌ Error: {response.get('error', 'Unknown error')}")
    
    elif data.startswith("redeploy_"):
        service_id = data.replace("redeploy_", "")
        success, response = await make_render_request('POST', f'services/{service_id}/deploys')
        if success:
            deploy_id = response.get('id', 'N/A')
            await query.edit_message_text(
                f"✅ Redeployment triggered for {service_id}!\n"
                f"Deployment ID: <code>{deploy_id}</code>",
                parse_mode=ParseMode.HTML
            )
        else:
            await query.edit_message_text(f"❌ Error: {response.get('error', 'Unknown error')}")
    
    elif data.startswith("toggle_suspend_"):
        service_id = data.replace("toggle_suspend_", "")
        # Check current status
        success, service_data = await make_render_request('GET', f'services/{service_id}')
        if not success:
            await query.edit_message_text(f"❌ Error: {service_data.get('error', 'Unknown error')}")
            return
        
        is_suspended = service_data.get('suspended', False)
        
        if is_suspended:
            # Resume
            data = {"suspended": False}
            success, response = await make_render_request('PATCH', f'services/{service_id}', data)
            action = "resumed"
        else:
            # Suspend
            data = {"suspended": True}
            success, response = await make_render_request('PATCH', f'services/{service_id}', data)
            action = "suspended"
        
        if success:
            await query.edit_message_text(f"✅ Service {service_id} {action} successfully.")
        else:
            await query.edit_message_text(f"❌ Error: {response.get('error', 'Unknown error')}")
    
    elif data.startswith("deployments_"):
        service_id = data.replace("deployments_", "")
        success, response = await make_render_request('GET', f'services/{service_id}/deployments')
        if success and response:
            deployments = response
            message = f"🚀 <b>Deployments ({len(deployments)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            
            for i, deploy in enumerate(deployments[:5], 1):
                deploy_id = deploy.get('id', 'N/A')
                status = deploy.get('status', 'N/A')
                created_at = deploy.get('createdAt', 'N/A')
                
                status_emoji = {
                    'live': '✅',
                    'build_failed': '❌',
                    'update_failed': '⚠️',
                    'building': '🔨',
                    'updating': '⚡',
                    'pending': '⏳',
                    'canceled': '🚫'
                }.get(status, '❓')
                
                message += f"{i}. {status_emoji} <b>{status.upper()}</b>\n"
                message += f"   ID: <code>{deploy_id}</code>\n"
                message += f"   Created: {created_at[:19] if created_at else 'N/A'}\n"
                
                if i < min(len(deployments), 5):
                    message += "   ━\n"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Trigger Deploy", callback_data=f"trigger_deploy_{service_id}")],
                [InlineKeyboardButton("🔙 Back to Service", callback_data=f"service_{service_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        else:
            await query.edit_message_text("📭 No deployments found.")
    
    elif data.startswith("trigger_deploy_"):
        service_id = data.replace("trigger_deploy_", "")
        success, response = await make_render_request('POST', f'services/{service_id}/deploys')
        if success:
            deploy_id = response.get('id', 'N/A')
            await query.edit_message_text(f"✅ Deployment triggered!\nID: <code>{deploy_id}</code>", parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(f"❌ Error: {response.get('error', 'Unknown error')}")
    
    elif data == "refresh_services":
        success, response = await make_render_request('GET', 'services')
        if success and response:
            services = response
            message = f"📋 <b>Your Services ({len(services)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            
            for i, service in enumerate(services[:10], 1):
                service_id = service.get('id', 'N/A')
                name = service.get('name', 'N/A')
                service_type = service.get('type', 'N/A')
                suspended = service.get('suspended', False)
                
                status = "⏸ Suspended" if suspended else "▶️ Running"
                
                message += f"{i}. <b>{name}</b>\n"
                message += f"   ID: <code>{service_id}</code>\n"
                message += f"   Type: {service_type} | {status}\n"
                
                if i < len(services[:10]):
                    message += "   ━\n"
            
            keyboard = []
            for service in services[:5]:
                service_id = service.get('id')
                name = service.get('name')[:15]
                keyboard.append([InlineKeyboardButton(f"📊 {name}", callback_data=f"service_{service_id}")])
            
            keyboard.append([
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_services"),
                InlineKeyboardButton("📈 Usage", callback_data="show_usage")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        else:
            await query.edit_message_text(f"❌ Error: {response.get('error', 'Unknown error') if response else 'No response'}")
    
    elif data == "show_usage":
        success, response = await make_render_request('GET', 'usage')
        if not success:
            await query.edit_message_text("⚠️ Usage statistics not available.")
            return
        
        message = "📊 <b>Usage Statistics</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        
        if isinstance(response, list):
            for item in response[:5]:
                service_type = item.get('type', 'Unknown')
                usage_amount = item.get('usage', 0)
                unit = item.get('unit', 'units')
                message += f"• <b>{service_type}</b>: {usage_amount} {unit}\n"
        elif isinstance(response, dict):
            for key, value in response.items():
                if key not in ['id', 'createdAt', 'updatedAt']:
                    message += f"• <b>{key}</b>: {value}\n"
        
        current_month = datetime.now().strftime("%B %Y")
        message += f"\n📅 <i>Period: {current_month}</i>"
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="refresh_services")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

# ===================== ERROR HANDLER =====================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors."""
    logger.error(f"Update {update} caused error {context.error}")

# ===================== MAIN FUNCTION =====================
def main() -> None:
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set")
        return
    
    if not RENDER_API_KEY:
        logger.error("RENDER_API_KEY environment variable is not set")
        return
    
    # Create Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("services", list_services))
    application.add_handler(CommandHandler("service", get_service))
    application.add_handler(CommandHandler("deployments", service_deployments))
    application.add_handler(CommandHandler("env", service_env_vars))
    application.add_handler(CommandHandler("suspend", suspend_service))
    application.add_handler(CommandHandler("resume", resume_service))
    application.add_handler(CommandHandler("redeploy", redeploy_service))
    application.add_handler(CommandHandler("restart", redeploy_service))  # Alias
    application.add_handler(CommandHandler("scale", scale_service))
    application.add_handler(CommandHandler("usage", show_usage))
    application.add_handler(CommandHandler("jobs", list_jobs))
    application.add_handler(CommandHandler("databases", list_databases))
    
    # Register callback query handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Register error handler
    application.add_error_handler(error_handler)
    
    # Start the Bot
    logger.info("Starting bot with polling...")
    
    # Create health server
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Bot is alive!')

        def log_message(self, format, *args):
            pass  # Silence logs

    def run_health_server():
        port = int(os.environ.get("PORT", 10000))
        httpd = HTTPServer(('0.0.0.0', port), HealthHandler)
        logger.info(f"✅ Health server on port {port}")
        httpd.serve_forever()

    # Start health server
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()