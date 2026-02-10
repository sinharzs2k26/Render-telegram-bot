#!/usr/bin/env python3
"""
Render.com Management Telegram Bot
Author: Your Name
Description: Manage Render services via Telegram bot using polling
Requirements: python-telegram-bot, requests
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
    Updater, Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ===================== CONFIGURATION =====================
# Get these from environment variables (set in Render dashboard)
TELEGRAM_BOT_TOKEN = os.environ.get('BOT_TOKEN')
RENDER_API_KEY = os.environ.get('RENDER_TOKEN')

# Render API configuration
RENDER_API_BASE = "https://api.render.com/v1"
HEADERS = {
    "Authorization": f"Bearer {RENDER_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

# Bot admin - your Telegram user ID (optional for authorization)
ADMIN_USER_ID = os.environ.get('USER_ID')

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
        return True  # No admin restriction if ADMIN_USER_ID not set
    
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
        
        # Some endpoints return 204 No Content
        if response.status_code == 204:
            return True, {"message": "Operation successful"}
        
        return True, response.json()
    
    # At the end of make_render_request, ensure you return empty dict/list:
    except requests.exceptions.RequestException as e:
        logger.error(f"Render API error: {e}")
        return False, {"error": str(e), "data": None}  # Always return a dict

async def format_service_info(service: dict) -> str:
    """Format service information for display."""
    service_id = service.get('id', 'N/A')
    name = service.get('name', 'N/A')
    service_type = service.get('type', 'N/A')
    owner_id = service.get('ownerId', 'N/A')
    repo = service.get('repo', 'N/A')
    branch = service.get('branch', 'N/A')
    created_at = service.get('createdAt', 'N/A')
    updated_at = service.get('updatedAt', 'N/A')
    suspended = service.get('suspended', 'N/A')
    auto_deploy = service.get('autoDeploy', 'N/A')
    
    # Get service-specific details
    details = service.get('serviceDetails', {})
    env_vars = details.get('envVars', [])
    plan = details.get('plan', 'free')
    num_instances = details.get('numInstances', 1)
    
    # Get deployment info
    deployments = service.get('deployments', [])
    latest_deploy = deployments[0] if deployments else {}
    deploy_status = latest_deploy.get('status', 'N/A')
    
    info = f"""
📦 <b>{name}</b> ({service_id})
━━━━━━━━━━━━━━━━━━━━━━━━
• Type: {service_type}
• Status: {deploy_status}
• Suspended: {'✅ Yes' if suspended else '❌ No'}
• Plan: {plan}
• Instances: {num_instances}
• Auto-deploy: {'✅ Enabled' if auto_deploy else '❌ Disabled'}
• Repository: {repo}
• Branch: {branch}
• Owner: {owner_id}
• Created: {created_at[:10] if isinstance(created_at, str) else created_at}
• Updated: {updated_at[:10] if isinstance(updated_at, str) else updated_at}
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
• /deployments <code>service_id</code> - List deployments
• /logs <code>service_id</code> - Get service logs
• /env <code>service_id</code> - Show environment variables
• /domains <code>service_id</code> - List custom domains
• /metrics <code>service_id</code> - Get service metrics
• /usage - Check usage statistics

<b>Quick Actions:</b>
• /suspend <code>service_id</code> - Suspend a service
• /resume <code>service_id</code> - Resume a service
• /redeploy <code>service_id</code> - Redeploy a service
• /restart <code>service_id</code> - Restart a service
• /scale <code>service_id</code> <code>num_instances</code> - Scale service instances

<b>Management:</b>
• /create_service - Create a new service (interactive)
• /delete_service <code>service_id</code> - Delete a service
• /update_env <code>service_id</code> - Update environment variables

Type /help for more detailed information.
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
• /services - List all your Render services

<b>Service Information:</b>
• /info <code>service_id</code> - Get detailed service info
• /deployments <code>service_id</code> - List service deployments
• /logs <code>service_id</code> - Get recent logs (last 100 lines)
• /env <code>service_id</code> - Show environment variables
• /domains <code>service_id</code> - List custom domains
• /metrics <code>service_id</code> - Get service metrics (CPU, Memory)

<b>Service Actions:</b>
• /suspend <code>service_id</code> - Suspend (pause) a service
• /resume <code>service_id</code> - Resume a suspended service
• /redeploy <code>service_id</code> - Trigger redeployment
• /restart <code>service_id</code> - Restart service instances
• /scale <code>service_id</code> <code>num</code> - Scale to N instances

<b>Management:</b>
• /create_service - Interactive service creation
• /delete_service <code>service_id</code> - Delete a service
• /update_env <code>service_id</code> - Update env vars (interactive)
• /usage - Get account usage statistics

