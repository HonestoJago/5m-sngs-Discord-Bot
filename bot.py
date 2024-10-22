import os
import uuid
import asyncio
import logging
from typing import Optional

import discord
from discord import ButtonStyle, app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG for detailed logs during development
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s',
    handlers=[
        logging.FileHandler(filename='bot.log', encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Helper function to retrieve and validate environment variables
def get_env_variable(var_name: str, cast_type, default=None):
    value = os.getenv(var_name, default)
    if value is None:
        logger.error(f"Environment variable '{var_name}' is not set.")
        raise ValueError(f"Environment variable '{var_name}' is not set.")
    try:
        return cast_type(value)
    except ValueError:
        logger.error(f"Environment variable '{var_name}' must be of type {cast_type.__name__}.")
        raise ValueError(f"Environment variable '{var_name}' must be of type {cast_type.__name__}.")

# Retrieve and validate environment variables
DISCORD_BOT_TOKEN = get_env_variable('DISCORD_BOT_TOKEN', str)
DESIGNATED_CHANNELS = get_env_variable('DESIGNATED_CHANNELS', lambda x: list(map(int, x.split(','))))
TEST_MODE = get_env_variable('TEST_MODE', lambda x: x.lower() == 'true', default=False)
ADMIN_USER_ID = get_env_variable('ADMIN_USER_ID', int)
PIN_BOT_ID = get_env_variable('PIN_BOT_ID', int)
ROLE_ID = get_env_variable('ROLE_ID', int)

# Set up intents
intents = discord.Intents.default()
intents.members = True  # Required for role checks
intents.message_content = True  # Required to read message content

# Custom Client with Command Tree
class CustomClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

client = CustomClient(intents=intents)
tree = client.tree

# Constants
MAX_PLAYERS = 8
sng_games = {}

# Check to ensure commands are used in designated channels
def in_designated_channel():
    async def predicate(interaction: discord.Interaction):
        return interaction.channel_id in DESIGNATED_CHANNELS
    return app_commands.check(predicate)

# UI Button Classes
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
            await interaction.response.send_message("An unexpected error occurred while updating players.", ephemeral=True)
            logger.error(f"Error in PlayerButton callback for SNG {self.sng_id}, slot {self.slot}: {e}", exc_info=True)

class StartSNGButton(discord.ui.Button):
    def __init__(self, sng_id):
        super().__init__(label="Start SNG", style=ButtonStyle.blurple, custom_id=f"start_sng_{sng_id}")

    async def callback(self, interaction: discord.Interaction):
        logger.info(f"StartSNGButton clicked by {interaction.user} for SNG {self.view.sng_id}")
        try:
            await self.view.start_sng(interaction)
        except Exception as e:
            await interaction.response.send_message("An unexpected error occurred while starting the SNG.", ephemeral=True)
            logger.error(f"Error in StartSNGButton callback for SNG {self.view.sng_id}: {e}", exc_info=True)

class EndSNGButton(discord.ui.Button):
    def __init__(self, sng_id):
        super().__init__(label="End SNG", style=ButtonStyle.red, custom_id=f"end_sng_{sng_id}")

    async def callback(self, interaction: discord.Interaction):
        logger.info(f"EndSNGButton clicked by {interaction.user} for SNG {self.view.sng_id}")
        try:
            await self.view.end_sng(interaction)
        except Exception as e:
            logger.error(f"Error in EndSNGButton callback for SNG {self.view.sng_id}: {e}", exc_info=True)

class NotifyMeButton(discord.ui.Button):
    def __init__(self, sng_id):
        super().__init__(label="Notify Me", style=ButtonStyle.blurple, custom_id=f"notify_me_{sng_id}")

    async def callback(self, interaction: discord.Interaction):
        logger.info(f"NotifyMeButton clicked by {interaction.user} for SNG {self.view.sng_id}")
        try:
            await self.view.toggle_notification(interaction)
        except Exception as e:
            await interaction.response.send_message("An unexpected error occurred while setting up notification.", ephemeral=True)
            logger.error(f"Error in NotifyMeButton callback for SNG {self.view.sng_id}: {e}", exc_info=True)

# SNG View Class
class SNGView(discord.ui.View):
    def __init__(self, sng_id, starter, channel_id):
        super().__init__(timeout=None)  # No timeout to keep the view alive
        self.sng_id = sng_id
        self.starter = starter
        self.channel_id = channel_id
        self.message: Optional[discord.Message] = None  # GUI message
        self.ping_message_id: Optional[int] = None  # Ping message
        self.start_message: Optional[discord.Message] = None  # Start message
        self.notify_users = set()
        self.last_activity = discord.utils.utcnow()
        self.end_task: Optional[asyncio.Task] = None
        self.inactivity_task = asyncio.create_task(self.start_inactivity_timer())
        self.game_messages = []  # List to track all game-related messages

        # Add Player Buttons
        for i in range(1, MAX_PLAYERS + 1):
            button = PlayerButton(sng_id, i)
            if i == 1:
                button.style = ButtonStyle.green
            self.add_item(button)

        # Add Control Buttons
        self.add_item(StartSNGButton(sng_id))
        self.add_item(EndSNGButton(sng_id))
        self.add_item(NotifyMeButton(sng_id))

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
        logger.info(f"Updating players for SNG {self.sng_id}")
        self.last_activity = discord.utils.utcnow()
        try:
            game = sng_games[self.sng_id]
            if not game['started']:
                await interaction.response.defer()

                game['players'] = slot

                # Update button styles
                for child in self.children:
                    if isinstance(child, PlayerButton):
                        child.style = ButtonStyle.green if child.slot <= slot else ButtonStyle.grey

                if game['players'] == MAX_PLAYERS:
                    game['started'] = True
                    # Disable all buttons except End SNG
                    for child in self.children:
                        if not isinstance(child, EndSNGButton):
                            child.disabled = True

                    await self.message.edit(view=self, embed=self.create_embed())

                    # Send start message and track it
                    self.start_message = await interaction.followup.send(
                        f"SNG {game['display_id']} has automatically started with {MAX_PLAYERS} players!"
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
                    await self.message.edit(view=self, embed=self.create_embed())

                await self.ping_channel(interaction)
            else:
                await interaction.response.send_message("Cannot modify players after SNG has started.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
            logger.error(f"Error in update_players: {e}", exc_info=True)

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

    async def end_sng(self, interaction: Optional[discord.Interaction] = None, auto_ended: bool = False):
        logger.info(f"Ending SNG {self.sng_id} (auto_ended: {auto_ended})")
        self.last_activity = discord.utils.utcnow()
        
        if interaction and interaction.channel_id != self.channel_id:
            return

        try:
            if interaction:
                # Check if the interaction response is already deferred
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)
            
            game = sng_games.get(self.sng_id)
            if game:
                # Cancel tasks
                if self.end_task and not self.end_task.done():
                    self.end_task.cancel()
                    logger.info(f"Auto-end task cancelled for SNG {self.sng_id}")
                if self.inactivity_task and not self.inactivity_task.done():
                    self.inactivity_task.cancel()
                    logger.info(f"Inactivity timer cancelled for SNG {self.sng_id}")
                
                # Delete all tracked game-related messages
                for msg in self.game_messages:
                    try:
                        await msg.delete()
                        logger.info(f"Deleted message ID {msg.id} related to SNG {self.sng_id}")
                    except Exception as e:
                        logger.error(f"Failed to delete message ID {msg.id} for SNG {self.sng_id}: {e}", exc_info=True)
                
                # Delete the GUI message
                if self.message:
                    try:
                        await self.message.delete()
                        logger.info(f"Deleted GUI message for SNG {self.sng_id}")
                    except Exception as e:
                        logger.error(f"Failed to delete GUI message for SNG {self.sng_id}: {e}", exc_info=True)
                else:
                    logger.warning(f"No GUI message to delete for SNG {self.sng_id}")
                
                # Remove the game from active games
                del sng_games[self.sng_id]
                logger.info(f"SNG {self.sng_id} removed from active games.")
                
                # Send confirmation message
                end_message = f"SNG {game['display_id']} has been {'automatically ' if auto_ended else ''}ended."
                try:
                    if interaction:
                        await interaction.followup.send(end_message, ephemeral=True)
                    else:
                        channel = client.get_channel(self.channel_id)
                        if channel:
                            await channel.send(end_message, delete_after=10)
                        else:
                            logger.error(f"Channel is None; cannot send confirmation message for SNG {self.sng_id}")
                except Exception as e:
                    logger.error(f"Failed to send confirmation message: {e}", exc_info=True)
                
                # Log the end of the game
                if interaction and interaction.user:
                    logger.info(f"SNG {game['display_id']} ended by {interaction.user.name}#{interaction.user.discriminator}")
                else:
                    logger.info(f"SNG {game['display_id']} was automatically ended.")
            else:
                logger.warning(f"Attempted to end SNG {self.sng_id}, but it was not found in active games.")
                if interaction:
                    await interaction.followup.send("This SNG has already been ended.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in end_sng: {e}", exc_info=True)
        
        # Ensure the game is removed even if an exception occurs
        if self.sng_id in sng_games:
            del sng_games[self.sng_id]
            logger.info(f"SNG {self.sng_id} forcibly removed from active games after error.")

    async def ping_channel(self, interaction: discord.Interaction):
        try:
            temp_message = await interaction.channel.send("Updating SNG status...")
            self.game_messages.append(temp_message)
            await temp_message.delete()
            logger.info("Temporary 'Updating SNG status...' message deleted.")
        except Exception as e:
            logger.error(f"Failed to ping channel: {e}", exc_info=True)

    async def auto_end_sng(self):
        logger.info(f"Auto-end task started for SNG {self.sng_id}")
        try:
            await asyncio.sleep(300)  # 5 minutes before ending
            logger.info(f"Auto-end task waking up to end SNG {self.sng_id}")
            if self.sng_id in sng_games:
                await self.end_sng(auto_ended=True)
            else:
                logger.info(f"SNG {self.sng_id} already ended before auto-end timer expired.")
        except asyncio.CancelledError:
            logger.info(f"Auto-end task cancelled for SNG {self.sng_id}")
        except Exception as e:
            logger.error(f"Error in auto_end_sng: {e}", exc_info=True)

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

# Slash Command to Start SNG
@tree.command(name="start", description="Start a new 5M Sit-and-Go game")
@app_commands.checks.has_any_role(ROLE_ID)  # Using ROLE_ID for role checks
@in_designated_channel()
async def start_sng(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("This command can only be used within a server.", ephemeral=True)
        return

    sng_id = str(uuid.uuid4())
    display_id = sng_id[:8]  # Use the first 8 characters of the UUID as the display ID
    starter = interaction.user.name
    sng_games[sng_id] = {
        'players': 1,
        'started': False,
        'starter': starter,
        'display_id': display_id
    }  # Start with 1 player

    embed = discord.Embed(title=f"5M Sit-and-Go Status (ID: {display_id})", color=discord.Color.blue())
    embed.add_field(name="Players", value=f"1/{MAX_PLAYERS}", inline=True)  # Start with 1 player
    embed.add_field(name="Status", value="Not Started", inline=True)
    embed.set_footer(text=f"Started by {starter}")

    view = SNGView(sng_id, starter, interaction.channel_id)

    # Store the view in sng_games to prevent garbage collection
    sng_games[sng_id]['view'] = view

    # Defer the response to allow time for processing
    await interaction.response.defer()

    if TEST_MODE:
        test_message = await interaction.followup.send("Test mode: Role mention skipped")
        view.game_messages.append(test_message)
    else:
        role = interaction.guild.get_role(ROLE_ID)
        if role:
            allowed_mentions = discord.AllowedMentions(roles=[role])
            try:
                logger.debug(f"Attempting to mention role {role.name} with ID {ROLE_ID}")
                ping_content = f"{role.mention} A new 5M SNG game has been created!"
                logger.info(f"Sending ping message: {ping_content}")
                
                # Send the ping message separately
                ping_message = await interaction.channel.send(
                    ping_content,
                    allowed_mentions=allowed_mentions
                )
                logger.info(f"Ping message sent for role {role.name} (ID: {role.id})")
                view.game_messages.append(ping_message)
            except discord.Forbidden:
                logger.error(f"Permission denied: Cannot mention role ID {ROLE_ID}.")
                await interaction.followup.send("Error: I don't have permission to mention the role. Starting game anyway.", ephemeral=True)
            except discord.HTTPException as e:
                logger.error(f"HTTP error occurred while sending ping: {e}")
                await interaction.followup.send("Error: Failed to send the role mention due to an internal error. Starting game anyway.", ephemeral=True)
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

    # Register the view to keep it alive
    client.add_view(view)

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
    logger.warning("Bot has disconnected from Discord.")

@client.event
async def on_resume():
    logger.info("Bot has successfully reconnected to Discord.")

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
