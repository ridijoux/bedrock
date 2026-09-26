#!/usr/bin/env python3
"""Provision recovery material without exposing secrets in argv or logs."""
import configparser
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
CONFIG = Path('/root/.config/rclone/rclone.conf')
TOKEN = Path('/etc/bedrock/op-token')
VAULT = 'Bedrock'


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def atomic(path, value, uid=0, gid=0):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.bedrock-')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(name, uid, gid)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def op(*args):
    env = os.environ.copy()
    env.pop('OP_CONNECT_HOST', None)
    env.pop('OP_CONNECT_TOKEN', None)
    env['OP_SERVICE_ACCOUNT_TOKEN'] = TOKEN.read_text().strip()
    # No shell; captured output can include secrets and must never be logged.
    return run(['op', *args], env=env, stdout=subprocess.PIPE).stdout


def document_id():
    items = json.loads(op('item', 'list', '--vault', VAULT, '--format', 'json'))
    matches = [item for item in items if item['title'] == 'rclone.conf']
    if len(matches) > 1:
        raise ValueError('Multiple rclone.conf items in Bedrock; resolve the duplicate before continuing.')
    return matches[0]['id'] if matches else None


def parse_config(text):
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(text)
    crypt = config['hermes-crypt']
    if crypt.get('type') != 'crypt' or not crypt.get('password') or not crypt.get('remote'):
        raise ValueError('hermes-crypt must be a configured crypt remote.')
    if crypt.get('no_data_encryption', 'false').lower() != 'false':
        raise ValueError('Backup content encryption must be enabled.')
    remote = crypt['remote'].split(':', 1)[0]
    if ':' not in crypt['remote'] or remote not in config or config[remote].get('type') != 'drive':
        raise ValueError('hermes-crypt must point to a configured Google Drive remote.')
    if not config[remote].get('token'):
        raise ValueError('Google Drive OAuth token is missing.')
    return config


def identity(text):
    config = parse_config(text)
    crypt = config['hermes-crypt']
    # Compare stored values conservatively; never re-obscure existing keys.
    return tuple(crypt.get(key, '') for key in ('remote', 'password', 'password2', 'filename_encryption', 'directory_name_encryption'))


def sync_backup():
    local = CONFIG.read_text()
    parse_config(local)
    item_id = document_id()
    if item_id:
        saved = op('document', 'get', item_id, '--vault', VAULT)
        if identity(saved) != identity(local):
            raise ValueError('Local encryption settings differ from 1Password. Refusing to overwrite recovery keys.')
        if saved != local:
            op('document', 'edit', item_id, str(CONFIG), '--vault', VAULT)
    else:
        result = op('document', 'create', str(CONFIG), '--title', 'rclone.conf', '--vault', VAULT, '--format', 'json')
        item_id = json.loads(result)['id']
    if op('document', 'get', item_id, '--vault', VAULT) != local:
        raise ValueError('Recovery document read-back verification failed.')
    print('Backup recovery configuration verified in 1Password.')


def authorize_drive(env):
    # Debian 13 ships rclone 1.60: --no-output is unavailable. Its config
    # command prints the final OAuth token on stdout. Only forward the local
    # browser URL; rclone's progress/authorization notices go to stderr.
    command = ['rclone', 'config', 'create', 'hermes-drive', 'drive', 'scope', 'drive',
               'config_is_local', 'true', 'config_auth_no_browser', 'true']
    with subprocess.Popen(command, env=env, stdout=subprocess.PIPE, text=True) as process:
        for line in process.stdout:
            match = re.search(r'http://(?:127\.0\.0\.1|localhost):53682/[^\s]+', line)
            if match:
                print(match.group(), flush=True)
        if process.wait():
            raise ValueError('Google Drive authorization failed; rerun the installer with the SSH tunnel.')