<b>Cron Jobs:</b>
• /cron_jobs - List all cron jobs
• /run_cron <code>cron_id</code> - Run cron job manually

<b>Databases:</b>
• /databases - List managed databases
• /backups <code>db_id</code> - List database backups

<b>Examples:</b>
<code>/services</code>
<code>/info srv-abc123def456</code>
<code>/suspend srv-abc123def456</code>
<code>/scale srv-abc123def456 2</code>
<code>/logs srv-abc123def456</code>
    """
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def list_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all Render services."""
    if not await check_admin(update):
        return
    
    await update.message.reply_text("📡 Fetching your services...")
    
    success, response = await make_render_request('GET', 'services', {'limit': 50})
    
    if not success:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")
        return
    
    services = response
    if not services:
        await update.message.reply_text("📭 No services found.")
        return
    
    message = f"📋 <b>Your Services ({len(services)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    for i, service in enumerate(services, 1):
        service_id = service.get('id', 'N/A')
        name = service.get('name', 'N/A')
        service_type = service.get('type', 'N/A')
        suspended = service.get('suspended', False)
        status = "⏸ Suspended" if suspended else "▶️ Running"
        
        deployments = service.get('deployments', [])
        deploy_status = deployments[0].get('status', 'unknown') if deployments else 'unknown'
        
        message += f"{i}. <b>{name}</b>\n"
        message += f"   ID: <code>{service_id}</code>\n"
        message += f"   Type: {service_type} | Status: {deploy_status} | {status}\n"
        
        if i < len(services):
            message += "   ━\n"
    
    # Add quick action buttons
    keyboard = []
    for service in services[:5]:  # Show buttons for first 5 services
        service_id = service.get('id')
        name = service.get('name')[:15]  # Truncate name
        keyboard.append([
            InlineKeyboardButton(
                f"📊 {name}",
                callback_data=f"service_info_{service_id}"
            )
        ])
    
    # Add general action buttons
    keyboard.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="refresh_services"),
        InlineKeyboardButton("📈 Usage", callback_data="show_usage")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Split message if too long (Telegram limit: 4096 chars)
    if len(message) > 4000:
        message = message[:4000] + "\n... (truncated)"
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )

async def service_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get detailed information about a specific service."""
    if not await check_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Please provide a service ID.\nExample: /info srv-abc123def456")
        return
    
    service_id = context.args[0]
    await update.message.reply_text(f"🔍 Fetching info for service: {service_id}")
    
    success, response = await make_render_request('GET', f'services/{service_id}')
    
    if not success:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")
        return
    
    info_text = format_service_info(response)
    
    # Create action buttons for this service
    keyboard = [
        [
            InlineKeyboardButton("🔄 Redeploy", callback_data=f"redeploy_{service_id}"),
            InlineKeyboardButton("⏸ Suspend" if not response.get('suspended') else "▶️ Resume", 
                               callback_data=f"toggle_suspend_{service_id}")
        ],
        [
            InlineKeyboardButton("📜 Logs", callback_data=f"logs_{service_id}"),
            InlineKeyboardButton("⚙️ Env Vars", callback_data=f"env_{service_id}")
        ],
        [
            InlineKeyboardButton("📊 Metrics", callback_data=f"metrics_{service_id}"),
            InlineKeyboardButton("🚀 Deployments", callback_data=f"deployments_{service_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back to Services", callback_data="refresh_services")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(info_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def service_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get service logs."""
    if not await check_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Please provide a service ID.\nExample: /logs srv-abc123def456")
        return
    
    service_id = context.args[0]
    await update.message.reply_text(f"📜 Fetching logs for service: {service_id}")
    
    success, response = await make_render_request('GET', f'services/{service_id}/logs')
    
    if not success:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")
        return
    
    logs = response.get('logs', '')
    if not logs:
        await update.message.reply_text("📭 No logs available.")
        return
    
    # Truncate logs if too long for Telegram (4096 chars)
    if len(logs) > 4000:
        logs = logs[:4000] + "\n\n... (logs truncated)"
    
    await update.message.reply_text(f"<pre>{logs}</pre>", parse_mode=ParseMode.HTML)

