import os
from dotenv import load_dotenv
import discord
from discord import ButtonStyle
import asyncio
from discord import app_commands
import uuid
import logging
from typing import Optional
from discord.ext import commands

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Change this to DEBUG for more detailed logs
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s',
    handlers=[
        logging.FileHandler(filename='bot.log', encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Set up intents
intents = discord.Intents.default()
intents.members = True  # Enable members intent for role checks
intents.message_content = True  # Enable message content intent

# Add these new constants
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))  # Your user ID
PIN_BOT_ID = int(os.getenv('PIN_BOT_ID'))  # Your pin bot's ID

# Modify the client initialization
class CustomClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

client = CustomClient(intents=intents)
tree = client.tree

MAX_PLAYERS = 8
sng_games = {}

# Get designated channels from environment variable
designated_channels_env = os.getenv('DESIGNATED_CHANNELS')
if not designated_channels_env:
    raise ValueError("DESIGNATED_CHANNELS environment variable is not set.")
DESIGNATED_CHANNELS = list(map(int, designated_channels_env.split(',')))

TEST_MODE = os.getenv('TEST_MODE', 'false').lower() == 'true'

# Define the role name as a constant or from environment variable
ROLE_NAME = os.getenv('ROLE_NAME', '5m-sngs')

# Add this constant near the top of your file, with other constants
ROLE_ID = 1295098347551592518

def in_designated_channel():
    async def predicate(interaction: discord.Interaction):
        return interaction.channel_id in DESIGNATED_CHANNELS
    return app_commands.check(predicate)

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
            logger.error(f"Unexpected error in PlayerButton callback for SNG {self.sng_id}, slot {self.slot}: {e}", exc_info=True)

class StartSNGButton(discord.ui.Button):
    def __init__(self, sng_id):
        super().__init__(label="Start SNG", style=ButtonStyle.blurple, custom_id=f"start_sng_{sng_id}")

    async def callback(self, interaction: discord.Interaction):
        logger.info(f"StartSNGButton clicked by {interaction.user} for SNG {self.view.sng_id}")
        try:
            await self.view.start_sng(interaction)
        except Exception as e:
            await interaction.response.send_message("An unexpected error occurred while starting the SNG.", ephemeral=True)
            logger.error(f"Unexpected error in StartSNGButton callback for SNG {self.view.sng_id}: {e}", exc_info=True)

class EndSNGButton(discord.ui.Button):
    def __init__(self, sng_id):
        super().__init__(label="End SNG", style=ButtonStyle.red, custom_id=f"end_sng_{sng_id}")

    async def callback(self, interaction: discord.Interaction):
        logger.info(f"EndSNGButton clicked by {interaction.user} for SNG {self.view.sng_id}")
        try:
            await self.view.end_sng(interaction)
        except Exception as e:
            # Since we have deferred the interaction in end_sng, we cannot send a new response here
            logger.error(f"Unexpected error in EndSNGButton callback for SNG {self.view.sng_id}: {e}", exc_info=True)

class NotifyMeButton(discord.ui.Button):
    def __init__(self, sng_id):
        super().__init__(label="Notify Me", style=ButtonStyle.blurple, custom_id=f"notify_me_{sng_id}")

    async def callback(self, interaction: discord.Interaction):
        logger.info(f"NotifyMeButton clicked by {interaction.user} for SNG {self.view.sng_id}")
        try:
            await self.view.toggle_notification(interaction)
        except Exception as e:
            await interaction.response.send_message("An unexpected error occurred while setting up notification.", ephemeral=True)
            logger.error(f"Unexpected error in NotifyMeButton callback for SNG {self.view.sng_id}: {e}", exc_info=True)

