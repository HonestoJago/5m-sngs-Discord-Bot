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

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the root directory using the provided `.env.example` template

5. Run the bot:
   ```bash
   python bot.py
   ```

## Usage

### Commands

- `/start` - Start a new SNG tournament (requires appropriate role)

### Permissions

The bot requires the following Discord permissions:
- Send Messages
- Manage Messages
- Read Message History
- View Channels
- Mention @everyone, @here, and All Roles

## Contributing

1. Fork the repository
2. Create a new branch for your feature
3. Commit your changes
4. Push to your branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For support, please open an issue in the GitHub repository.
