
async def send_long_message(channel, content):
    for chunk in [content[i:i + 2000] for i in range(0, len(content), 2000)]:
        await channel.send(chunk)