def setup_backup(recovery=False):
    item_id = document_id()  # Network/auth errors must never mean "create new keys".
    if CONFIG.exists():
        parse_config(CONFIG.read_text())
        if item_id and identity(op('document', 'get', item_id, '--vault', VAULT)) != identity(CONFIG.read_text()):
            raise ValueError('Local backup keys conflict with 1Password; stopping without changing either.')
    elif item_id:
        saved = op('document', 'get', item_id, '--vault', VAULT)
        parse_config(saved)
        atomic(CONFIG, saved)
        print('Backup configuration recovered from 1Password.')
    elif recovery:
        raise ValueError('No recovery document in Bedrock. Cannot restore; no new keys were generated.')
    else:
        CONFIG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Work in a staging file: interrupted OAuth never publishes a partial config.
        pending = CONFIG.with_name('rclone.pending.conf')
        if not pending.exists():
            atomic(pending, '')
        env = os.environ.copy()
        env['RCLONE_CONFIG'] = str(pending)
        print('Google Drive authorization: use SSH with -L 53682:127.0.0.1:53682.', flush=True)
        print('Open the localhost URL printed below in your computer browser.', flush=True)
        authorize_drive(env)
        config = configparser.ConfigParser(interpolation=None)
        config.read(pending)
        def obscure():
            return run(['rclone', 'obscure', '-'], input=secrets.token_urlsafe(48), stdout=subprocess.PIPE).stdout.strip()
        config['hermes-crypt'] = {
            'type': 'crypt', 'remote': 'hermes-drive:bedrock-backups',
            'filename_encryption': 'standard', 'directory_name_encryption': 'true',
            'password': obscure(), 'password2': obscure(),
        }
        import io
        output = io.StringIO()
        config.write(output)
        parse_config(output.getvalue())
        atomic(CONFIG, output.getvalue())
        pending.unlink()
    CONFIG.chmod(0o600)
    sync_backup()  # Escrow and read-back BEFORE any upload or retention.
    if not recovery:
        run(['rclone', '--config', str(CONFIG), 'mkdir', 'hermes-crypt:'])
    run(['rclone', '--config', str(CONFIG), 'lsf', 'hermes-crypt:', '--max-depth', '1'], stdout=subprocess.DEVNULL)


def sync_secrets():
    item = json.loads(op('item', 'get', 'Hermes', '--vault', VAULT, '--format', 'json'))
    fields = {field.get('label'): field.get('value', '') for field in item.get('fields', [])}
    token = fields.get('TELEGRAM_BOT_TOKEN', '')
    chat = fields.get('TELEGRAM_CHAT_ID', '')
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token):
        raise ValueError('Invalid TELEGRAM_BOT_TOKEN in Bedrock/Hermes.')
    if not re.fullmatch(r'[1-9][0-9]*', chat):
        raise ValueError('TELEGRAM_CHAT_ID must be your positive private Telegram user/chat ID.')
    username = fields.get('HERMES_DASHBOARD_BASIC_AUTH_USERNAME', '')
    password = fields.get('HERMES_DASHBOARD_BASIC_AUTH_PASSWORD', '')
    secret = fields.get('HERMES_DASHBOARD_BASIC_AUTH_SECRET', '')
    if not re.fullmatch(r'[A-Za-z0-9_.@-]+', username):
        raise ValueError('Set HERMES_DASHBOARD_BASIC_AUTH_USERNAME in Bedrock/Hermes.')
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
        run(['python3', str(ROOT / 'scripts/merge-env.py'), name, str(ROOT / 'data/hermes/.env')])
    finally:
        os.unlink(name)
    atomic(ROOT / 'ops.env', f'TELEGRAM_BOT_TOKEN={token}\nTELEGRAM_CHAT_ID={chat}\n')
    print('Telegram credentials and private user allowlist synchronized.')


def main():
    if os.geteuid() != 0:
        raise ValueError('Run with sudo (or as root).')
    os.umask(0o077)
    action = sys.argv[1]
    if action == 'login':
        if not TOKEN.exists():
            token = getpass.getpass('1Password service account token (read/write Bedrock): ').strip()
            if not token:
                raise ValueError('Empty service account token.')
            atomic(TOKEN, token + '\n')
        op('vault', 'get', VAULT, '--format', 'json')
    elif action == 'setup-backup':
        setup_backup()
    elif action == 'recover-backup':
        setup_backup(recovery=True)
    elif action == 'sync-backup':
        sync_backup()
    elif action == 'validate-backup':
        parse_config(CONFIG.read_text())
    elif action == 'sync-secrets':
        sync_secrets()
    else:
        raise ValueError('Unknown provisioning action.')


if __name__ == '__main__':
    try:
        main()
    except configparser.Error:
        # Parser diagnostics can include the offending line and its secrets.
        sys.exit('Provisioning failed: invalid rclone configuration format.')
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        # CalledProcessError includes argv only; secrets are never passed in argv.
        print(f'Provisioning failed: {error}', file=sys.stderr)
        sys.exit(1)
