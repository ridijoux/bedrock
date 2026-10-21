# Imports expose recipes at the root, keeping existing operator commands stable.
import 'just/host.just'
import 'services/hermes/recipes.just'
import 'services/gatelet/recipes.just'

repo := justfile_directory()

default:
    @just --list

# Explicit operations for gonzabot.
gonzabot-install:
    HERMES_INSTANCE=gonzabot just --justfile {{quote(repo)}}/Justfile install

gonzabot-setup:
    HERMES_INSTANCE=gonzabot just --justfile {{quote(repo)}}/Justfile setup

gonzabot-start:
    HERMES_INSTANCE=gonzabot just --justfile {{quote(repo)}}/Justfile start

gonzabot-stop:
    HERMES_INSTANCE=gonzabot just --justfile {{quote(repo)}}/Justfile stop

gonzabot-restart:
    HERMES_INSTANCE=gonzabot just --justfile {{quote(repo)}}/Justfile restart

gonzabot-status:
    HERMES_INSTANCE=gonzabot just --justfile {{quote(repo)}}/Justfile status

gonzabot-logs:
    HERMES_INSTANCE=gonzabot just --justfile {{quote(repo)}}/Justfile logs

gonzabot-gatelet-start:
    HERMES_INSTANCE=gonzabot just --justfile {{quote(repo)}}/Justfile gatelet-start

gonzabot-gatelet-stop:
    HERMES_INSTANCE=gonzabot just --justfile {{quote(repo)}}/Justfile gatelet-stop

gonzabot-gatelet-logs:
    HERMES_INSTANCE=gonzabot just --justfile {{quote(repo)}}/Justfile gatelet-logs


# Explicit operations for saruman.
saruman-install:
    HERMES_INSTANCE=saruman just --justfile {{quote(repo)}}/Justfile install

saruman-setup:
    HERMES_INSTANCE=saruman just --justfile {{quote(repo)}}/Justfile setup

saruman-start:
    HERMES_INSTANCE=saruman just --justfile {{quote(repo)}}/Justfile start

saruman-stop:
    HERMES_INSTANCE=saruman just --justfile {{quote(repo)}}/Justfile stop

saruman-restart:
    HERMES_INSTANCE=saruman just --justfile {{quote(repo)}}/Justfile restart

saruman-status:
    HERMES_INSTANCE=saruman just --justfile {{quote(repo)}}/Justfile status

saruman-logs:
    HERMES_INSTANCE=saruman just --justfile {{quote(repo)}}/Justfile logs

saruman-gatelet-start:
    HERMES_INSTANCE=saruman just --justfile {{quote(repo)}}/Justfile gatelet-start

saruman-gatelet-stop:
    HERMES_INSTANCE=saruman just --justfile {{quote(repo)}}/Justfile gatelet-stop

saruman-gatelet-logs:
    HERMES_INSTANCE=saruman just --justfile {{quote(repo)}}/Justfile gatelet-logs
