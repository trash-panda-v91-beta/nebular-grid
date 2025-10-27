# Nebular Grid Agent Guidelines

## Commands
- Build/Run: `just` (shows available tasks)
- Lint YAML: `yamllint .` 
- Format YAML: `yamlfmt .`
- Test: Use `just` to run specific tasks (check justfile)
- Single test: Use appropriate `just` command per test

## Code Conventions
- Shell: `bash -euo pipefail`
- YAML:
  - Double quotes for strings
  - 2-space indentation
  - Include document start marker (`---`)
  - Block style for arrays
- Nix: Follow standard Nixpkgs formatting
- Naming: Use kebab-case for files and commands
- Error handling: Use `gum confirm` for user interactions
- Command output: Use `just log` for formatted logging
- Template rendering: Use minijinja for templating

## Project Structure
- `/clusters/{name}` - Cluster configurations
- Use `mod.just` files for modularity
- Each module provides its own commands via `just`