async def service_deployments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List service deployments."""
    if not await check_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Please provide a service ID.\nExample: /deployments srv-abc123def456")
        return
    
    service_id = context.args[0]
    await update.message.reply_text(f"🚀 Fetching deployments for service: {service_id}")
    
    success, response = await make_render_request('GET', f'services/{service_id}/deployments', {'limit': 10})
    
    if not success:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")
        return
    
    deployments = response
    if not deployments:
        await update.message.reply_text("📭 No deployments found.")
        return
    
    message = f"🚀 <b>Recent Deployments ({len(deployments)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    for i, deploy in enumerate(deployments, 1):
        deploy_id = deploy.get('id', 'N/A')
        status = deploy.get('status', 'N/A')
        commit_id = deploy.get('commit', {}).get('id', 'N/A')[:8]
        commit_msg = deploy.get('commit', {}).get('message', 'N/A')
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
        message += f"   Commit: {commit_id} - {commit_msg[:50]}\n"
        message += f"   Created: {created_at[:19] if isinstance(created_at, str) else created_at}\n"
        
        if i < len(deployments):
            message += "   ━\n"
    
    # Add action buttons
    keyboard = [
        [
            InlineKeyboardButton("🔄 Trigger Deploy", callback_data=f"trigger_deploy_{service_id}"),
            InlineKeyboardButton("↩️ Rollback", callback_data=f"rollback_{service_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back to Service", callback_data=f"service_info_{service_id}")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Split message if too long
    if len(message) > 4000:
        message = message[:4000] + "\n... (truncated)"
    
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
    
    success, response = await make_render_request('POST', f'services/{service_id}/suspend')
    
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
    
    success, response = await make_render_request('POST', f'services/{service_id}/resume')
    
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
    
    success, response = await make_render_request('POST', f'services/{service_id}/deploys')
    
    if success:
        deploy_id = response.get('id', 'N/A')
        await update.message.reply_text(f"✅ Redeployment triggered!\nDeployment ID: <code>{deploy_id}</code>", 
                                 parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")

async def scale_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scale service instances."""
    if not await check_admin(update):
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Please provide service ID and number of instances.\nExample: /scale srv-abc123def456 2")
        return
    
    service_id = context.args[0]
    try:
        num_instances = int(context.args[1])
        if num_instances < 1:
            await update.message.reply_text("❌ Number of instances must be at least 1.")
            return
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid number for instances.")
        return
    
    await update.message.reply_text(f"📊 Scaling service {service_id} to {num_instances} instance(s)")
    
    # First get current service details
    success, service_info = make_render_request('GET', f'services/{service_id}')
    if not success:
        await update.message.reply_text(f"❌ Error fetching service: {service_info.get('error', 'Unknown error')}")
        return
    
    # Update the numInstances in serviceDetails
    service_info['serviceDetails']['numInstances'] = num_instances
    
    success, response = await make_render_request('PATCH', f'services/{service_id}', service_info)
    
    if success:
        await update.message.reply_text(f"✅ Service {service_id} scaled to {num_instances} instance(s).")
    else:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")

