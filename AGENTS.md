# Agent Setup Notes

This repository is intended to be installed by coding agents for users who want
phone access to local Codex/tmux terminals.

Recommended agent workflow:

1. Run `phonecodex doctor` and report missing tools.
2. Install missing system tools only with user approval.
3. Run `phonecodex install`.
4. Run `phonecodex codex NAME DIR` for the target project.
5. Give the user the URL printed by `phonecodex list`.

Do not expose PhoneCodex ports publicly. Prefer Tailscale. The toolbar API can paste
text and send control keys to the user's terminal.

