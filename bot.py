import os
import uuid
import asyncio
import logging
from typing import Optional, List

import discord
from discord import ButtonStyle, app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s',
    handlers=[
        logging.FileHandler(filename='bot.log', encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Debug logging for environment setup
logger.info("Starting bot initialization...")
logger.info(f"Current working directory: {os.getcwd()}")
logger.info(f".env file exists: {os.path.exists('.env')}")

# Read and set environment variables directly
env_vars = {}
try:
    with open('.env', 'r') as f:
        env_contents = f.read()
        logger.info(f"ENV file contents:\n{env_contents}")
        
        # Parse each line
        for line in env_contents.splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
                os.environ[key.strip()] = value.strip()
                logger.info(f"Set environment variable {key.strip()} = {value.strip()}")
except Exception as e:
    logger.error(f"Error reading .env: {e}")

# Then proceed with the rest of the initialization

def parse_bool(value):
    """Parse string to bool with explicit logging"""
    logger.info(f"parse_bool received value: '{value}' (type: {type(value)})")
    
    if isinstance(value, bool):
        logger.info(f"Value is already bool: {value}")
        return value
        
    if isinstance(value, str):
        # Strip any whitespace and convert to lowercase
        cleaned_value = value.strip().lower()
        logger.info(f"Cleaned string value: '{cleaned_value}'")
        
        # Check for various true values
        is_true = cleaned_value in ('true', 't', 'yes', 'y', '1', 'on')
        logger.info(f"String '{cleaned_value}' evaluates to: {is_true}")
        return is_true
        
    logger.info(f"Defaulting non-string/non-bool value to False")
    return False

# Helper function to retrieve and validate environment variables
def get_env_variable(var_name: str, cast_type, default=None):
    value = os.getenv(var_name, default)
    logger.info(f"Reading environment variable {var_name}: '{value}' (type: {type(value)})")
    if value is None:
        logger.error(f"Environment variable '{var_name}' is not set.")
        raise ValueError(f"Environment variable '{var_name}' is not set.")
    try:
        result = cast_type(value)
        logger.info(f"Converted {var_name} value '{value}' to: {result}")
        return result
    except ValueError:
        logger.error(f"Environment variable '{var_name}' must be of type {cast_type.__name__}.")
        raise ValueError(f"Environment variable '{var_name}' must be of type {cast_type.__name__}.")

# Retrieve and validate environment variables
DISCORD_BOT_TOKEN = get_env_variable('DISCORD_BOT_TOKEN', str)
DESIGNATED_CHANNELS = get_env_variable('DESIGNATED_CHANNELS', lambda x: list(map(int, x.split(','))))
TEST_MODE = get_env_variable('TEST_MODE', parse_bool, default=False)
logger.info(f"Raw env value for TEST_MODE: '{os.getenv('TEST_MODE')}'")
logger.info(f"Final TEST_MODE value: {TEST_MODE} (type: {type(TEST_MODE)})")
ADMIN_USER_ID = get_env_variable('ADMIN_USER_ID', int)
PIN_BOT_ID = get_env_variable('PIN_BOT_ID', int)
ROLE_ID = get_env_variable('ROLE_ID', int)

# Set up intents
intents = discord.Intents.default()
intents.members = True  # Required for role checks
intents.message_content = True  # Required to read message content

# First define the button classes
class PlayerButton(discord.ui.Button):
    def __init__(self, sng_id, slot):
        super().__init__(style=ButtonStyle.grey, label=f"Player {slot}", custom_id=f"player_{sng_id}_{slot}")
        self.sng_id = sng_id
        self.slot = slot

    async def callback(self, interaction: discord.Interaction):
        logger.info(f"PlayerButton clicked by {interaction.user} for SNG {self.view.sng_id}, slot {self.slot}")
        try:
            await self.view.update_players(interaction, self.slot)
        except Exception as e:
            await interaction.response.send_message(
                "An unexpected error occurred while updating players.",
                ephemeral=True
            )
            logger.error(f"Error in PlayerButton callback: {e}", exc_info=True)

class StartSNGButton(discord.ui.Button):
    def __init__(self, sng_id):
        super().__init__(label="Start SNG", style=ButtonStyle.blurple, custom_id=f"start_sng_{sng_id}")

    async def callback(self, interaction: discord.Interaction):
        logger.info(f"StartSNGButton clicked by {interaction.user} for SNG {self.view.sng_id}")
        try:
            await self.view.start_sng(interaction)
        except Exception as e:
            await interaction.response.send_message(
                "An unexpected error occurred while starting the SNG.",
                ephemeral=True
            )
            logger.error(f"Error in StartSNGButton callback: {e}", exc_info=True)

class EndSNGButton(discord.ui.Button):
    def __init__(self, sng_id):
        super().__init__(label="End SNG", style=ButtonStyle.red, custom_id=f"end_sng_{sng_id}")

    async def callback(self, interaction: discord.Interaction):
        logger.info(f"EndSNGButton clicked by {interaction.user} for SNG {self.view.sng_id}")
        try:
            await self.view.end_sng(interaction)
        except Exception as e:
            logger.error(f"Error in EndSNGButton callback: {e}", exc_info=True)

class NotifyMeButton(discord.ui.Button):
    def __init__(self, sng_id):
        super().__init__(label="Notify Me", style=ButtonStyle.blurple, custom_id=f"notify_me_{sng_id}")

    async def callback(self, interaction: discord.Interaction):
        logger.info(f"NotifyMeButton clicked by {interaction.user} for SNG {self.view.sng_id}")
        try:
            await self.view.toggle_notification(interaction)
        except Exception as e:
            await interaction.response.send_message(
                "An error occurred while toggling notifications.",
                ephemeral=True
            )
            logger.error(f"Error in NotifyMeButton callback: {e}", exc_info=True)

# Then define the SNGView class
class SNGView(discord.ui.View):
    def __init__(self, sng_id, starter, channel_id):
        # Set timeout to None for persistence
        super().__init__(timeout=None)
        self.sng_id = sng_id
        self.starter = starter
        self.channel_id = channel_id
        self.message: Optional[discord.Message] = None
        self.ping_message_id: Optional[int] = None
        self.start_message: Optional[discord.Message] = None
        self.notify_users = set()
        self.last_activity = discord.utils.utcnow()
        self.end_task: Optional[asyncio.Task] = None
        self.game_messages = []
        
        # Start inactivity timer
        self.inactivity_task = asyncio.create_task(self.start_inactivity_timer())

        # Add Player Buttons with custom_ids
        for i in range(1, MAX_PLAYERS + 1):
            button = PlayerButton(sng_id, i)
            button.custom_id = f"player_{sng_id}_{i}"
            if i == 1:
                button.style = ButtonStyle.green
            self.add_item(button)

        # Add Control Buttons with custom_ids
        start_button = StartSNGButton(sng_id)
        start_button.custom_id = f"start_sng_{sng_id}"
        self.add_item(start_button)
        
        end_button = EndSNGButton(sng_id)
        end_button.custom_id = f"end_sng_{sng_id}"
        self.add_item(end_button)
        
        notify_button = NotifyMeButton(sng_id)
        notify_button.custom_id = f"notify_me_{sng_id}"
        self.add_item(notify_button)

    def create_embed(self):
        if self.sng_id in sng_games:
            game = sng_games[self.sng_id]
            embed = discord.Embed(title=f"5M Sit-and-Go Status (ID: {game['display_id']})", color=discord.Color.blue())
            embed.add_field(name="Players", value=f"{game['players']}/{MAX_PLAYERS}", inline=True)
            embed.add_field(name="Status", value="In Progress" if game['started'] else "Not Started", inline=True)
            embed.add_field(name="Notifications", value=f"{len(self.notify_users)} user(s)", inline=True)
            embed.set_footer(text=f"Started by {self.starter}")
            logger.info(f"Created embed for game {game['display_id']}. Notify users: {self.notify_users}")
        else:
            embed = discord.Embed(title="5M Sit-and-Go Ended", color=discord.Color.red())
            embed.add_field(name="Status", value="This SNG has ended or timed out", inline=False)
            logger.info(f"Created 'ended' embed for game {self.sng_id}")
        return embed

    async def update_players(self, interaction: discord.Interaction, slot: int):
        """Update the number of players in the game."""
        logger.info(f"Updating players for SNG {self.sng_id}")
        self.last_activity = discord.utils.utcnow()
        
        try:
            await interaction.response.defer()
            
            if self.sng_id not in sng_games:
                await interaction.followup.send(
                    "This game has already ended. Please start a new game.", 
                    ephemeral=True
                )
                return

            game = sng_games[self.sng_id]
            if game['started']:
                await interaction.followup.send(
                    "Cannot modify players after SNG has started.",
                    ephemeral=True
                )
                return

            game['players'] = slot

            # Update button styles
            for child in self.children:
                if isinstance(child, PlayerButton):
                    child.style = ButtonStyle.green if child.slot <= slot else ButtonStyle.grey

            # Update GUI message
            await self.message.edit(embed=self.create_embed(), view=self)
            await self.ping_channel(interaction)

            # Handle max players case
            if game['players'] == MAX_PLAYERS:
                game['started'] = True
                for child in self.children:
                    if not isinstance(child, EndSNGButton):
                        child.disabled = True

                await self.message.edit(view=self, embed=self.create_embed())

                self.start_message = await interaction.followup.send(
                    f"SNG {game['display_id']} has automatically started with {MAX_PLAYERS} players!"
                )
                self.game_messages.append(self.start_message)

                logger.info(f"TEST_MODE is set to: {TEST_MODE}")
                await self.send_notifications(client, game['display_id'])

                if self.inactivity_task and not self.inactivity_task.done():
                    self.inactivity_task.cancel()
                    logger.info(f"Inactivity timer cancelled for SNG {self.sng_id}")

                if self.end_task and not self.end_task.done():
                    self.end_task.cancel()
                self.end_task = asyncio.create_task(self.auto_end_sng())
                logger.info(f"Auto-end task started for SNG {self.sng_id}")

        except Exception as e:
            logger.error(f"Error in update_players: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "An error occurred while updating the game. Please try ending this game and starting a new one.", 
                    ephemeral=True
                )
            except:
                pass

    async def start_sng(self, interaction: discord.Interaction):
        logger.info(f"Starting SNG {self.sng_id}")
        self.last_activity = discord.utils.utcnow()
        if interaction.channel_id != self.channel_id:
            return
        try:
            await interaction.response.defer()
            game = sng_games[self.sng_id]
            if game['players'] >= 2 and not game['started']:
                game['started'] = True
                
                # Disable all buttons except End SNG
                for child in self.children:
                    if not isinstance(child, EndSNGButton):
                        child.disabled = True

                if self.message:
                    await self.message.edit(view=self, embed=self.create_embed())
                else:
                    logger.warning(f"self.message is None for SNG {self.sng_id}")

                # Send start message and track it
                self.start_message = await interaction.followup.send(
                    f"SNG {game['display_id']} has been manually started with {game['players']} players!"
                )
                self.game_messages.append(self.start_message)

                logger.info(f"TEST_MODE is set to: {TEST_MODE}")

                # Notify users who requested notifications
                await self.send_notifications(client, game['display_id'])

                # Start auto-end task
                if self.end_task and not self.end_task.done():
                    self.end_task.cancel()
                self.end_task = asyncio.create_task(self.auto_end_sng())

                # Cancel the inactivity timer as the game has started
                if self.inactivity_task and not self.inactivity_task.done():
                    self.inactivity_task.cancel()
                    logger.info(f"Inactivity timer cancelled for SNG {self.sng_id}")
            else:
                await interaction.followup.send("Cannot start SNG. Make sure there are at least 2 players.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
            logger.error(f"Error in start_sng: {e}", exc_info=True)

    async def _end_game(self, auto_ended: bool = False, interaction: Optional[discord.Interaction] = None) -> bool:
        """Core game ending logic used by all end-game scenarios."""
        logger.info(f"Ending SNG {self.sng_id} (auto_ended: {auto_ended})")
        
        # First, check if the game exists
        game_info = sng_games.get(self.sng_id)
        if not game_info:
            logger.warning(f"Attempted to end SNG {self.sng_id}, but it was not found in active games.")
            if interaction:
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message("This game has already ended.", ephemeral=True)
                except discord.NotFound:
                    logger.info(f"Interaction expired while ending game {self.sng_id}")
                except Exception as e:
                    logger.error(f"Error responding to end game interaction: {e}")
            return False

        # Delete messages and clean up
        try:
            deletion_successful = await self._cleanup_messages()
            if deletion_successful:
                await self._cleanup_game_state(game_info, interaction)
                return True
            return False
        except Exception as e:
            logger.error(f"Error during game cleanup: {e}", exc_info=True)
            return False

    async def _cleanup_messages(self) -> bool:
        """Handle message deletion with proper logging."""
        deletion_successful = True
        
        for msg in self.game_messages:
            if not await self.delete_with_retry(msg, "game message"):
                deletion_successful = False
                
        if not await self.delete_with_retry(self.message, "GUI message"):
            deletion_successful = False
            
        return deletion_successful

    async def _cleanup_game_state(self, game_info: dict, interaction: Optional[discord.Interaction]):
        """Clean up game state and handle interaction response."""
        del sng_games[self.sng_id]
        logger.info(f"SNG {self.sng_id} removed from active games")
        
        # Cancel tasks - should include refresh_task
        for task in [self.end_task, self.inactivity_task]:  # Changed
            if task and not task.done():
                task.cancel()
                
        # Handle interaction response
        if interaction:
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)
                await interaction.followup.send(
                    f"SNG {game_info['display_id']} has been ended.",
                    ephemeral=True
                )
            except discord.NotFound:
                logger.info(f"Interaction expired during cleanup for {self.sng_id}")
            except Exception as e:
                logger.error(f"Error sending cleanup confirmation: {e}")

    async def end_sng(self, interaction: Optional[discord.Interaction] = None, auto_ended: bool = False):
        """End game via manual button press or other direct call."""
        logger.info(f"Ending SNG {self.sng_id}")
        
        # Remove the view from storage
        client.remove_view(self.sng_id)
        
        # Cancel inactivity task
        if self.inactivity_task and not self.inactivity_task.done():
            self.inactivity_task.cancel()
            logger.info(f"Inactivity task cancelled for SNG {self.sng_id}")
        
        # Cancel end task if it exists
        if self.end_task and not self.end_task.done():
            self.end_task.cancel()
                
        # Delete messages with better error handling
        messages_to_delete = set(self.game_messages)  # Use set to avoid duplicates
        if self.message:
            messages_to_delete.add(self.message)
            
        for msg in messages_to_delete:
            try:
                await msg.delete()
            except discord.NotFound:
                logger.info(f"Message already deleted for SNG {self.sng_id}")
            except discord.HTTPException as e:
                if e.code == 50027:  # Invalid Webhook Token
                    try:
                        channel = client.get_channel(self.channel_id)
                        if channel:
                            try:
                                message = await channel.fetch_message(msg.id)
                                await message.delete()
                            except discord.NotFound:
                                pass
                            except Exception as e:
                                logger.error(f"Failed to delete through channel: {e}")
                    except Exception as e:
                        logger.error(f"Failed to get channel: {e}")
                else:
                    logger.error(f"Error deleting message: {e}")
                
        # Clear message lists
        self.game_messages.clear()
        self.message = None
        
        # Remove from active games
        if self.sng_id in sng_games:
            del sng_games[self.sng_id]
            logger.info(f"SNG {self.sng_id} removed from active games")
            
        # Send confirmation if interaction exists
        if interaction:
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)
                await interaction.followup.send(
                    f"SNG has been ended.",
                    ephemeral=True
                )
            except discord.NotFound:
                logger.info(f"Interaction expired during cleanup for {self.sng_id}")

    async def auto_end_sng(self):
        """Auto-end the SNG after timer expires."""
        logger.info(f"Auto-end task started for SNG {self.sng_id}")
        try:
            await asyncio.sleep(180)  # Wait for 3 minutes
            logger.info(f"Auto-end task waking up to end SNG {self.sng_id}")
            if self.sng_id in sng_games:
                await self._end_game(auto_ended=True)
        except asyncio.CancelledError:
            logger.info(f"Auto-end task cancelled for SNG {self.sng_id}")
        except Exception as e:
            logger.error(f"Error in auto_end_sng: {e}", exc_info=True)

    async def ping_channel(self, interaction: discord.Interaction):
        """Send and delete a message to show channel activity."""
        try:
            temp_message = await interaction.channel.send("Updating SNG status...")
            self.game_messages.append(temp_message)
            await temp_message.delete()
            logger.info("Sent and deleted temporary status message to show activity")
        except Exception as e:
            logger.error(f"Failed to send activity indicator message: {e}", exc_info=True)

    async def start_inactivity_timer(self):
        logger.info(f"Inactivity timer started for SNG {self.sng_id}")
        try:
            await asyncio.sleep(3600)  # Wait for 1 hour
            logger.info(f"Inactivity timer expired for SNG {self.sng_id}")
            if self.sng_id in sng_games and not sng_games[self.sng_id]['started']:
                await self.end_sng(auto_ended=True)
        except asyncio.CancelledError:
            logger.info(f"Inactivity timer cancelled for SNG {self.sng_id}")
        except Exception as e:
            logger.error(f"Error in start_inactivity_timer: {e}", exc_info=True)

    async def toggle_notification(self, interaction: discord.Interaction):
        logger.info(f"Toggling notification for user {interaction.user.id} on SNG {self.sng_id}")
        self.last_activity = discord.utils.utcnow()
        try:
            user_id = interaction.user.id
            if user_id in self.notify_users:
                self.notify_users.remove(user_id)
                await interaction.response.send_message("You will no longer be notified when this game is created.", ephemeral=True)
                logger.info(f"User {user_id} removed from notification list for SNG {self.sng_id}")
            else:
                self.notify_users.add(user_id)
                await interaction.response.send_message("You will be notified when this game is created.", ephemeral=True)
                logger.info(f"User {user_id} added to notification list for SNG {self.sng_id}")

            # Update the embed to reflect the new notification count
            await self.message.edit(embed=self.create_embed(), view=self)
        except Exception as e:
            await interaction.response.send_message("An error occurred while toggling notifications.", ephemeral=True)
            logger.error(f"Error in toggle_notification: {e}", exc_info=True)

    async def send_notifications(self, client, game_id):
        for user_id in self.notify_users:
            try:
                user = await client.fetch_user(user_id)
                await user.send(f"The SNG game {game_id} has been created!")
                logger.info(f"Notification sent to user {user.id} for game {game_id}")
            except discord.HTTPException as e:
                logger.warning(f"Failed to send DM to user {user_id}. Error: {e}")
            except Exception as e:
                logger.error(f"Error while trying to notify user {user_id}: {e}", exc_info=True)

    async def safe_delete_message(self, message: Optional[discord.Message], context: str = "message") -> bool:
        """Safely delete a message with error handling."""
        if message is None:
            return False
        
        try:
            await message.delete()
            logger.info(f"Successfully deleted {context} for SNG {self.sng_id}")
            return True
        except discord.NotFound:
            logger.info(f"{context.capitalize()} already deleted for SNG {self.sng_id}")
            return True
        except discord.Forbidden:
            logger.warning(f"Missing permissions to delete {context} for SNG {self.sng_id}")
            return False
        except Exception as e:
            logger.error(f"Error deleting {context} for SNG {self.sng_id}: {e}", exc_info=True)
            return False

    async def delete_with_retry(self, message, context: str, max_retries: int = 3):
        """Delete a message with retry mechanism."""
        for attempt in range(max_retries):
            try:
                if message:
                    await message.delete()
                    logger.info(f"Successfully deleted {context} for SNG {self.sng_id} (attempt {attempt + 1})")
                    return True
            except discord.NotFound:
                logger.info(f"{context} already deleted for SNG {self.sng_id}")
                return True
            except discord.Forbidden as e:
                logger.warning(f"Missing permissions to delete {context} for SNG {self.sng_id}: {e}")
                return False
            except discord.HTTPException as e:
                if e.code == 50027:  # Invalid Webhook Token
                    logger.warning(f"Invalid webhook token for {context}, attempting channel fetch")
                    try:
                        channel = client.get_channel(self.channel_id)
                        if channel:
                            message = await channel.fetch_message(message.id)
                            await message.delete()
                            return True
                    except Exception as channel_e:
                        logger.error(f"Failed to delete through channel: {channel_e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
            except Exception as e:
                logger.error(f"Error deleting {context} for SNG {self.sng_id}: {e}", exc_info=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
        return False

# Finally define the CustomClient class that uses SNGView
class CustomClient(discord.Client):
    """Enhanced Discord client with better connection handling"""
    def __init__(self):
        # Improved connection settings
        super().__init__(
            intents=intents,
            heartbeat_timeout=150.0,
            guild_ready_timeout=10.0,
            gateway_queue_size=512
        )
        self.tree = app_commands.CommandTree(self)
        self.disconnect_count = 0
        self.active_views = {}  # Store active views

    async def setup_hook(self):
        # Restore active views on startup
        for sng_id, game in sng_games.items():
            if not game['started']:
                view = SNGView(sng_id, game['starter'], game.get('channel_id'))
                self.add_view(view)
                self.active_views[sng_id] = view
                logger.info(f"Restored view for game {sng_id}")
        await self.tree.sync()

    def store_view(self, sng_id: str, view: SNGView):
        """Store a view for persistence"""
        self.active_views[sng_id] = view
        self.add_view(view)
        logger.info(f"Stored view for game {sng_id}")

    def remove_view(self, sng_id: str):
        """Remove a stored view"""
        if sng_id in self.active_views:
            del self.active_views[sng_id]
            logger.info(f"Removed view for game {sng_id}")

# Then create the client instance
client = CustomClient()
tree = client.tree

# Constants
MAX_PLAYERS = 8
sng_games = {}

# Check to ensure commands are used in designated channels
def in_designated_channel():
    async def predicate(interaction: discord.Interaction):
        return interaction.channel_id in DESIGNATED_CHANNELS
    return app_commands.check(predicate)

# Slash Command to Start SNG
@tree.command(name="start", description="Start a new 5M Sit-and-Go game")
@app_commands.checks.has_any_role(ROLE_ID)  # Using ROLE_ID for role checks
@in_designated_channel()
async def start_sng(interaction: discord.Interaction):
    logger.info(f"Starting new SNG with TEST_MODE = {TEST_MODE}")
    logger.info(f"TEST_MODE type at command start: {type(TEST_MODE)}")
    logger.info(f"Raw TEST_MODE env value at command start: {os.getenv('TEST_MODE')}")
    
    if not interaction.guild:
        await interaction.response.send_message("This command can only be used within a server.", ephemeral=True)
        return

    sng_id = str(uuid.uuid4())
    display_id = sng_id[:8]
    starter = interaction.user.name
    sng_games[sng_id] = {
        'players': 1,
        'started': False,
        'starter': starter,
        'display_id': display_id
    }

    embed = discord.Embed(title=f"5M Sit-and-Go Status (ID: {display_id})", color=discord.Color.blue())
    embed.add_field(name="Players", value=f"1/{MAX_PLAYERS}", inline=True)
    embed.add_field(name="Status", value="Not Started", inline=True)
    embed.set_footer(text=f"Started by {starter}")

    view = SNGView(sng_id, starter, interaction.channel_id)
    sng_games[sng_id]['view'] = view
    sng_games[sng_id]['channel_id'] = interaction.channel_id  # Store channel ID
    await interaction.response.defer()

    # Make the test mode check more explicit
    is_test = bool(TEST_MODE)  # Force boolean conversion
    logger.info(f"Is test mode (after bool conversion): {is_test}")

    if is_test:
        logger.info("TEST_MODE is True - skipping role ping")
        test_message = await interaction.followup.send("Test mode: Role mention skipped")
        view.game_messages.append(test_message)
    else:
        logger.info("TEST_MODE is False - sending role ping")
        role = interaction.guild.get_role(ROLE_ID)
        if role:
            allowed_mentions = discord.AllowedMentions(roles=[role])
            try:
                ping_content = f"{role.mention} A new 5M SNG game has been created!"
                logger.info(f"Sending ping message: {ping_content}")
                
                ping_message = await interaction.channel.send(
                    ping_content,
                    allowed_mentions=allowed_mentions
                )
                logger.info(f"Ping message sent for role {role.name} (ID: {role.id})")
                view.game_messages.append(ping_message)
            except Exception as e:
                logger.error(f"Failed to send ping message: {e}", exc_info=True)
                await interaction.followup.send("Failed to ping role. Starting game anyway.", ephemeral=True)
        else:
            logger.error(f"Role with ID {ROLE_ID} not found.")
            await interaction.followup.send(
                "Error: The specified role does not exist. Please contact an administrator.",
                ephemeral=True
            )

    # Send the GUI embed and track it
    gui_message = await interaction.followup.send(embed=embed, view=view)
    view.message = gui_message
    view.game_messages.append(gui_message)

    # Store the view for persistence
    client.store_view(sng_id, view)

    # Log relevant information
    logger.info(f"TEST_MODE is set to: {TEST_MODE}")
    logger.info(f"SNG started with ID: {sng_id}, Display ID: {display_id}")
    logger.info(f"Starter: {starter}, Channel ID: {interaction.channel_id}")

# **New Test Command to Ping the Role**
'''
Test ping function commented out after confirming role pinging works correctly in main functionality.
Uncomment if further testing is needed in the future.

@tree.command(name="test_ping", description="Test pinging the @5m-sngs role")
@app_commands.checks.has_any_role(ROLE_ID)  # Restricting to roles that can ping
@in_designated_channel()
async def test_ping(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("This command can only be used within a server.", ephemeral=True)
        return

    role = interaction.guild.get_role(ROLE_ID)
    if role:
        allowed_mentions = discord.AllowedMentions(roles=[role])  # Correct: Passing Role object
        try:
            ping_content = f"{role.mention} This is a test ping!"
            logger.info(f"Sending test ping message: {ping_content}")
            await interaction.response.send_message(
                ping_content,
                allowed_mentions=allowed_mentions
            )
            # Retrieve the sent message to delete it after a delay
            message = await interaction.original_response()
            logger.info(f"Test ping message sent for role {role.name} (ID: {role.id})")
            await message.delete(delay=5)  # Delete the test message after 5 seconds
        except discord.Forbidden:
            logger.error(f"Permission denied: Cannot mention role ID {ROLE_ID}.")
            await interaction.followup.send("Error: I don't have permission to mention the role.", ephemeral=True)
        except discord.HTTPException as e:
            logger.error(f"HTTP error occurred while sending test ping: {e}")
            await interaction.followup.send("Error: Failed to send the test role mention due to an internal error.", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send test ping message: {e}", exc_info=True)
            await interaction.followup.send("Failed to ping role.", ephemeral=True)
    else:
        logger.error(f"Role with ID {ROLE_ID} not found.")
        await interaction.response.send_message(
            "Error: The specified role does not exist. Please contact an administrator.",
            ephemeral=True
        )
'''

# Event Handlers
@client.event
async def on_ready():
    logger.info(f'{client.user} has connected to Discord!')
    try:
        synced = await tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}", exc_info=True)

@client.event
async def on_disconnect():
    client.disconnect_count += 1
    logger.warning(
        f"\nDisconnection #{client.disconnect_count}"
        f"\nTime: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
        f"\nActive Games: {len(sng_games)}"
    )
    # Log details of active games
    for game_id, game in sng_games.items():
        logger.warning(
            f"- Game {game['display_id']}: "
            f"{game['players']} players, "
            f"{'Started' if game['started'] else 'Not Started'}, "
            f"Started by {game['starter']}"
        )

@client.event
async def on_resume():
    logger.info(
        f"\nConnection Resumed"
        f"\nTime: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
        f"\nChecking {len(sng_games)} active games..."
    )

# Error Handler for Slash Commands
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingAnyRole):
        await interaction.response.send_message("You don't have the required role to use this command.", ephemeral=True)
    elif isinstance(error, app_commands.errors.CheckFailure):
        await interaction.response.send_message("This command can only be used in designated channels.", ephemeral=True)
    else:
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
    logger.error(f"An error occurred: {error}", exc_info=True)

# Message Event to Delete Unauthorized Messages
@client.event
async def on_message(message):
    if message.channel.id in DESIGNATED_CHANNELS:
        # Allow messages from the admin, pin bot, and this bot itself
        if message.author.id in [ADMIN_USER_ID, PIN_BOT_ID, client.user.id]:
            return

        # Allow slash commands
        if message.content.startswith('/'):
            return

        # Delete all other messages
        try:
            await message.delete()
            logger.info(f"Deleted message from {message.author} in channel {message.channel.name}")
        except discord.errors.Forbidden:
            logger.warning(f"Bot doesn't have permission to delete message from {message.author} in channel {message.channel.name}")
        except Exception as e:
            logger.error(f"Error deleting message: {e}", exc_info=True)

# Start the Bot
if __name__ == '__main__':
    logger.info("Starting bot...")
    client.run(DISCORD_BOT_TOKEN)
else:
    logger.info("Bot module imported, not starting client.")
