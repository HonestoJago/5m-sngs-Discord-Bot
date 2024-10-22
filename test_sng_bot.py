import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from discord import Interaction, Message, ButtonStyle
from bot import SNGView, sng_games, MAX_PLAYERS, EndSNGButton, client

print("Starting imports...")

# Import each component separately
print("Importing logger...")
from bot import logger
print("logger imported")

print("Importing client...")
from bot import client
print("client imported")

print("Importing tree...")
from bot import tree
print("tree imported")

print("Importing SNGView...")
from bot import SNGView
print("SNGView imported")

print("Importing sng_games...")
from bot import sng_games
print("sng_games imported")

print("Importing MAX_PLAYERS...")
from bot import MAX_PLAYERS
print("MAX_PLAYERS imported")

print("Importing EndSNGButton...")
from bot import EndSNGButton
print("EndSNGButton imported")

print("All imports complete")

# Add these imports at the top of the file
import asyncio
from concurrent.futures import ThreadPoolExecutor

@pytest.fixture(scope="module")
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_interaction():
    interaction = AsyncMock(spec=Interaction)
    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction

@pytest.fixture
def mock_client():
    client = MagicMock()
    client.get_channel = MagicMock(return_value=AsyncMock())
    return client

@pytest.fixture
async def sng_view(mock_interaction, mock_client):
    sng_id = "test_sng_id"
    view = SNGView(sng_id, "TestStarter", mock_interaction.channel_id)
    view.message = AsyncMock(spec=Message)
    view.start_message = AsyncMock(spec=Message)
    view.game_messages = [AsyncMock(spec=Message) for _ in range(3)]
    sng_games[sng_id] = {
        'players': 2,
        'started': True,
        'starter': "TestStarter",
        'display_id': "TEST123"
    }
    yield view
    # Clean up after the test
    if sng_id in sng_games:
        del sng_games[sng_id]

@pytest.mark.asyncio
async def test_manual_end_game(sng_view, mock_interaction):
    # Simulate manual ending of the game
    await sng_view.end_sng(mock_interaction)

    # Check if the game was removed from sng_games
    assert sng_view.sng_id not in sng_games

    # Check if the GUI message was deleted
    assert sng_view.message.delete.called

    # Check if all game messages were deleted
    for msg in sng_view.game_messages:
        assert msg.delete.called

    # Check if a confirmation message was sent
    assert mock_interaction.followup.send.called
    assert "ended" in mock_interaction.followup.send.call_args[0][0]

@pytest.mark.asyncio
async def test_auto_end_game(sng_view, mock_client):
    # Mock the client.get_channel method
    channel = AsyncMock()
    mock_client.get_channel.return_value = channel

    # Simulate auto-ending of the game
    with patch('asyncio.sleep', new_callable=AsyncMock), \
         patch('bot.client', mock_client):
        await sng_view.auto_end_sng()

    # Check if the game was removed from sng_games
    assert sng_view.sng_id not in sng_games

    # Check if the GUI message was deleted
    assert sng_view.message.delete.called

    # Check if all game messages were deleted
    for msg in sng_view.game_messages:
        assert msg.delete.called

    # Check if a confirmation message was sent to the channel
    assert channel.send.called
    assert "automatically ended" in channel.send.call_args[0][0]

@pytest.mark.asyncio
async def test_inactivity_timer(sng_view, mock_client):
    # Set the game as not started
    sng_games[sng_view.sng_id]['started'] = False

    # Mock the client.get_channel method
    channel = AsyncMock()
    mock_client.get_channel.return_value = channel

    # Simulate inactivity timer
    with patch('asyncio.sleep', new_callable=AsyncMock), \
         patch('bot.client', mock_client):
        await sng_view.start_inactivity_timer()

    # Check if the game was removed from sng_games
    assert sng_view.sng_id not in sng_games

    # Check if the GUI message was deleted
    assert sng_view.message.delete.called

    # Check if all game messages were deleted
    for msg in sng_view.game_messages:
        assert msg.delete.called

    # Check if a confirmation message was sent to the channel
    assert channel.send.called
    assert "automatically ended" in channel.send.call_args[0][0]

@pytest.mark.asyncio
async def test_message_deletion_all_scenarios(sng_view, mock_interaction, mock_client):
    # Setup
    channel = AsyncMock()
    mock_client.get_channel.return_value = channel

    scenarios = [
        ("Manual end", sng_view.end_sng, [mock_interaction]),
        ("Auto end", sng_view.auto_end_sng, []),
        ("Inactivity timer", sng_view.end_sng, [None, True]),
    ]

    for scenario_name, end_function, args in scenarios:
        print(f"Testing {scenario_name}")
        
        # Reset mocks and game state
        sng_view.message.delete.reset_mock()
        for msg in sng_view.game_messages:
            msg.delete.reset_mock()
        sng_games[sng_view.sng_id] = {'players': 2, 'started': True, 'starter': "TestStarter", 'display_id': "TEST123"}

        # Run the end game function
        with patch('bot.sng_games', new=sng_games), \
             patch('asyncio.sleep', new_callable=AsyncMock), \
             patch('bot.client', mock_client):
            await end_function(*args)

        # Check if the GUI message was deleted
        assert sng_view.message.delete.called, f"{scenario_name}: GUI message not deleted"

        # Check if all game messages were deleted
        for i, msg in enumerate(sng_view.game_messages):
            assert msg.delete.called, f"{scenario_name}: Game message {i} not deleted"

        # Check if the game was removed from sng_games
        assert sng_view.sng_id not in sng_games, f"{scenario_name}: Game not removed from sng_games"

        # Ensure all deletions happened before game removal
        delete_calls = [sng_view.message.delete.call_count] + [msg.delete.call_count for msg in sng_view.game_messages]
        for call_count in delete_calls:
            assert call_count > 0, f"{scenario_name}: Message deletion not called"

    print("All scenarios tested successfully")

print("Test file updated")