async def show_usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show account usage statistics."""
    if not await check_admin(update):
        return
    
    await update.message.reply_text("📈 Fetching usage statistics...")
    
    success, response = await make_render_request('GET', 'usage')
    
    if not success:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")
        return
    
    usage = response
    message = "📊 <b>Usage Statistics</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    # Parse and display usage
    for item in usage:
        service_type = item.get('type', 'Unknown')
        usage_amount = item.get('usage', 0)
        limit = item.get('limit', 'Unlimited')
        unit = item.get('unit', 'units')
        
        message += f"• <b>{service_type}</b>: {usage_amount} {unit}"
        if limit != 'Unlimited':
            message += f" / {limit} {unit}"
        message += "\n"
    
    # Add current month
    current_month = datetime.now().strftime("%B %Y")
    message += f"\n📅 <i>Period: {current_month}</i>"
    
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)

async def list_cron_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all cron jobs."""
    if not await check_admin(update):
        return
    
    await update.message.reply_text("⏰ Fetching cron jobs...")
    
    success, response = await make_render_request('GET', 'crons', {'limit': 20})
    
    if not success:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")
        return
    
    crons = response
    if not crons:
        await update.message.reply_text("📭 No cron jobs found.")
        return
    
    message = f"⏰ <b>Cron Jobs ({len(crons)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    for i, cron in enumerate(crons, 1):
        cron_id = cron.get('id', 'N/A')
        name = cron.get('name', 'N/A')
        schedule = cron.get('schedule', 'N/A')
        last_run = cron.get('lastRunAt', 'Never')
        next_run = cron.get('nextRunAt', 'N/A')
        service_id = cron.get('serviceId', 'N/A')
        
        message += f"{i}. <b>{name}</b>\n"
        message += f"   ID: <code>{cron_id}</code>\n"
        message += f"   Service: <code>{service_id}</code>\n"
        message += f"   Schedule: {schedule}\n"
        message += f"   Last Run: {last_run[:19] if isinstance(last_run, str) else last_run}\n"
        message += f"   Next Run: {next_run[:19] if isinstance(next_run, str) else next_run}\n"
        
        if i < len(crons):
            message += "   ━\n"
    
    # Add action buttons for first 3 cron jobs
    keyboard = []
    for cron in crons[:3]:
        cron_id = cron.get('id')
        name = cron.get('name')[:15]
        keyboard.append([
            InlineKeyboardButton(f"▶️ Run {name}", callback_data=f"run_cron_{cron_id}")
        ])
    
    keyboard.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="refresh_crons")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if len(message) > 4000:
        message = message[:4000] + "\n... (truncated)"
    
    await update.message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def list_databases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List managed databases."""
    if not await check_admin(update):
        return
    
    await update.message.reply_text("🗄️ Fetching databases...")
    
    success, response = await make_render_request('GET', 'databases', {'limit': 20})
    
    if not success:
        await update.message.reply_text(f"❌ Error: {response.get('error', 'Unknown error')}")
        return
    
    databases = response
    if not databases:
        await update.message.reply_text("📭 No databases found.")
        return
    
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

async def create_service_interactive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start interactive service creation."""
    if not await check_admin(update):
        return
    
    # This is a simplified version - you'd need to implement a conversation handler
    # For simplicity, we'll provide instructions
    instructions = """
🆕 <b>Creating a New Service</b>

To create a service via API, you need to provide:
1. Service name
2. Repository URL
3. Branch name
4. Service type (web, worker, cron, etc.)
5. Build/start commands
6. Environment variables

<b>Example API Request:</b>
<code>POST /services</code>
{
  "name": "my-web-app",
  "type": "web",
  "repo": "https://github.com/username/repo",
  "branch": "main",
  "buildCommand": "npm install && npm run build",
  "startCommand": "npm start",
  "plan": "free",
  "envVars": [
    {"key": "NODE_ENV", "value": "production"}
  ]
}

For now, use the Render dashboard for complex service creation.
Simple services can be created with /create_simple_service.
    """
    
    await update.message.reply_text(instructions, parse_mode=ParseMode.HTML)