class SNGView(discord.ui.View):
    def __init__(self, sng_id, starter, channel_id):
        super().__init__(timeout=None)  # No timeout to keep the view alive
        self.sng_id = sng_id
        self.starter = starter
        self.channel_id = channel_id
        self.message = None
        self.message_id = None
        self.start_message = None  # This will store the "Preparing to start SNG" message
        self.notify_users = set()  # Set to store users who want notifications
        self.last_activity = discord.utils.utcnow()
        self.end_task = None  # Task to automatically end the SNG after it starts
        self.inactivity_task = None  # Task to automatically end unstarted SNG after 1 hour

        for i in range(1, MAX_PLAYERS + 1):
            button = PlayerButton(sng_id, i)
            if i == 1:
                button.style = ButtonStyle.green
            self.add_item(button)

        self.add_item(StartSNGButton(sng_id))
        self.add_item(EndSNGButton(sng_id))
        self.add_item(NotifyMeButton(sng_id))

        # Start the inactivity timer for unstarted SNGs
        self.inactivity_task = asyncio.create_task(self.start_inactivity_timer())

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
            if not sng_games[self.sng_id]['started']:
                await interaction.response.defer()

                sng_games[self.sng_id]['players'] = slot

                for button in self.children:
                    if isinstance(button, PlayerButton):
                        button.style = ButtonStyle.green if button.slot <= slot else ButtonStyle.grey

                if sng_games[self.sng_id]['players'] == MAX_PLAYERS:
                    sng_games[self.sng_id]['started'] = True
                    # Disable all buttons except End SNG
                    for child in self.children:
                        if not isinstance(child, EndSNGButton):
                            child.disabled = True

                    await self.message.edit(view=self, embed=self.create_embed())

                    self.start_message = await interaction.followup.send(
                        f"SNG {sng_games[self.sng_id]['display_id']} has automatically started with {MAX_PLAYERS} players!"
                    )

                    logger.info(f"TEST_MODE is set to: {TEST_MODE}")

                    # Notify users who requested notifications
                    await self.send_notifications(client, sng_games[self.sng_id]['display_id'])

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
            if game['players'] > 1 and not game['started']:
                game['started'] = True

                # Disable all buttons except End SNG
                for child in self.children:
                    if not isinstance(child, EndSNGButton):
                        child.disabled = True

                await self.message.edit(view=self, embed=self.create_embed())

                self.start_message = await interaction.followup.send(
                    f"SNG {game['display_id']} has been manually started with {game['players']} players!"
                )

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
        logger.info(f"Ending SNG {self.sng_id}")
        self.last_activity = discord.utils.utcnow()
        if interaction and interaction.channel_id != self.channel_id:
            return
        try:
            if interaction:
                try:
                    await interaction.response.defer(ephemeral=True)
                except Exception as e:
                    logger.error(f"Failed to defer interaction: {e}", exc_info=True)
            else:
                logger.info("No interaction provided; proceeding without deferring.")

            if self.sng_id in sng_games:
                game = sng_games[self.sng_id]

                # Cancel tasks
                if not auto_ended:
                    if self.end_task and not self.end_task.done():
                        self.end_task.cancel()
                        logger.info(f"Auto-end task cancelled for SNG {self.sng_id}")
                    if self.inactivity_task and not self.inactivity_task.done():
                        self.inactivity_task.cancel()
                        logger.info(f"Inactivity timer cancelled for SNG {self.sng_id}")

                # Remove the reference to the view
                del sng_games[self.sng_id]
                logger.info(f"SNG {self.sng_id} removed from active games.")

                # Delete the GUI message
                if self.message:
                    try:
                        logger.info(f"Attempting to delete GUI message for SNG {self.sng_id}")
                        await self.message.delete()
                        logger.info(f"GUI message deleted for SNG {self.sng_id}")
                    except discord.errors.NotFound:
                        logger.warning(f"GUI message for SNG {self.sng_id} already deleted or not found")
                    except Exception as e:
                        logger.error(f"Failed to delete GUI message: {e}", exc_info=True)

                # Delete any other bot messages related to this SNG
                if self.channel_id:
                    channel = client.get_channel(self.channel_id)
                    if channel:
                        async for message in channel.history(limit=100):
                            if message.author == client.user and (self.sng_id in message.content or game['display_id'] in message.content):
                                try:
                                    await message.delete()
                                    logger.info(f"Deleted related message for SNG {self.sng_id}")
                                except Exception as e:
                                    logger.error(f"Failed to delete related message: {e}", exc_info=True)

                # Send confirmation message only if not auto-ended
                if not auto_ended:
                    try:
                        if interaction:
                            await interaction.followup.send(f"SNG {game['display_id']} has been ended.", ephemeral=True)
                        else:
                            channel = client.get_channel(self.channel_id)
                            if channel:
                                await channel.send(f"SNG {game['display_id']} has been ended.", delete_after=10)
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
                if interaction:
                    try:
                        await interaction.followup.send("This SNG has already been ended.", ephemeral=True)
                    except Exception as e:
                        logger.error(f"Failed to send follow-up message: {e}", exc_info=True)
                else:
                    logger.info(f"SNG {self.sng_id} has already been ended.")
        except Exception as e:
            logger.error(f"Error in end_sng: {e}", exc_info=True)

    async def ping_channel(self, interaction: discord.Interaction):
        temp_message = await interaction.channel.send("Updating SNG status...")
        await temp_message.delete()

    async def auto_end_sng(self):
        logger.info(f"Auto-end task started for SNG {self.sng_id}")
        try:
            await asyncio.sleep(300)  # 5 minutes before ending
            logger.info(f"Auto-end task waking up to end SNG {self.sng_id}")
            await self.end_sng(auto_ended=True)
        except asyncio.CancelledError:
            # Task was cancelled
            logger.info(f"Auto-end task cancelled for SNG {self.sng_id}")
            pass
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
            # Task was cancelled
            logger.info(f"Inactivity timer cancelled for SNG {self.sng_id}")
            pass
        except Exception as e:
            logger.error(f"Error in start_inactivity_timer: {e}", exc_info=True)

    async def toggle_notification(self, interaction: discord.Interaction):
        logger.info(f"Toggling notification for user {interaction.user.id} on SNG {self.sng_id}")
        self.last_activity = discord.utils.utcnow()
        try:
            user_id = interaction.user.id
            if user_id in self.notify_users:
                self.notify_users.remove(user_id)
                await interaction.response.send_message("You will no longer be notified when this game starts.", ephemeral=True)
            else:
                self.notify_users.add(user_id)
                await interaction.response.send_message("You will be notified when this game starts.", ephemeral=True)

            logger.info(f"User {user_id} toggled notifications for game {self.sng_id}. Current notify list: {self.notify_users}")

            # Update the embed to reflect the new notification count
            await self.message.edit(embed=self.create_embed(), view=self)
        except Exception as e:
            await interaction.response.send_message("An error occurred while toggling notifications.", ephemeral=True)
            logger.error(f"Error in toggle_notification: {e}", exc_info=True)

    async def send_notifications(self, client, game_id):
        for user_id in self.notify_users:
            try:
                user = await client.fetch_user(user_id)
                await user.send(f"The SNG game {game_id} has started!")
                logger.info(f"Notification sent to user {user.id} for game {game_id}")
            except discord.HTTPException as e:
                logger.warning(f"Failed to send DM to user {user_id}. Error: {e}")
            except Exception as e:
                logger.error(f"Error while trying to notify user {user_id}: {e}", exc_info=True)

