import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.utils import get
from discord import ui
import os
import config
import asyncio
import sqlite3
from datetime import datetime, timedelta
import time
import sys
import signal
import requests

intents = discord.Intents.all()
bot = commands.AutoShardedBot(command_prefix='?', intents=intents)

def get_welcome_connection():
    conn = sqlite3.connect('storage/welcome.sqlite')
    return conn

def get_jr_connection():
    conn = sqlite3.connect('storage/joinroles.sqlite')
    return conn

def get_reaction_connection():
    conn = sqlite3.connect('storage/reaction_roles.sqlite')
    return conn

from datetime import datetime
import sqlite3

def is_premium(user_id: str):
    conn = sqlite3.connect('storage/premium_users.sqlite')
    cursor = conn.cursor()

    # Fetch the premium expiry date for the given user_id
    cursor.execute('SELECT premium_expiry_date FROM premium_users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        expiry_date_str = result[0]  # This is the premium expiry date as a string
        try:
            # Convert the string to a datetime object including microseconds
            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d %H:%M:%S.%f')

            # Check if the current time is before the expiry date
            if expiry_date > datetime.now():
                return True
        except ValueError as e:
            print(f"Error parsing date: {e}")
    
    return False



@bot.event
async def on_ready():
    print('Logged in as', bot.user.name)
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

    num_of_servers = str(len(bot.guilds))    

    botactivity = discord.Activity(type=discord.ActivityType.watching, name=f"{num_of_servers} servers!")
    await bot.change_presence(activity=botactivity, status=discord.Status.online)
    await send_heartbeat()

async def send_heartbeat():
    while True:
        try:
            requests.get(config.BETTERSTACK_API)
        except Exception as e:
            print(f"Error sending heartbeat: {e}")
        
        await asyncio.sleep(30)

@bot.event
async def on_guild_join(guild):
    num_of_servers = str(len(bot.guilds))    

    botactivity = discord.Activity(type=discord.ActivityType.watching, name=f"{num_of_servers} servers!")
    await bot.change_presence(activity=botactivity, status=discord.Status.online)

@bot.event
async def on_guild_remove(guild):
    num_of_servers = str(len(bot.guilds))    

    botactivity = discord.Activity(type=discord.ActivityType.watching, name=f"{num_of_servers} servers!")
    await bot.change_presence(activity=botactivity, status=discord.Status.online)

@bot.event
async def on_member_join(member: discord.Member):
    guild_id = member.guild.id
    conn = get_welcome_connection()
    conn2 = get_jr_connection()
    
    cursor = conn.cursor()
    cursor2 = conn2.cursor()

    cursor.execute('SELECT message FROM welcome_messages WHERE guild_id = ?', (guild_id,))
    cursor2.execute('SELECT role_id FROM join_roles WHERE guild_id = ?', (guild_id,))
    result = cursor.fetchone()
    result2 = cursor2.fetchone()

    conn.close()
    conn2.close()

    if result:
        welcome_message = result[0].replace('[user]', member.mention)
        await member.guild.system_channel.send(content=welcome_message)
    else:
        print(f'No welcome message set for guild {member.guild.name}!')

    if result2:
        role = member.guild.get_role(result2[0])
        await member.add_roles(role)
    else:
        print(f'No welcome role set for guild {member.guild.name}!')

@bot.event
async def on_raw_reaction_add(payload):
    if payload.guild_id is None:
        return

    conn = get_reaction_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT role_id FROM reaction_roles WHERE message_id = ? AND emoji = ?', (payload.message_id, str(payload.emoji)))
    result = cursor.fetchone()
    
    if result:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(result[0])
        member = guild.get_member(payload.user_id)

        if role and member:
            await member.add_roles(role)

    conn.close()

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.guild_id is None:
        return

    conn = get_reaction_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT role_id FROM reaction_roles WHERE message_id = ? AND emoji = ?', (payload.message_id, str(payload.emoji)))
    result = cursor.fetchone()

    if result:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(result[0])
        member = guild.get_member(payload.user_id)

        if role and member:
            await member.remove_roles(role)

    conn.close()

@bot.event
async def on_raw_message_delete(payload):
    message_id = payload.message_id

    conn = get_reaction_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM reaction_roles WHERE message_id = ?', (message_id,))
    changes = conn.total_changes
    conn.commit()

    if changes > 0:
        print(f"Removed {changes} reaction role(s) for deleted message {message_id}.")
    conn.close()

class EmbedCreationModal(ui.Modal, title="Create an Embed"):
    e_author = ui.TextInput(label="Embed Author", style=discord.TextStyle.short, placeholder="uhAlexz", required=False)
    e_title = ui.TextInput(label="Embed Title", style=discord.TextStyle.short, placeholder="A title", required=True)
    e_description = ui.TextInput(label="Embed Description", style=discord.TextStyle.paragraph, placeholder="Write your embed description here.", required=True)
    e_footer = ui.TextInput(label="Embed Footer", style=discord.TextStyle.short, placeholder="Sigma Bot", required=False)
    cid = ui.TextInput(label="Channel ID", style=discord.TextStyle.short, placeholder="1234567890145", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel = bot.get_channel(int(self.cid.value))
            if channel is None:
                await interaction.response.send_message("Invalid Channel ID.", ephemeral=True)
                return

            embed = discord.Embed(
                title=self.e_title.value,
                description=self.e_description.value,
                color=discord.Color.blue()
            )
            
            if self.e_author.value:
                embed.set_author(name=self.e_author.value)
            if self.e_footer.value:
                embed.set_footer(text=self.e_footer.value)
            
            await channel.send(embed=embed)
            await interaction.response.send_message(f"Sent embed to channel: `{channel.name}`!", ephemeral=True)

        except ValueError:
            await interaction.response.send_message("Invalid Channel ID format. Please enter a valid number.", ephemeral=True)

@bot.tree.command(name="embed", description="Send an embed")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
async def embed(interaction: discord.Interaction):

    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
        return
    
    await interaction.response.send_modal(EmbedCreationModal())

@bot.tree.command(name="set_welcome", description="Set the welcome message!")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
async def set_welcome(interaction: discord.Interaction, message: str):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
        return

    if '[user]' not in message:
        await interaction.response.send_message('The welcome message must include `[user]` to mention the member that joins!', ephemeral=True)
    
    guild_id = interaction.guild_id
    conn = get_welcome_connection()
    cursor = conn.cursor()

    cursor.execute('''
    INSERT INTO welcome_messages (guild_id, message)
    VALUES (?, ?)
    ON CONFLICT(guild_id) DO UPDATE SET message=excluded.message
    ''', (guild_id, message))

    conn.commit()
    conn.close()

    await interaction.response.send_message(f'Welcome message has been set to: {message}!', ephemeral=True)

@bot.tree.command(name="set_joinrole", description="Set the join role on join!")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
async def set_joinrole(interaction: discord.Interaction, role: discord.Role):
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
        return

    role_id = role.id
    
    if not interaction.guild.get_role(role_id):
        await interaction.response.send_message(f'Role ID: `{role_id}` does not exist!', ephemeral=True)
    
    guild_id = interaction.guild_id
    conn = get_jr_connection()
    cursor = conn.cursor()

    cursor.execute('''
    INSERT INTO join_roles (guild_id, role_id)
    VALUES (?, ?)
    ON CONFLICT(guild_id) DO UPDATE SET role_id=excluded.role_id
    ''', (guild_id, role_id))

    conn.commit()
    conn.close()

    await interaction.response.send_message(f'Join role has been set to: {interaction.guild.get_role(role_id).mention}!', ephemeral=True)

@bot.tree.command(name="premium_only", description="A premium-only command.")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
async def premium_only(interaction: discord.Interaction):
    if is_premium(interaction.user.id):
        await interaction.response.send_message(content='You have access to this command!')
    else:
        await interaction.response.send_message(content='You must subscribe to premium to get access to this command.')

@bot.tree.command(name="purge", description="Mass delete messages.")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
async def purge(interaction: discord.Interaction, amount: int):

    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
        return
    
    await interaction.response.send_message(content=f'Starting to purge {amount} messages!', ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount, reason="Purging messages via command.")
    
    embed = discord.Embed(
        title=f"{len(deleted)} Purged Messages",
        description=f"{len(deleted)} messages have been purged by: **{interaction.user.mention}**!",
        color = discord.Color.dark_gray(),
    )

    
    message: discord.Message = await interaction.followup.send(embed=embed)
    await asyncio.sleep(3)
    await message.delete()

@bot.tree.command(name="kick", description="Kick a user from your Discord server")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str):

    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
        return
    
    await user.kick(reason=reason)
    await interaction.response.send_message(f"✅ Successfully kicked **{user}**!")

@bot.tree.command(name="ban", description="Ban a user from your Discord server")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str):

    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
        return
    
    await user.ban(reason=reason)
    await interaction.response.send_message(f"✅ Successfully banned **{user}**!")