# ===================== CALLBACK QUERY HANDLER =====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("service_info_"):
        service_id = data.replace("service_info_", "")
        success, response = await make_render_request('GET', f'services/{service_id}')
        if success:
            info_text = format_service_info(response)
            
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Redeploy", callback_data=f"redeploy_{service_id}"),
                    InlineKeyboardButton("⏸ Suspend" if not response.get('suspended') else "▶️ Resume", 
                                       callback_data=f"toggle_suspend_{service_id}")
                ],
                [
                    InlineKeyboardButton("📜 Logs", callback_data=f"logs_{service_id}"),
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
        # First check current status
        success, service_data = make_render_request('GET', f'services/{service_id}')
        if not success:
            await query.edit_message_text(f"❌ Error: {service_data.get('error', 'Unknown error')}")
            return
        
        is_suspended = service_data.get('suspended', False)
        
        if is_suspended:
            # Resume the service
            success, response = await make_render_request('POST', f'services/{service_id}/resume')
            action = "resumed"
        else:
            # Suspend the service
            success, response = await make_render_request('POST', f'services/{service_id}/suspend')
            action = "suspended"
        
        if success:
            await query.edit_message_text(f"✅ Service {service_id} {action} successfully.")
        else:
            await query.edit_message_text(f"❌ Error: {response.get('error', 'Unknown error')}")
    
    elif data.startswith("logs_"):
        service_id = data.replace("logs_", "")
        success, response = await make_render_request('GET', f'services/{service_id}/logs')
        if success:
            logs = response.get('logs', '')
            if not logs:
                await query.edit_message_text("📭 No logs available.")
            else:
                if len(logs) > 4000:
                    logs = logs[:4000] + "\n\n... (logs truncated)"
                await query.edit_message_text(f"<pre>{logs}</pre>", parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(f"❌ Error: {response.get('error', 'Unknown error')}")
    
    elif data == "refresh_services":
        success, response = await make_render_request('GET', 'services', {'limit': 50})
        if success:
            services = response
            message = f"📋 <b>Your Services ({len(services)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            
            for i, service in enumerate(services[:10], 1):  # Show first 10
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
            
            # Recreate buttons
            keyboard = []
            for service in services[:5]:
                service_id = service.get('id')
                name = service.get('name')[:15]
                keyboard.append([
                    InlineKeyboardButton(
                        f"📊 {name}",
                        callback_data=f"service_info_{service_id}"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_services"),
                InlineKeyboardButton("📈 Usage", callback_data="show_usage")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if len(message) > 4000:
                message = message[:4000] + "\n... (truncated)"
            
            await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        else:
            await query.edit_message_text(f"❌ Error: {response.get('error', 'Unknown error')}")
    
    elif data == "show_usage":
        success, response = await make_render_request('GET', 'usage')
        if success:
            usage = response
            message = "📊 <b>Usage Statistics</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            
            for item in usage[:10]:  # Show first 10 items
                service_type = item.get('type', 'Unknown')
                usage_amount = item.get('usage', 0)
                limit = item.get('limit', 'Unlimited')
                unit = item.get('unit', 'units')
                
                message += f"• <b>{service_type}</b>: {usage_amount} {unit}"
                if limit != 'Unlimited':
                    message += f" / {limit} {unit}"
                message += "\n"
            
            current_month = datetime.now().strftime("%B %Y")
            message += f"\n📅 <i>Period: {current_month}</i>"
            
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="refresh_services")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        else:
            await query.edit_message_text(f"❌ Error: {response.get('error', 'Unknown error')}")
    
    elif data == "refresh_crons":
        success, response = await make_render_request('GET', 'crons', {'limit': 20})
        if success:
            crons = response
            if not crons:
                await query.edit_message_text("📭 No cron jobs found.")
                return
            
            message = f"⏰ <b>Cron Jobs ({len(crons)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            
            for i, cron in enumerate(crons[:10], 1):
                cron_id = cron.get('id', 'N/A')
                name = cron.get('name', 'N/A')
                schedule = cron.get('schedule', 'N/A')
                last_run = cron.get('lastRunAt', 'Never')
                
                message += f"{i}. <b>{name}</b>\n"
                message += f"   ID: <code>{cron_id}</code>\n"
                message += f"   Schedule: {schedule}\n"
                message += f"   Last Run: {last_run[:19] if isinstance(last_run, str) else last_run}\n"
                
                if i < len(crons[:10]):
                    message += "   ━\n"
            
            # Add action buttons
            keyboard = []
            for cron in crons[:3]:
                cron_id = cron.get('id')
                name = cron.get('name')[:15]
                keyboard.append([
                    InlineKeyboardButton(f"▶️ Run {name}", callback_data=f"run_cron_{cron_id}")
                ])
            
            keyboard.append([
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_crons")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if len(message) > 4000:
                message = message[:4000] + "\n... (truncated)"
            
            await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        else:
            await query.edit_message_text(f"❌ Error: {response.get('error', 'Unknown error')}")
    
    elif data.startswith("run_cron_"):
        cron_id = data.replace("run_cron_", "")
        success, response = await make_render_request('POST', f'crons/{cron_id}/runs')
        if success:
            await query.edit_message_text(f"✅ Cron job {cron_id} triggered successfully.")
        else:
            await query.edit_message_text(f"❌ Error: {response.get('error', 'Unknown error')}")

# ===================== ERROR HANDLER =====================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors."""
    logger.error(f"Update {update} caused error {context.error}")

# ===================== MAIN FUNCTION =====================
def main() -> None:
    """Start the bot."""
    # Check environment variables
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set")
        return
    
    if not RENDER_API_KEY:
        logger.error("RENDER_API_KEY environment variable is not set")
        return
    
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("services", list_services))
    application.add_handler(CommandHandler("info", service_info))
    application.add_handler(CommandHandler("logs", service_logs))
    application.add_handler(CommandHandler("deployments", service_deployments))
    application.add_handler(CommandHandler("suspend", suspend_service))
    application.add_handler(CommandHandler("resume", resume_service))
    application.add_handler(CommandHandler("redeploy", redeploy_service))
    application.add_handler(CommandHandler("restart", redeploy_service))  # Alias for redeploy
    application.add_handler(CommandHandler("scale", scale_service))
    application.add_handler(CommandHandler("usage", show_usage))
    application.add_handler(CommandHandler("cron_jobs", list_cron_jobs))
    application.add_handler(CommandHandler("databases", list_databases))
    application.add_handler(CommandHandler("create_service", create_service_interactive))
    
    # Register callback query handler for buttons
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Register error handler
    application.add_error_handler(error_handler)
    
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Bot is alive!')
        
        def log_message(self, format, *args):
            pass  # Silence logs

    def run_health_server():
        port = int(os.environ.get("PORT", 8080))
        httpd = HTTPServer(('0.0.0.0', port), HealthHandler)
        logger.info(f"✅ Health server on port {port}")
        httpd.serve_forever()
    
    # Start health server
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    

if __name__ == '__main__':
    main()