@tree.command(name="start", description="Start a new 5M Sit-and-Go game")
@app_commands.checks.has_any_role(ROLE_NAME)
@in_designated_channel()
async def start_sng(interaction: discord.Interaction):
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

    # Defer the response
    await interaction.response.defer()

    if TEST_MODE:
        view.message = await interaction.followup.send("Test mode: Role mention skipped", embed=embed, view=view)
    else:
        role = interaction.guild.get_role(ROLE_ID)
        if role:
            view.message = await interaction.followup.send(f"{role.mention}", embed=embed, view=view)
        else:
            view.message = await interaction.followup.send(f"Role with ID {ROLE_ID} not found.", embed=embed, view=view)

    view.message_id = view.message.id if view.message else None

    # Register the view to keep it alive
    client.add_view(view)

    # Log the TEST_MODE status
    logger.info(f"TEST_MODE is set to: {TEST_MODE}")

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

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingAnyRole):
        await interaction.response.send_message("You don't have the required role to use this command.", ephemeral=True)
    elif isinstance(error, app_commands.errors.CheckFailure):
        await interaction.response.send_message("This command can only be used in designated channels.", ephemeral=True)
    else:
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
    logger.error(f"An error occurred: {error}", exc_info=True)

# Add this new event handler
@client.event
async def on_message(message):
    if message.channel.id in DESIGNATED_CHANNELS:
        # Allow messages from the admin (you), the pin bot, and this bot itself
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

# Get the bot token from the environment variable
bot_token = os.getenv('DISCORD_BOT_TOKEN')
if not bot_token:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is not set.")

# Add this near the end of your file, just before client.run(bot_token)
logger.info("Starting bot...")

client.run(bot_token)
