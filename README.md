Allows you to talk to a LLM at a specific API endpoint through Discord channels, with optional ST style character cards, lorebooks, or memory hooks. Channels/servers only.

Pulses every 120 seconds (configurable) to check for new Discord messages.


INSTRUCTIONS:
1. Configure Identity & Access: Copy .env.example to .env, then populate your DISCORD_BOT_TOKEN and LLM_API_KEY. Without these, the system remains silent. Optionally attach a path to your existing character card, lorebooks, or mem API hook.

2. Initialize the Environment: Run the startup script for your OS (./run.sh or run.bat). This creates a virtual environment and installs all dependencies automatically.

3. Verify Handshake: Watch the terminal for [DISCORD] Anchored to... followed by [SYSTEM] Worker starting. If you see those, the signal is live.


Made by Ronni & Val.
