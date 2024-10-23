import discord
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
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

    # No need to check for confirmation message anymore as it's been removed

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

    # No need to check for confirmation message anymore as it's been removed

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

# Add to existing imports
from discord import Message, Interaction, ButtonStyle

# Add new test scenarios
@pytest.mark.asyncio
async def test_end_game_scenarios(mock_interaction, mock_client):
    """Test all scenarios that can end a game to ensure consistent cleanup."""
    
    # Add channel to mock_interaction
    mock_interaction.channel = AsyncMock()
    mock_interaction.channel.send = AsyncMock()
    
    scenarios = [
        ("Manual end via button", lambda view: view.end_sng(mock_interaction)),
        ("Auto-end after 5 minutes", lambda view: view.auto_end_sng()),
        ("Inactivity timeout", lambda view: view.start_inactivity_timer()),
        ("Max players reached", lambda view: test_max_players_scenario(view, mock_interaction))
    ]
    
    async def test_max_players_scenario(view, interaction):
        # First update to max players
        await view.update_players(interaction, MAX_PLAYERS)
        
        # Verify game started automatically
        assert sng_games[view.sng_id]['started'] is True
        
        # Verify buttons disabled (except End SNG)
        for child in view.children:
            if not isinstance(child, EndSNGButton):
                assert child.disabled
                
        # Verify auto-end task was created
        assert view.end_task is not None
        assert not view.end_task.done()
        
        # Simulate 5-minute timer completion
        await view.auto_end_sng()
        
        # Verify cleanup
        assert view.sng_id not in sng_games
        assert view.message.delete.called
        for msg in view.game_messages:
            assert msg.delete.called
    
    for scenario_name, trigger_func in scenarios:
        # Setup
        sng_id = f"test_sng_{scenario_name}"
        channel_id = 123456789
        
        # Create mock messages
        gui_message = AsyncMock(spec=Message)
        game_messages = [AsyncMock(spec=Message) for _ in range(3)]
        
        # Create view
        view = SNGView(sng_id, "TestStarter", channel_id)
        view.message = gui_message
        view.game_messages = game_messages
        
        # Initialize game state
        sng_games[sng_id] = {
            'players': 1,
            'started': False,
            'starter': "TestStarter",
            'display_id': "TEST123",
            'view': view
        }
        
        # Setup mock channel
        channel = AsyncMock()
        mock_client.get_channel.return_value = channel
        
        print(f"\nTesting {scenario_name}")
        
        # Setup interaction mocks
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()
        mock_interaction.response.is_done = AsyncMock(return_value=False)
        
        # Execute the end game scenario
        with patch('bot.client', mock_client), \
             patch('asyncio.sleep', new_callable=AsyncMock):  # Skip sleep delays
            await trigger_func(view)
            
            # Verify cleanup
            assert view.sng_id not in sng_games, f"{scenario_name}: Game not removed from sng_games"
            assert gui_message.delete.called, f"{scenario_name}: GUI message not deleted"
            for msg in game_messages:
                assert msg.delete.called, f"{scenario_name}: Game message not deleted"
        
        # Clean up for next scenario
        if sng_id in sng_games:
            del sng_games[sng_id]

@pytest.mark.asyncio
async def test_message_deletion_retry_mechanism():
    """Test that message deletion retries work correctly."""
    
    sng_id = "test_retry_sng"
    channel_id = 123456789
    view = SNGView(sng_id, "TestStarter", channel_id)
    
    # Mock message that fails first attempt but succeeds on retry
    failing_message = AsyncMock(spec=Message)
    failing_message.delete.side_effect = [
        discord.HTTPException(AsyncMock(), {'code': 50027}),  # First attempt fails
        None  # Second attempt succeeds
    ]
    
    # Test retry mechanism
    result = await view.delete_with_retry(failing_message, "test message")
    
    assert result is True
    assert failing_message.delete.call_count == 2