@bot.tree.command(name="mute", description="Mute a user on your Discord server")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
async def mute(interaction: discord.Interaction, user: discord.Member, reason: str):

    if not interaction.user.guild_permissions.mute_members:
        await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
        return

    role = discord.utils.get(interaction.guild.roles, name="Muted")

    if get(interaction.guild.roles, name="Muted"):
        await user.add_roles(role)
        await interaction.response.send_message(f"✅ Sucessfully muted **{user}**!")
    else:
        await interaction.response.send_message(f"🚫 A muted role does not exist! Please create one.")

@bot.tree.command(name="reaction_role", description="Allow a reaction to give a role")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
@app_commands.describe(message_id="The ID of the message to react to", emoji="The emoji for the role", role="The role to assign")
async def reaction_role(interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
        return

    conn = get_reaction_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
        INSERT INTO reaction_roles (message_id, emoji, role_id)
        VALUES (?, ?, ?)
        ''', (message_id, emoji, role.id))
        
        conn.commit()
        channel = interaction.channel
        message = await channel.fetch_message(message_id)
        await message.add_reaction(emoji)

        await interaction.response.send_message(content=f'Reaction role set! React with :{emoji}: to assign {role.mention}!', ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to set reaction role: {str(e)}.")
    finally:
        conn.close()

@bot.tree.command(name="del_reaction_role", description="Remove a reaction role from a specific message.")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
@app_commands.describe(message_id="The ID of the message to remove the reaction from", emoji="The emoji to remove")
async def del_reaction_role(interaction: discord.Interaction, message_id: int, emoji: str):

    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message("You don't have permission to manage roles.", ephemeral=True)
        return

    conn = get_reaction_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM reaction_roles WHERE message_id = ? AND emoji = ?', (message_id, emoji))
    changes = conn.total_changes
    conn.commit()

    if changes > 0:
        try:
            channel = interaction.channel
            message = await channel.fetch_message(message_id)
            await message.clear_reaction(emoji)

            await interaction.response.send_message(f"Removed the reaction role for {emoji} on message {message_id}.", ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message(f"Message with ID {message_id} not found, but reaction role has been removed from the database.", ephemeral=True)
    else:
        await interaction.response.send_message(f"No reaction role found for {emoji} on message {message_id}.", ephemeral=True)

    conn.close()

@bot.tree.command(name="add_premium", description="Add a user to premium.")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
async def add_premium(interaction: discord.Interaction, user: discord.User):
    if user and interaction.user.id == 1144267370769174608:
        try:
            conn = sqlite3.connect('storage/premium_users.sqlite')
            cursor = conn.cursor()

            expiry_date = datetime.now() + timedelta(days=30)
            cursor.execute('''
            INSERT INTO premium_users (user_id, premium_expiry_date) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET premium_expiry_date=excluded.premium_expiry_date
            ''', (user.id, expiry_date))

            conn.commit()
            
            await interaction.response.send_message(content=f'{user.mention} has been added the premium list!', ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(content=f'Error: {e}', ephemeral=True)
        finally:
            conn.close()

@bot.tree.command(name="members", description="Get the amount of members in the server.")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
async def members(interaction: discord.Interaction):
    guild = interaction.guild

    total_members = guild.member_count
    humans = len([member for member in guild.members if not member.bot])
    bots = len([member for member in guild.members if member.bot])
    online_members = len([member for member in guild.members if not member.bot and (member.status == discord.Status.online or member.status == discord.Status.do_not_disturb)])

    embed = discord.Embed(
        title='',
        color = discord.Color.dark_gray()
    )
    
    embed.add_field(name="Total Members", value=total_members, inline=True)
    embed.add_field(name="Humans", value=humans, inline=True)
    embed.add_field(name="Bots", value=bots, inline=True)
    embed.add_field(name="Online", value=online_members, inline=True)

    embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ping", description="Get the ping of the bot.")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
async def ping(interaction: discord.Interaction):
    start_time = time.time()

    await interaction.response.defer()

    end_time = time.time()
    latency = round(bot.latency * 1000)
    response_time = round((end_time - start_time) * 1000)

    await interaction.followup.send(content=f'🏓 Pong!\nLatency: `{latency}ms`\nResponse Time: `{response_time}ms`')

@bot.tree.command(name="roleall", description="Give everyone a specific role.")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
async def roleall(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message("You don't have permission to manage roles.", ephemeral=True)
        return
    guild = interaction.guild
    count = 0
    amt = 0

    for member in guild.members:
        if not role in member.roles and not member.bot:
            amt += 1

    if not amt >= 1:
        await interaction.response.send_message(f'There are {amt} members to add {role.mention} to!', ephemeral=True)
        return
    
    await interaction.response.send_message(f'{role.name} is being added to {amt} users!\nThis should take `{round(amt * 0.1)}` seconds.')
    
    for member in guild.members:
        if not role in member.roles and not member.bot:
            await member.add_roles(role, reason=f"Role has been added by: {interaction.user.global_name}")
            count += 1
            asyncio.sleep(.1)
        

    await interaction.followup.send(f'I have applied the `{role.name}` role to `{count}` users!', ephemeral=True)
    
@bot.tree.command(name="role", description="Give a role to a specific user.")
@app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
async def role(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    if role and user:
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("You don't have permission to manage roles.", ephemeral=True)
            return
        
        try:
            await user.add_roles(role)
            await interaction.response.send_message(content=f'{role.name} has been applied to {user.mention}!', ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(content=f'Error giving {role.mention} to {user.mention} due to {e}.', ephemeral=True)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError,):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(f'You are on cooldown for this command! Try again in `{round(error.retry_after, 2)}` seconds!', ephemeral=True)

bot.run(token=config.TOKEN)