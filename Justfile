# Imports expose recipes at the root, keeping existing operator commands stable.
import 'just/host.just'
import 'services/hermes/recipes.just'
import 'services/gatelet/recipes.just'

repo := justfile_directory()

default:
    @just --list