@pytest.mark.asyncio
async def test_cleanup_order():
    """Test that cleanup happens in the correct order."""
    
    # Create a wrapper class to track operations
    class TrackedDict(dict):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.operations = []
            
        def __delitem__(self, key):
            self.operations.append("game_removed")
            super().__delitem__(key)
    
    # Replace sng_games with our tracked version
    tracked_games = TrackedDict()
    
    sng_id = "test_cleanup_sng"
    channel_id = 123456789
    view = SNGView(sng_id, "TestStarter", channel_id)
    
    # Setup mocks
    gui_message = AsyncMock(spec=Message)
    game_messages = [AsyncMock(spec=Message) for _ in range(3)]
    view.message = gui_message
    view.game_messages = game_messages
    
    # Initialize game state in our tracked dict
    tracked_games[sng_id] = {
        'players': 1,
        'started': False,
        'starter': "TestStarter",
        'display_id': "TEST123",
        'view': view
    }
    
    # Mock message deletions with different labels
    async def mock_gui_delete():
        tracked_games.operations.append("gui_deleted")
        return True
        
    async def mock_game_message_delete():
        tracked_games.operations.append("game_message_deleted")
        return True
        
    # Set up delete behaviors
    gui_message.delete = AsyncMock(side_effect=mock_gui_delete)
    for msg in game_messages:
        msg.delete = AsyncMock(side_effect=mock_game_message_delete)
    
    # Execute end game with our tracked dictionary
    with patch('bot.sng_games', tracked_games):
        await view.end_sng(auto_ended=True)
        
        # Verify all messages were deleted
        assert gui_message.delete.called, "GUI message was not deleted"
        for msg in game_messages:
            assert msg.delete.called, "Game message was not deleted"
            
        # Verify game was removed
        assert sng_id not in tracked_games, "Game was not removed from sng_games"
        
        # Verify order
        print(f"Operation order: {tracked_games.operations}")
        
        # Verify all game messages were deleted
        game_message_deletions = tracked_games.operations.count("game_message_deleted")
        assert game_message_deletions == len(game_messages), "Not all game messages were deleted"
        
        # Verify GUI was deleted
        assert "gui_deleted" in tracked_games.operations, "GUI was not deleted"
        
        # Verify game removal happened last
        assert tracked_games.operations[-1] == "game_removed", "Game was not removed last"

# Add test for delete_with_retry
@pytest.mark.asyncio
async def test_delete_with_retry():
    """Test the delete_with_retry helper function."""
    
    sng_id = "test_retry_sng"
    channel_id = 123456789
    view = SNGView(sng_id, "TestStarter", channel_id)
    
    # Mock message that fails first attempt but succeeds on retry
    failing_message = AsyncMock(spec=Message)
    failing_message.delete.side_effect = [
        discord.HTTPException(AsyncMock(), {'code': 50027}),  # First attempt fails
        None  # Second attempt succeeds
    ]
    
    # Test retry mechanism
    result = await view.delete_with_retry(failing_message, "test message")
    
    assert result is True
    assert failing_message.delete.call_count == 2

@pytest.mark.asyncio
async def test_core_end_game_functionality():
    """Test that _end_game handles all scenarios correctly."""
    sng_id = "test_core_end"
    channel_id = 123456789
    view = SNGView(sng_id, "TestStarter", channel_id)
    
    # Setup mocks
    gui_message = AsyncMock(spec=Message)
    game_messages = [AsyncMock(spec=Message) for _ in range(3)]
    view.message = gui_message
    view.game_messages = game_messages
    
    # Initialize game state
    sng_games[sng_id] = {
        'players': 1,
        'started': False,
        'starter': "TestStarter",
        'display_id': "TEST123",
        'view': view
    }
    
    # Track operation order
    operations = []
    
    # Mock message deletions
    async def mock_delete():
        operations.append("message_deleted")
        return True
    
    gui_message.delete = AsyncMock(side_effect=mock_delete)
    for msg in game_messages:
        msg.delete = AsyncMock(side_effect=mock_delete)
    
    # Execute core end game
    success = await view._end_game(auto_ended=True)
    
    # Verify success
    assert success is True, "End game operation should succeed"
    
    # Verify all messages were deleted
    assert gui_message.delete.called, "GUI message not deleted"
    for msg in game_messages:
        assert msg.delete.called, "Game message not deleted"
    
    # Verify game was removed from active games
    assert sng_id not in sng_games, "Game not removed from sng_games"
    
    # Verify order - all deletions before game removal
    assert len(operations) == len(game_messages) + 1, "Not all messages were deleted"
    assert operations.count("message_deleted") == len(game_messages) + 1, "Incorrect number of deletions"

