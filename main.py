###Huge thanks to @Idently on youtube for help with the discord bot setup, @Jtk.21 on discord for help with the retreival of fight start times and the offset used for twitch
###and OpenAI for formatting, syntax checking, and help with error checking###

import os
import json
from typing import Final
from dotenv import load_dotenv
from discord import Intents, Client, Message
import aiohttp
import urllib.parse
from datetime import datetime, timezone

load_dotenv()

# Load tokens from .env file
DISCORD_TOKEN: Final[str] = os.getenv("DISCORD_TOKEN")
TWITCH_ACCESS_TOKEN: Final[str] = os.getenv("TWITCH_ACCESS_TOKEN")
TWITCH_CLIENT_ID: Final[str] = os.getenv("TWITCH_CLIENT_ID")
TWITCH_USERNAME: Final[str] = os.getenv("TWITCH_USERNAME")
WCL_TOKEN: Final[str] = os.getenv("LOGS_TOKEN")

# Load configuration from config.json
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

# Load values from config.json
TARGET_CHANNEL_ID: Final[int] = int(config["TARGET_CHANNEL_ID"])
GUILD_NAME: Final[str] = config["GUILD_NAME"]
SERVER_NAME: Final[str] = config["SERVER_NAME"]
SERVER_REGION: Final[str] = config["SERVER_REGION"]
COMMAND_PREFIX: Final[str] = config["COMMAND_PREFIX"]

# Bot setup
intents: Intents = Intents.default()
intents.message_content = True
client: Client = Client(intents=intents)

# Helper function to format timestamps from milliseconds
def format_timestamp(milliseconds: int) -> str:
    seconds = milliseconds / 1000
    return datetime.fromtimestamp(seconds, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

# Helper function to get Twitch user ID
async def get_twitch_user_id() -> str:
    url = f"https://api.twitch.tv/helix/users?login={TWITCH_USERNAME}"
    headers = {
        "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}",
        "Client-Id": TWITCH_CLIENT_ID
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            data = await response.json()
            if 'data' in data and len(data['data']) > 0:
                return data['data'][0]['id']
            return None

# Helper function to get most recent Twitch broadcast
async def get_recent_broadcast(user_id: str):
    url = f"https://api.twitch.tv/helix/videos?user_id={user_id}&first=1&type=archive"
    headers = {
        "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}",
        "Client-Id": TWITCH_CLIENT_ID
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            data = await response.json()
            if 'data' in data and len(data['data']) > 0:
                return data['data'][0]
            return None

# Messaging
async def get_recent_boss_pull() -> str:
    guild_name = urllib.parse.quote(GUILD_NAME)
    server_name = urllib.parse.quote(SERVER_NAME)
    server_region = SERVER_REGION
    api_key = WCL_TOKEN
    
    # Get the most recent report
    api_url = f"https://www.warcraftlogs.com:443/v1/reports/guild/{guild_name}/{server_name}/{server_region}?api_key={api_key}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        most_recent_report = max(data, key=lambda r: r['end'])
                        report_id = most_recent_report['id']
                        report_start_time = most_recent_report['start']
                        
                        # Get specific pulls (fights) within that report
                        report_fights_url = f"https://www.warcraftlogs.com:443/v1/report/fights/{report_id}?api_key={api_key}"
                        async with session.get(report_fights_url) as fights_response:
                            if fights_response.status == 200:
                                fights_data = await fights_response.json()
                                if 'fights' in fights_data and fights_data['fights']:
                                    last_fight = fights_data['fights'][-1]
                                    pull_number = last_fight['id']
                                    pull_start_offset = last_fight['start_time']
                                    pull_url = f"https://www.warcraftlogs.com/reports/{report_id}#fight={pull_number}"
                                    
                                    # Calculate the actual start time of the pull
                                    actual_pull_start_time = report_start_time + pull_start_offset
                                    formatted_start_time = format_timestamp(actual_pull_start_time)
                                    
                                    # Get the Twitch user ID
                                    user_id = await get_twitch_user_id()
                                    if not user_id:
                                        return f"Latest pull: {pull_url}\nStart Time (UTC): {formatted_start_time}\nTwitch user ID not found."
                                    
                                    # Get the most recent broadcast
                                    broadcast = await get_recent_broadcast(user_id)
                                    if not broadcast:
                                        return f"Latest pull: {pull_url}\nStart Time (UTC): {formatted_start_time}\nNo recent Twitch broadcast found."
                                    
                                    # Calculate the timestamp offset in the broadcast
                                    broadcast_start_time = datetime.strptime(broadcast['created_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp() * 1000
                                    timestamp_offset = int((actual_pull_start_time - broadcast_start_time) / 1000)
                                    twitch_url = f"{broadcast['url']}?t={timestamp_offset}s"
                                    
                                    return f"Latest pull: {pull_url}\nTwitch URL: {twitch_url}"
                                else:
                                    return "No pulls found in the most recent report."
                            else:
                                return f"Error fetching fights: {fights_response.status} {await fights_response.text()}"
                    else:
                        return "No report data found."
                else:
                    return f"Error fetching data: {response.status} {await response.text()}"
    except aiohttp.ClientError as e:
        return f"API request failed: {str(e)}"

# Handle startup
@client.event
async def on_ready() -> None:
    print(f"{client.user} is now running!")

# Handle messages in a specific channel
@client.event
async def on_message(message: Message) -> None:
    if message.author == client.user:
        return

    if message.channel.id != TARGET_CHANNEL_ID:
        return

    username: str = str(message.author)
    user_message: str = message.content
    channel: str = str(message.channel)

    print(f"[{channel}] {username}: '{user_message}'")

    if user_message.startswith(COMMAND_PREFIX):
        api_response = await get_recent_boss_pull()

        print(f"API Response: {api_response}")

        if len(api_response) > 4000:
            api_response = api_response[:4000]

        await message.channel.send(api_response)

# Entry point
def main() -> None:
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
