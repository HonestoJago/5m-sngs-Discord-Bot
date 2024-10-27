# Discord SNG Bot

A Discord bot designed to manage Sit-and-Go (SNG) poker tournaments. The bot provides automated tournament management with features like player registration, game status tracking, and automated cleanup.

## Features

- Create and manage SNG tournaments with up to 8 players
- Automated game start when maximum players are reached
- Role-based notifications for new games
- Automatic cleanup of inactive games
- Configurable designated channels
- Comprehensive logging system
- Error handling and retry mechanisms

## Prerequisites

Before setting up the bot, you'll need:
- Python 3.8 or higher
- A Discord account with administrator access to your server
- A Discord application and bot token from the [Discord Developer Portal](https://discord.com/developers/applications)

## Discord Server Setup

1. Enable Developer Mode in Discord:
   - User Settings → App Settings → Advanced → Developer Mode

2. Create necessary roles and channels:
   - Create a role for SNG players (copy its ID for ROLE_ID)
   - Create a dedicated channel for the bot (copy its ID for DESIGNATED_CHANNELS)

3. Required Bot Permissions:
   The bot needs the following permissions:
   - Send Messages
   - Manage Messages (to delete non-command messages)
   - Read Message History
   - View Channels
   - Mention @everyone, @here, and All Roles
   - Use Slash Commands
   - applications.commands (scopes)
   - guilds.channels.read (scopes)
   - dm.channels.messages.write (scopes)
   
## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/discord-sng-bot.git
   cd discord-sng-bot
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Linux/Mac:
   # source venv/bin/activate
   ```

3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure the bot:
   - Rename `.env.example` to `.env`
   - Edit `.env` and fill in your configuration values
   - See Configuration section below for details on each setting

5. Run the bot:
   ```bash
   python bot.py
   ```

## Configuration

The bot uses environment variables for configuration. Copy `.env.example` to `.env` and configure the following:

- `DISCORD_BOT_TOKEN` (required): Your bot's token from Discord Developer Portal
- `DESIGNATED_CHANNELS` (required): Channel ID(s) where the bot will operate
- `ADMIN_USER_ID` (required): Discord user ID of the admin
- `ROLE_ID` (required): Discord role ID to ping for new games
- `TEST_MODE` (optional): Set to true to disable role pings during testing
- `PIN_BOT_ID` (optional): Bot ID for pinned messages

See `.env.example` for detailed descriptions of each variable.

## Usage

### Commands
- `/start` - Start a new SNG tournament (requires appropriate role)

### Game Flow
1. Use `/start` to create a new game
2. Players click buttons to join
3. Game starts automatically at 8 players or manually with 2+ players
4. Bot manages cleanup after game completion

## Troubleshooting

Common issues:
1. Bot not responding to commands:
   - Verify bot token is correct
   - Check channel IDs in DESIGNATED_CHANNELS
   - Ensure bot has proper permissions

2. Messages not being deleted:
   - Verify bot has "Manage Messages" permission
   - Check ADMIN_USER_ID is correct

3. Role pings not working:
   - Ensure TEST_MODE is set to false
   - Verify ROLE_ID is correct
   - Check bot has permission to mention roles

## Contributing

1. Fork the repository
2. Create a new branch for your feature
3. Commit your changes
4. Push to your branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For support:
1. Check the troubleshooting section above
2. Review the configuration in `.env.example`
3. Open an issue in the GitHub repository