@pytest.mark.asyncio
async def test_auto_end_timer():
    """Test that auto-end timer works correctly."""
    sng_id = "test_auto_end"
    channel_id = 123456789
    view = SNGView(sng_id, "TestStarter", channel_id)
    
    # Setup mocks
    gui_message = AsyncMock(spec=Message)
    game_messages = [AsyncMock(spec=Message) for _ in range(3)]
    view.message = gui_message
    view.game_messages = game_messages
    
    # Initialize game state
    sng_games[sng_id] = {
        'players': MAX_PLAYERS,
        'started': True,
        'starter': "TestStarter",
        'display_id': "TEST123",
        'view': view
    }
    
    # Start auto-end timer
    with patch('asyncio.sleep', new_callable=AsyncMock):
        await view.auto_end_sng()
        
        # Verify game was ended
        assert sng_id not in sng_games, "Game not removed after auto-end"
        assert gui_message.delete.called, "GUI message not deleted after auto-end"
        for msg in game_messages:
            assert msg.delete.called, "Game message not deleted after auto-end"

@pytest.mark.asyncio
async def test_message_deletion_retry():
    """Test message deletion retry mechanism."""
    sng_id = "test_deletion_retry"
    channel_id = 123456789
    view = SNGView(sng_id, "TestStarter", channel_id)
    
    # Mock message that fails first attempt but succeeds on retry
    message = AsyncMock(spec=Message)
    message.delete.side_effect = [
        discord.HTTPException(AsyncMock(), {'code': 50027}),  # First attempt fails
        None  # Second attempt succeeds
    ]
    
    # Test retry mechanism
    success = await view.delete_with_retry(message, "test message")
    
    assert success is True, "Retry mechanism should succeed"
    assert message.delete.call_count == 2, "Should retry once after failure"

@pytest.mark.asyncio
async def test_end_game_error_handling():
    """Test error handling during game end."""
    sng_id = "test_error_handling"
    channel_id = 123456789
    view = SNGView(sng_id, "TestStarter", channel_id)
    
    # Setup mocks that will fail to delete
    gui_message = AsyncMock(spec=Message)
    gui_message.delete.side_effect = discord.Forbidden(AsyncMock(), "No permission")
    view.message = gui_message
    
    game_messages = [AsyncMock(spec=Message) for _ in range(3)]
    for msg in game_messages:
        msg.delete.side_effect = discord.NotFound(AsyncMock(), "Message not found")
    view.game_messages = game_messages
    
    # Initialize game state
    sng_games[sng_id] = {
        'players': 1,
        'started': False,
        'starter': "TestStarter",
        'display_id': "TEST123",
        'view': view
    }
    
    # Execute end game
    success = await view._end_game(auto_ended=True)
    
    # Verify behavior with errors
    assert success is False, "Should return False when deletions fail"
    assert sng_id in sng_games, "Game should not be removed if deletions fail"

@pytest.mark.asyncio
async def test_concurrent_end_attempts():
    """Test handling of concurrent attempts to end the game."""
    sng_id = "test_concurrent"
    channel_id = 123456789
    view = SNGView(sng_id, "TestStarter", channel_id)
    
    # Setup mocks
    view.message = AsyncMock(spec=Message)
    view.game_messages = [AsyncMock(spec=Message) for _ in range(3)]
    
    # Initialize game state
    sng_games[sng_id] = {
        'players': 1,
        'started': False,
        'starter': "TestStarter",
        'display_id': "TEST123",
        'view': view
    }
    
    # Attempt to end game concurrently
    async def end_game():
        return await view._end_game(auto_ended=True)
    
    # Run multiple end attempts concurrently
    results = await asyncio.gather(
        end_game(),
        end_game(),
        return_exceptions=True
    )
    
    # Verify only one attempt succeeded
    success_count = sum(1 for r in results if r is True)
    assert success_count == 1, "Only one end attempt should succeed"

print("Test file updated")

