import discord
import random
from discord.ext import commands
import asyncio

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.reactions = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

sessions = {}
prompts = [
    "A mysterious figure in a cloak enters the town.",
    "In a world where magic is common, a rare child born without it.",
    "An ancient map leads to an unexpected treasure.",
    "A time traveler gets stuck in the wrong era.",
    "A scientist discovers a hidden world within our own.",
    "A group of strangers must work together to survive a mysterious island.",
    "A hero is framed for a crime they didn't commit.",
    "A haunted house with a tragic history draws new residents.",
    "A young orphan discovers they have extraordinary powers.",
    "A detective must solve a crime that defies all logic.",
]

PUBLISHED_STORIES_CHANNEL_ID = 1233241928745877615

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    # Send a test message to the bot-commands channel
    channel = discord.utils.get(bot.get_all_channels(), name='bot-commands')
    if channel:
        await channel.send("Bot is now online and ready to go!")
    else:
        print("bot-commands channel not found. Please create one.")

@bot.event
async def on_command_error(ctx, error):
    print(f"Error: {error}")

@bot.command(name='test')
async def test_command(ctx):
    print("test_command triggered")
    await ctx.send("Test command received!")

@bot.command(name='start_session')
async def start_session(ctx, num_people: int, *mentions: discord.Member):
    print(f"start_session called by {ctx.author} with {num_people} participants.")
    await ctx.send(f"start_session called by {ctx.author} with {num_people} participants.")

    if num_people < 1:
        await ctx.send("Please provide a valid number of participants.")
        return

    initiator = ctx.author
    participants = [initiator] + list(mentions)

    if len(participants) > num_people:
        await ctx.send(f"Too many participants mentioned. Maximum required: {num_people}.")
        return

    message = await ctx.send(
        f"{ctx.author.mention} wants to start a collaborative writing session! "
        f"React to this message to join. We need {num_people} participants."
    )
    print(f"Session initiation message sent: {message.id}")

    def check(reaction, user):
        print(f"Reaction received: {reaction.emoji} by {user}")
        return str(reaction.emoji) == '✋' and user != bot.user and user not in participants

    await message.add_reaction('✋')
    print("Waiting for reactions...")

    while len(participants) < num_people:
        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=3600.0, check=check)
            participants.append(user)
            await ctx.send(f"{user.mention} has joined the session. {len(participants)}/{num_people} participants.")
            print(f"{user} has joined the session. Participants: {participants}")
        except asyncio.TimeoutError:
            await ctx.send("Session start timed out. Not enough participants.")
            print("Session start timed out. Not enough participants.")
            return

    await message.clear_reactions()

    # Create a new text channel for the writing session
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        bot.user: discord.PermissionOverwrite(read_messages=True)
    }
    for participant in participants:
        overwrites[participant] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    session_channel = await ctx.guild.create_text_channel(f'writing-session-{ctx.author.name}', overwrites=overwrites)
    sessions[session_channel.id] = {
        'participants': participants,
        'contributions': [],
        'turn_order': participants.copy(),  # Initialize turn_order with participants
        'prompt': None,
        'current_writer': None,
        'initiator': initiator
    }
    print(f"New channel created: {session_channel.name}")

    # Ask for prompt generation method
    prompt_message = await session_channel.send(
        f"{initiator.mention}, choose a prompt generation method:\n"
        "1️⃣ Random Prompt\n"
        "2️⃣ Create Your Own"
    )
    await prompt_message.add_reaction('1️⃣')
    await prompt_message.add_reaction('2️⃣')
    print("Prompt generation method message sent.")

    def prompt_check(reaction, user):
        return user == initiator and reaction.message.id == prompt_message.id and str(reaction.emoji) in ['1️⃣', '2️⃣']

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=600.0, check=prompt_check)
        if str(reaction.emoji) == '1️⃣':
            # Random Prompt
            selected_prompt = random.choice(prompts)
            sessions[session_channel.id]['prompt'] = selected_prompt
            await session_channel.send(f"Random Prompt Selected: {selected_prompt}")
        elif str(reaction.emoji) == '2️⃣':
            await session_channel.send("Great, share it in the channel!")
            def custom_prompt_check(m):
                return m.author == initiator and m.channel == session_channel

            custom_prompt = await bot.wait_for('message', check=custom_prompt_check)
            sessions[session_channel.id]['prompt'] = custom_prompt.content
    except asyncio.TimeoutError:
        await session_channel.send("Prompt selection timed out.")
        print("Prompt selection timed out.")
        return

    await start_writing(session_channel)

async def start_writing(channel):
    session = sessions[channel.id]
    random.shuffle(session['turn_order'])
    await select_writer(channel)

async def select_writer(channel):
    session = sessions[channel.id]
    if not session['turn_order']:
        await channel.send("The story is complete!")
        await finalize_story(channel)
        return

    writer = session['turn_order'].pop(0)
    session['current_writer'] = writer

    await channel.set_permissions(writer, read_messages=True, send_messages=True)
    for participant in session['participants']:
        if participant != writer:
            await channel.set_permissions(participant, read_messages=False, send_messages=False)

    # Show only the original prompt and the previous submission
    instructions = session['prompt']
    if session['contributions']:
        instructions += "\n" + session['contributions'][-1]

    await channel.send(f"{writer.mention}, it's your turn to contribute to the story! Here is the prompt:\n{instructions}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)

    channel_id = message.channel.id
    if channel_id in sessions:
        session = sessions[channel_id]
        if message.author == session['current_writer']:
            session['contributions'].append(message.content)

            await message.channel.set_permissions(message.author, read_messages=False, send_messages=False)
            await message.channel.purge(limit=100)

            await select_writer(message.channel)

async def finalize_story(channel):
    session = sessions[channel.id]
    final_story = session['prompt'] + "\n" + "\n".join(session['contributions'])

    # Invite everyone back into the channel
    for participant in session['participants']:
        await channel.set_permissions(participant, read_messages=True, send_messages=True)

    await channel.send("Here's the final story:\n" + final_story)
    await channel.send(f"This channel will be deleted in 12 hours. {session['initiator'].mention}, you can share the story by using the command `!share` within this channel. To delete the channel immediately, use `!delete`.")

    # Clean up the session after 12 hours
    await asyncio.sleep(43200)
    await channel.delete()
    del sessions[channel.id]

    print(f"Finalized story and updated permissions for all participants in channel: {channel.name}")

@bot.command(name='share')
async def share_story(ctx):
    channel_id = ctx.channel.id
    if channel_id in sessions:
        session = sessions[channel_id]
        if ctx.author == session['initiator']:
            final_story = session['prompt'] + "\n" + "\n".join(session['contributions'])
            published_channel = bot.get_channel(PUBLISHED_STORIES_CHANNEL_ID)
            if published_channel:
                await published_channel.send(f"Story from {ctx.channel.name}:\n{final_story}")
                await ctx.send("The story has been shared to #published-stories!")
            else:
                await ctx.send("Published-stories channel not found. Please create one.")
        else:
            await ctx.send("Only the session initiator can share the story.")
    else:
        await ctx.send("This command can only be used in an active writing session channel.")

@bot.command(name='delete')
async def delete_channel(ctx):
    channel_id = ctx.channel.id
    if channel_id in sessions:
        session = sessions[channel_id]
        if ctx.author == session['initiator']:
            await ctx.channel.delete()
            del sessions[channel_id]
        else:
            await ctx.send("Only the session initiator can delete the channel.")
    else:
        await ctx.send("This command can only be used in an active writing session channel.")

bot.run('Secret Token [hidden]')