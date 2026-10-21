#!/usr/bin/env python3
"""Provision Hermes credentials from a read-only 1Password service account."""
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
TOKEN = Path(os.environ.get('BEDROCK_STATE', '/etc/bedrock')) / 'op-token'
VAULT = os.environ.get('HERMES_VAULT', 'Bedrock')
ITEM = os.environ.get('HERMES_ITEM', 'Hermes')
HOME = Path(os.environ.get('HERMES_HOME', '/opt/hermes-home'))


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.bedrock-')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def op(*args):
    env = os.environ.copy()
    env.pop('OP_CONNECT_HOST', None)
    env.pop('OP_CONNECT_TOKEN', None)
    env['OP_SERVICE_ACCOUNT_TOKEN'] = TOKEN.read_text().strip()
    # Captured output can include secrets and must never be logged.
    return run(['op', *args], env=env, stdout=subprocess.PIPE).stdout


def sync_secrets():
    item = json.loads(op('item', 'get', ITEM, '--vault', VAULT, '--format', 'json'))
    fields = {field.get('label'): field.get('value', '') for field in item.get('fields', [])}
    token = fields.get('TELEGRAM_BOT_TOKEN', '')
    chat = fields.get('TELEGRAM_CHAT_ID', '')
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token):
        raise ValueError('Invalid TELEGRAM_BOT_TOKEN in the selected instance secret item.')
    if not re.fullmatch(r'[1-9][0-9]*', chat):
        raise ValueError('TELEGRAM_CHAT_ID must be your positive private Telegram user/chat ID.')
    username = fields.get('HERMES_DASHBOARD_BASIC_AUTH_USERNAME', '')
    password = fields.get('HERMES_DASHBOARD_BASIC_AUTH_PASSWORD', '')
    secret = fields.get('HERMES_DASHBOARD_BASIC_AUTH_SECRET', '')
    if not re.fullmatch(r'[A-Za-z0-9_.@-]+', username):
        raise ValueError('Set HERMES_DASHBOARD_BASIC_AUTH_USERNAME in the selected instance secret item.')
    if len(password) < 16 or '\n' in password or '\r' in password:
        raise ValueError('HERMES_DASHBOARD_BASIC_AUTH_PASSWORD must contain at least 16 characters on one line.')
    if len(secret) < 32 or '\n' in secret or '\r' in secret:
        raise ValueError('HERMES_DASHBOARD_BASIC_AUTH_SECRET must contain at least 32 characters on one line.')
    content = (f'TELEGRAM_BOT_TOKEN={token}\nTELEGRAM_ALLOWED_USERS={chat}\nTELEGRAM_HOME_CHANNEL={chat}\n'
               f'HERMES_DASHBOARD_BASIC_AUTH_USERNAME={username}\n'
               f'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD={password}\n'
               f'HERMES_DASHBOARD_BASIC_AUTH_SECRET={secret}\n')
    fd, name = tempfile.mkstemp()
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
        run(['python3', str(ROOT / 'scripts/merge-env.py'), name, str(HOME / 'data/hermes/.env')])
    finally:
        os.unlink(name)
    print('Telegram credentials and private user allowlist synchronized.')


def main():
    if os.geteuid() != 0:
        raise ValueError('Run with sudo (or as root).')
    os.umask(0o077)
    if len(sys.argv) != 2:
        raise ValueError('Usage: provision.py login|sync-secrets')
    action = sys.argv[1]
    if action == 'login':
        if not TOKEN.exists():
            token = getpass.getpass(f'1Password service account token (read-only {VAULT}): ').strip()
            if not token:
                raise ValueError('Empty service account token.')
            atomic(TOKEN, token + '\n')
        op('vault', 'get', VAULT, '--format', 'json')
    elif action == 'sync-secrets':
        sync_secrets()
    else:
        raise ValueError('Unknown provisioning action.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        # CalledProcessError includes argv only; secrets are never passed in argv.
        print(f'Provisioning failed: {error}', file=sys.stderr)
        sys.exit(1)
