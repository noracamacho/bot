# bot.py
import discord
from discord.ext import commands
from discord.ui import Button, View
from discord import app_commands, ui, ButtonStyle
from datetime import datetime
import uuid
import random
import requests
import base64
import asyncio
from typing import Optional
from datetime import datetime, timedelta, timezone
from google.cloud.firestore_v1.base_query import FieldFilter, BaseCompositeFilter
from db.db_management import (
    add_path, add_channel_to_path, add_topic, add_task, get_topics, get_start_date,
    get_user_tasks, mark_user_task, get_all_paths, get_weeks_for_path, get_path_duration, get_topics_by_path,
    get_path_by_channel, get_function_usage, get_command_metrics, get_channel_name, get_path_name, 
    add_path_to_user, is_admin, get_all_tasks_for_path, get_all_tasks_for_path, get_user_tasks_by_path, 
    record_function_usage, update_start_date, record_satisfaction_response, remove_channel_from_path, 
    get_command_metrics_by_channel, get_command_metrics_by_path, get_task_name, delete_task, delete_topic, 
    delete_path
)
# record_function_usage, get_command_metrics_by_channel, get_command_metrics_by_path,
from db.firebase_config import db
from config import DISCORD_TOKEN, RAPIDAPI_KEY, JUDGE0_URL


intents = discord.Intents.default()
intents.message_content = True
intents.members = True  
bot = commands.Bot(command_prefix="!", intents=intents)
# tree = bot.tree

class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("Slash commands have been synced.")

    async def on_ready(self):
        print(f'Logged in as {self.user}')
        print(f'Commands synced: {[cmd.name for cmd in self.tree.get_commands()]}')
    
    
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await tree.sync()  # Sync the slash commands

@bot.event
async def on_member_update(before, after):
    # Check if the role has been updated
    if before.roles != after.roles:
        add_path_to_user(after)

@bot.event
async def on_guild_channel_create(channel):
    # Add a listener for the members in the newly created channel
    for member in channel.members:
        add_path_to_user(member)

@bot.event
async def on_member_join(member):
    add_path_to_user(member)

@bot.event
async def on_guild_join(guild):
    for member in guild.members:
        add_path_to_user(member)

client = MyClient()
tree = client.tree



class PathModal(ui.Modal):
    def __init__(self):
        super().__init__(title="Add New Path")

        self.path_name = ui.TextInput(
            label="Path Name",
            placeholder="Enter the name of the path",
            required=True
        )
        self.duration_weeks = ui.TextInput(
            label="Duration (weeks)",
            placeholder="Enter the duration in weeks",
            required=True
        )

        self.add_item(self.path_name)
        self.add_item(self.duration_weeks)

    async def on_submit(self, interaction: discord.Interaction):
        path_name = self.path_name.value
        duration_weeks = self.duration_weeks.value

        if not duration_weeks.isdigit():
            await interaction.response.send_message("Duration must be a number.", ephemeral=True)
            return

        duration_weeks = int(duration_weeks)
        path_id = add_path(path_name, duration_weeks)
        await interaction.response.send_message(f'Path "{path_name}" added with ID {path_id} and duration {duration_weeks} weeks.', ephemeral=True)
        record_function_usage(interaction.user.id, 'addpath')


@tree.command(name="addpath", description="Add a new path")
async def addpath(interaction: discord.Interaction):
    modal = PathModal()
    await interaction.response.send_modal(modal)


            
class ConfirmButton(Button):
    def __init__(self, new_path_id, channel_id, start_date, new_path_name, current_path_id):
        super().__init__(label="Yes", style=ButtonStyle.success)
        self.new_path_id = new_path_id
        self.channel_id = str(channel_id)  # Ensure channel_id is a string
        self.start_date = start_date
        self.new_path_name = new_path_name
        self.current_path_id = current_path_id

    async def callback(self, confirm_interaction: discord.Interaction):
        try:
            print(f"Attempting to remove channel {self.channel_id} from path {self.current_path_id}")  # Debugging info
            remove_channel_from_path(self.current_path_id, self.channel_id)

            print(f"Adding channel {self.channel_id} to path {self.new_path_id}")  # Debugging info
            add_channel_to_path(self.new_path_id, self.channel_id, confirm_interaction.guild.get_channel(int(self.channel_id)).name, self.start_date)

            # Update user roles for all members in the channel
            channel = confirm_interaction.guild.get_channel(int(self.channel_id))
            if channel:
                for member in channel.members:
                    if not member.bot:
                        print(f"Adding path to user {member.id} in channel {self.channel_id}")  # Debugging info
                        add_path_to_user(member, self.channel_id)

            await confirm_interaction.response.send_message(f'Channel {self.channel_id} linked to path "{self.new_path_name}" starting on {self.start_date}.', ephemeral=True)
        except Exception as e:
            await confirm_interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
            print(f"Error in confirming channel linking: {e}")
            

class ChannelLinkModal(ui.Modal, title="Link Channel to Path"):
    def __init__(self, path_id, path_name):
        super().__init__()
        self.path_id = path_id
        self.path_name = path_name

        self.channel_id = ui.TextInput(
            label="Channel ID",
            placeholder="Enter the channel ID",
            required=True
        )
        self.start_date = ui.TextInput(
            label="Start Date (YYYY-MM-DD)",
            placeholder="Enter the start date",
            required=True
        )

        self.add_item(self.channel_id)
        self.add_item(self.start_date)

    async def on_submit(self, interaction: discord.Interaction):
        channel_id = self.channel_id.value
        start_date = self.start_date.value

        try:
            print(f"Checking path for channel ID: {channel_id}")  # Debugging info
            path_info = get_path_by_channel(int(channel_id))
            print(f"Path info: {path_info}")  # Debugging info
            if path_info:
                current_path_id, current_path_name = path_info
                print(f"Path: {path_info}")  # Debugging
                print(f"Channel {channel_id} is currently linked to path {current_path_name} with ID {current_path_id}")  # Debugging info
                confirm_view = View()
                confirm_view.add_item(ConfirmButton(self.path_id, channel_id, start_date, self.path_name, current_path_id))
                await interaction.response.send_message(f"The channel ID {channel_id} is already linked to path {current_path_name}. Do you want to link it to the new path?", view=confirm_view, ephemeral=True)
            else:
                print(f"Channel {channel_id} is not linked to any path. Proceeding to link it to {self.path_id}")  # Debugging info
                add_channel_to_path(self.path_id, channel_id, interaction.guild.get_channel(int(channel_id)).name, start_date)
                await interaction.response.send_message(f'Channel {channel_id} linked to path "{self.path_name}" starting on {start_date}.', ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
            print(f"Error in linking channel: {e}")


@tree.command(name="linkchannel", description="Link a channel to a path")
async def linkchannel(interaction: discord.Interaction):
    paths = get_all_paths()
    if not paths:
        await interaction.response.send_message("No paths available.", ephemeral=True)
        return
    
    class PathButton(Button):
        def __init__(self, path_id, path_name):
            super().__init__(label=path_name, style=discord.ButtonStyle.primary)
            self.path_id = path_id
            self.path_name = path_name

        async def callback(self, button_interaction: discord.Interaction):
            modal = ChannelLinkModal(self.path_id, self.path_name)
            await button_interaction.response.send_modal(modal)

    path_view = View()
    for path_id, path_name in paths:
        path_view.add_item(PathButton(path_id, path_name))

    await interaction.response.send_message("Please select a path to link the channel:", view=path_view, ephemeral=True)



class TopicModal(ui.Modal):
    def __init__(self, path_id, week, path_name):
        super().__init__(title="Add New Topic")
        self.path_id = path_id
        self.week = week
        self.path_name = path_name

        self.topic_name = ui.TextInput(
            label="Topic Name",
            placeholder="Enter the topic name",
            required=True
        )
        self.description = ui.TextInput(
            label="Description",
            placeholder="Enter a brief description",
            required=False,
            style=discord.TextStyle.paragraph
        )

        self.add_item(self.topic_name)
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        topic_name = self.topic_name.value
        description = self.description.value
        
        topic_id = add_topic(self.path_id, self.week, topic_name, description)
        await interaction.response.send_message(f'Topic "{topic_name}" added to path "{self.path_name}", week {self.week} with ID {topic_id}.', ephemeral=True)
        record_function_usage(interaction.user.id, 'addtopic')



@tree.command(name="addtopic", description="Add a new topic to a path")
async def addtopic(interaction: discord.Interaction):
    paths = get_all_paths()
    if not paths:
        await interaction.response.send_message("No paths available.", ephemeral=True)
        return

    class PathButton(Button):
        def __init__(self, path_id, path_name):
            super().__init__(label=path_name, style=discord.ButtonStyle.primary)
            self.path_id = path_id
            self.path_name = path_name

        async def callback(self, button_interaction: discord.Interaction):
            duration_weeks = get_path_duration(self.path_id)
            existing_weeks = get_weeks_for_path(self.path_id)
            all_weeks = list(range(1, duration_weeks + 1))
            available_weeks = [week for week in all_weeks if week not in existing_weeks]

            if not available_weeks:
                await button_interaction.response.send_message(f'All weeks for path "{self.path_name}" already have topics.', ephemeral=True)
                return

            class WeekButton(Button):
                def __init__(self, week, path_id, path_name):
                    super().__init__(label=f"Week {week}", style=discord.ButtonStyle.secondary)
                    self.week = week
                    self.path_id = path_id
                    self.path_name = path_name

                async def callback(self, week_button_interaction: discord.Interaction):
                    modal = TopicModal(self.path_id, self.week, self.path_name)
                    await week_button_interaction.response.send_modal(modal)

            week_view = View()
            for week in available_weeks:
                week_view.add_item(WeekButton(week, self.path_id, self.path_name))

            await button_interaction.response.send_message("Please select a week:", view=week_view, ephemeral=True)

    path_view = View()
    for path_id, path_name in paths:
        path_view.add_item(PathButton(path_id, path_name))

    await interaction.response.send_message("Please select a path:", view=path_view, ephemeral=True)



class TaskModal(ui.Modal, title="Add New Task"):
    def __init__(self, path_id, topic_id, topic_name, week):
        super().__init__()
        self.path_id = path_id
        self.topic_id = topic_id
        self.topic_name = topic_name
        self.week = week

        self.task_name = ui.TextInput(
            label="Task Name",
            placeholder="Enter the task name",
            required=True
        )

        self.add_item(self.task_name)

    async def on_submit(self, interaction: discord.Interaction):
        task_name = self.task_name.value

        try:
            task_id = add_task(self.path_id, self.topic_id, task_name, self.week)
            if task_id:
                await interaction.response.send_message(f'Task "{task_name}" added to topic "{self.topic_name}", week {self.week}, with ID {task_id}.', ephemeral=True)
            else:
                await interaction.response.send_message(f"Failed to add task to topic.", ephemeral=True)
            record_function_usage(interaction.user.id, 'addtask')
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
            print(f"Error in adding task: {e}")

@tree.command(name="addtask", description="Add a new task to a topic")
async def addtask(interaction: discord.Interaction):
    paths = get_all_paths()
    if not paths:
        await interaction.response.send_message("No paths available.", ephemeral=True)
        return

    class PathButton(Button):
        def __init__(self, path_id, path_name):
            super().__init__(label=path_name, style=discord.ButtonStyle.primary)
            self.path_id = path_id
            self.path_name = path_name

        async def callback(self, button_interaction: discord.Interaction):
            try:
                print(f"Fetching topics for path {self.path_id}")  # Debugging info
                topics = get_topics_by_path(self.path_id)
                if not topics:
                    await button_interaction.response.send_message(f'No topics available for path "{self.path_name}".', ephemeral=True)
                    return

                print(f"Fetched topics: {topics}")  # Debugging info
                class TopicButton(Button):
                    def __init__(self, path_id, topic_id, topic_data):
                        super().__init__(label=topic_data['name'], style=discord.ButtonStyle.secondary)
                        self.path_id = path_id
                        self.topic_id = topic_id
                        self.topic_name = topic_data['name']
                        self.week = topic_data['week']

                    async def callback(self, topic_button_interaction: discord.Interaction):
                        print(f"Selected topic {self.topic_name} with ID {self.topic_id}, week {self.week}")  # Debugging info
                        modal = TaskModal(self.path_id, self.topic_id, self.topic_name, self.week)
                        await topic_button_interaction.response.send_modal(modal)

                topic_view = View()
                for topic_id, topic_data in topics:
                    topic_view.add_item(TopicButton(self.path_id, topic_id, topic_data))

                await button_interaction.response.send_message("Please select a topic:", view=topic_view, ephemeral=True)
            except Exception as e:
                await button_interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
                print(f"Error in PathButton callback: {e}")

    path_view = View()
    for path_id, path_name in paths:
        path_view.add_item(PathButton(path_id, path_name))

    await interaction.response.send_message("Please select a path:", view=path_view, ephemeral=True)
    
    

class DateCorrectionModal(ui.Modal):
    def __init__(self, path_id, channel_id, incorrect_date):
        super().__init__(title="Current date format is incorrect.")
        self.path_id = path_id
        self.channel_id = channel_id
        self.new_start_date = ui.TextInput(
            label="Enter new start date (YYYY-MM-DD)",
            style=discord.TextStyle.short,
            placeholder=f"{incorrect_date}"
        )

        # self.add_item(self.error_message)
        self.add_item(self.new_start_date)

    async def on_submit(self, interaction: discord.Interaction):
        new_date_str = self.new_start_date.value
        try:
            new_start_date = datetime.strptime(new_date_str, '%Y-%m-%d')
            db.collection('path_channels').document(str(self.channel_id)).update({
                'start_date': new_date_str
            })
            await interaction.response.send_message(f"Start date updated to {new_date_str}. Please re-run the /checklist command.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message(f"The provided date '{new_date_str}' is not in the correct format (YYYY-MM-DD). Please try again.", ephemeral=True)



class WeekPaginator(View):
    def __init__(self, pages):
        super().__init__()
        self.pages = pages
        self.current_page = 0
        self.previous_button = Button(label="Previous", style=discord.ButtonStyle.primary, custom_id="previous_page")
        self.next_button = Button(label="Next", style=discord.ButtonStyle.primary, custom_id="next_page")
        self.update_buttons()
        self.add_item(self.previous_button)
        self.add_item(self.next_button)

    @property
    def page_content(self):
        return self.pages[self.current_page]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data["custom_id"] == "previous_page":
            if self.current_page > 0:
                self.current_page -= 1
                self.update_buttons()
                await interaction.response.edit_message(content=self.page_content, view=self)
            return False
        elif interaction.data["custom_id"] == "next_page":
            if self.current_page < len(self.pages) - 1:
                self.current_page += 1
                self.update_buttons()
                await interaction.response.edit_message(content=self.page_content, view=self)
            return False
        return True

    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == len(self.pages) - 1



@tree.command(name="status", description="Check your status")
async def status(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    user_id = str(interaction.user.id)  # Ensure user_id is a string
    channel_id = interaction.channel_id
    path_info = get_path_by_channel(channel_id)

    if path_info is None:
        await interaction.followup.send("This channel is not associated with any path.", ephemeral=True)
        return

    path_id, path_name = path_info
    start_date = get_start_date(channel_id)

    if not start_date:
        await interaction.followup.send("No start date found for this channel.", ephemeral=True)
        return

    try:
        start_date = datetime.strptime(str(start_date), '%Y-%m-%d').date()
    except ValueError:
        await interaction.followup.send("The start date format is incorrect.", ephemeral=True)
        return

    current_date = datetime.now().date()
    delta = current_date - start_date
    current_week = (delta.days // 7) + 1

    duration_weeks = get_path_duration(path_id)
    current_week = min(current_week, duration_weeks)

    # Fetch all tasks for the path
    user_tasks = get_user_tasks_by_path(user_id, path_id)
    user_task_dict = {task['task_id']: (task['completed'], task['proof_url']) for task in user_tasks}

    # Fetch topics for the path from the sub-collection
    topics_ref = db.collection('paths').document(path_id).collection('topics')
    topics = topics_ref.stream()
    weekly_responses = {}
    tasks_found = False
    for topic in topics:
        topic_data = topic.to_dict()
        week = topic_data.get('week')
        task_ids = topic_data.get('tasks', [])
        
        if task_ids:  # Only process weeks that have tasks
            if week not in weekly_responses:
                weekly_responses[week] = f'**Path {path_name}**\n**You are in week: {current_week}**\n\n**Week: {week}**\n```\n'
                weekly_responses[week] += '{:<19} {:<59} {:<10}\n'.format('Task', 'Proof URL', 'Status')
                weekly_responses[week] += '-' * 94 + '\n'

            for task_id in task_ids:
                task_doc = db.collection('tasks').document(task_id).get()
                if task_doc.exists:
                    tasks_found = True
                    task_data = task_doc.to_dict()
                    task_name = task_data.get('name')
                    completed, proof_url = user_task_dict.get(task_id, (False, " "))
                    status = '✅' if completed else '❌'
                    weekly_responses[week] += '{:<19} {:<61} {:<10}\n'.format(task_name, proof_url, status)

    if not tasks_found:
        await interaction.followup.send("There are no tasks available for this path.", ephemeral=True)
        return

    pages = []
    for week in sorted(weekly_responses.keys()):
        weekly_responses[week] += '```'
        pages.append(weekly_responses[week])

    if not pages:
        await interaction.followup.send("No tasks found for this path.", ephemeral=True)
        return

    paginator = WeekPaginator(pages)
    await interaction.followup.send(paginator.page_content, view=paginator, ephemeral=True)

    record_function_usage(user_id, 'status', channel_id)



class TaskDeleteButton(Button):
    def __init__(self, task_id, task_name, path_id, topic_id):
        super().__init__(label=f"Delete {task_name}", style=ButtonStyle.danger)
        self.task_id = task_id
        self.task_name = task_name
        self.path_id = path_id
        self.topic_id = topic_id

    async def callback(self, interaction: discord.Interaction):
        try:
            delete_task(self.task_id, self.path_id, self.topic_id)
            await interaction.response.send_message(f'Task "{self.task_name}" with ID {self.task_id} has been deleted.', ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)



@tree.command(name="deletetask", description="Delete a task from a topic")
async def deletetask(interaction: discord.Interaction):
    paths = get_all_paths()
    if not paths:
        await interaction.response.send_message("No paths available.", ephemeral=True)
        return

    class PathButton(Button):
        def __init__(self, path_id, path_name):
            super().__init__(label=path_name, style=ButtonStyle.primary)
            self.path_id = path_id
            self.path_name = path_name

        async def callback(self, button_interaction: discord.Interaction):
            try:
                topics = get_topics_by_path(self.path_id)
                if not topics:
                    await button_interaction.response.send_message(f'No topics available for path "{self.path_name}".', ephemeral=True)
                    return

                class TopicButton(Button):
                    def __init__(self, path_id, topic_id, topic_name):
                        super().__init__(label=topic_name, style=ButtonStyle.secondary)
                        self.path_id = path_id
                        self.topic_id = topic_id
                        self.topic_name = topic_name

                    async def callback(self, topic_button_interaction: discord.Interaction):
                        try:
                            topic_ref = db.collection('paths').document(self.path_id).collection('topics').document(self.topic_id)
                            topic_doc = topic_ref.get()
                            if topic_doc.exists:
                                topic_data = topic_doc.to_dict()
                                tasks = topic_data.get('tasks', [])
                                if not tasks:
                                    await topic_button_interaction.response.send_message(f'No tasks available for topic "{self.topic_name}".', ephemeral=True)
                                    return

                                task_view = View()
                                for task_id in tasks:
                                    task_name = get_task_name(task_id)
                                    task_view.add_item(TaskDeleteButton(task_id, task_name, self.path_id, self.topic_id))

                                await topic_button_interaction.response.send_message("Please select a task to delete:", view=task_view, ephemeral=True)
                        except Exception as e:
                            await topic_button_interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

                topic_view = View()
                for topic in topics:
                    topic_id, topic_data = topic
                    topic_view.add_item(TopicButton(self.path_id, topic_id, topic_data['name']))

                await button_interaction.response.send_message("Please select a topic:", view=topic_view, ephemeral=True)
            except Exception as e:
                await button_interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    path_view = View()
    for path_id, path_name in paths:
        path_view.add_item(PathButton(path_id, path_name))

    await interaction.response.send_message("Please select a path:", view=path_view, ephemeral=True)

  
class ConfirmDeletePathButton(Button):
    def __init__(self, path_id, path_name):
        super().__init__(label=f"Delete {path_name}", style=ButtonStyle.danger)
        self.path_id = path_id
        self.path_name = path_name

    async def callback(self, interaction: discord.Interaction):
        try:
            delete_path(self.path_id)
            await interaction.response.send_message(f'Path "{self.path_name}" with ID {self.path_id} has been deleted.', ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)


@tree.command(name="deletepath", description="Delete a path")
async def deletepath(interaction: discord.Interaction):
    paths = get_all_paths()
    if not paths:
        await interaction.response.send_message("No paths available.", ephemeral=True)
        return

    path_view = View()
    for path_id, path_name in paths:
        path_view.add_item(ConfirmDeletePathButton(path_id, path_name))

    await interaction.response.send_message("Please select a path to delete:", view=path_view, ephemeral=True)
    
    
    
class TopicDeleteButton(Button):
    def __init__(self, path_id, path_name, topic_id, topic_name):
        super().__init__(label=f"Delete {topic_name}", style=ButtonStyle.danger)
        self.path_id = path_id
        self.path_name = path_name
        self.topic_id = topic_id
        self.topic_name = topic_name

    async def callback(self, interaction: discord.Interaction):
        try:
            delete_topic(self.path_id, self.topic_id)
            await interaction.response.send_message(f'Topic "{self.topic_name}" with ID {self.topic_id} has been deleted from path "{self.path_name}".', ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)



@tree.command(name="deletetopic", description="Delete a topic from a path")
async def deletetopic(interaction: discord.Interaction):
    paths = get_all_paths()
    if not paths:
        await interaction.response.send_message("No paths available.", ephemeral=True)
        return

    class PathButton(Button):
        def __init__(self, path_id, path_name):
            super().__init__(label=path_name, style=ButtonStyle.primary)
            self.path_id = path_id
            self.path_name = path_name

        async def callback(self, button_interaction: discord.Interaction):
            try:
                topics = get_topics_by_path(self.path_id)
                if not topics:
                    await button_interaction.response.send_message(f'No topics available for path "{self.path_name}".', ephemeral=True)
                    return

                topic_view = View()
                for topic_id, topic_data in topics:
                    topic_name = topic_data.get('name', 'Unnamed Topic')
                    topic_view.add_item(TopicDeleteButton(self.path_id, self.path_name, topic_id, topic_name))

                await button_interaction.response.send_message("Please select a topic to delete:", view=topic_view, ephemeral=True)
            except Exception as e:
                await button_interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    path_view = View()
    for path_id, path_name in paths:
        path_view.add_item(PathButton(path_id, path_name))

    await interaction.response.send_message("Please select a path:", view=path_view, ephemeral=True)



@tree.command(name="checklist", description="Show your checklist for the current path")
async def checklist(interaction: discord.Interaction):
    user_id = interaction.user.id
    channel_id = interaction.channel_id
    path = get_path_by_channel(channel_id)

    if path is None:
        await interaction.response.send_message("This channel is not associated with any path.", ephemeral=True)
        return

    path_id, path_name = path
    start_date = get_start_date(channel_id)

    if not start_date:
        await interaction.response.send_message("No start date found for this channel.", ephemeral=True)
        return

    try:
        start_date = datetime.strptime(str(start_date), '%Y-%m-%d').date()  # This ensures only the date part is used
    except ValueError:
        modal = DateCorrectionModal(path_id=path_id, channel_id=channel_id, incorrect_date=str(start_date))
        await interaction.response.send_modal(modal)
        return

    current_date = datetime.now().date()
    delta = current_date - start_date
    current_week = (delta.days // 7) + 1

    path_doc = db.collection('paths').document(path_id).get()
    if not path_doc.exists:
        await interaction.response.send_message("Path not found.", ephemeral=True)
        return

    topics_ref = db.collection('paths').document(path_id).collection('topics')
    topics = topics_ref.stream()

    weekly_responses = {}
    for topic in topics:
        topic_data = topic.to_dict()
        week = topic_data.get('week')
        if week not in weekly_responses:
            weekly_responses[week] = f'**Path {path_name}**\n**You are in week: {current_week}**\n\n**Week: {week}**\n```\n'
            weekly_responses[week] += '{:<45} {:<25} {:<15}\n'.format('Topic', 'Task', 'Due Date')
            weekly_responses[week] += '-' * 90 + '\n'

        topic_name = topic_data.get('name')
        task_ids = topic_data.get('tasks', [])
        due_date = (start_date + timedelta(days=week * 7)).strftime('%Y-%m-%d')

        if task_ids:
            for i, task_id in enumerate(task_ids):
                task_doc = db.collection('tasks').document(task_id).get()
                if task_doc.exists:
                    task_data = task_doc.to_dict()
                    task_name = task_data.get('name')
                    if i == 0:
                        weekly_responses[week] += '{:<45} {:<25} {:<15}\n'.format(topic_name, task_name, due_date)
                    else:
                        weekly_responses[week] += '{:<45} {:<25} {:<15}\n'.format('', task_name, due_date)
        else:
            weekly_responses[week] += '{:<45} {:<25} {:<15}\n'.format(topic_name, 'No tasks', due_date)

    pages = []
    for week in sorted(weekly_responses.keys()):
        weekly_responses[week] += '```'
        pages.append(weekly_responses[week])
        
    if not pages:
        await interaction.response.send_message("No topics found for this path.", ephemeral=True)
        return

    paginator = WeekPaginator(pages)
    await interaction.response.send_message(paginator.page_content, view=paginator, ephemeral=True)
    record_function_usage(user_id, 'checklist', channel_id)
    

class ProofModal(ui.Modal, title="Submit Proof URL"):
    def __init__(self, user_id, path_id, task_id, task_name):
        super().__init__(title="Submit Proof URL")
        self.user_id = user_id
        self.path_id = path_id
        self.task_id = task_id
        self.task_name = task_name

        self.proof_url = ui.TextInput(
            label="Proof URL",
            style=discord.TextStyle.short,
            placeholder="Enter the proof URL",
            required=True
        )

        self.add_item(self.proof_url)

    async def on_submit(self, interaction: discord.Interaction):
        proof_url = self.proof_url.value
        try:
            mark_user_task(self.user_id, self.path_id, self.task_id, True, proof_url)
            await interaction.response.send_message(f'Task "{self.task_name}" marked as completed with proof URL: {proof_url}!', ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)


@tree.command(name="complete", description="Mark a task as complete")
async def complete(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    user_id = interaction.user.id
    channel_id = interaction.channel_id
    path = get_path_by_channel(channel_id)

    if path is None:
        await interaction.followup.send("This channel is not associated with any path.", ephemeral=True)
        return

    path_id, path_name = path
    print(f"Path ID: {path_id}, Path Name: {path_name}")  # Debugging
    user_tasks = get_user_tasks_by_path(user_id, path_id)
    print(f"User Tasks: {user_tasks}")  # Debugging

    path_doc = db.collection('paths').document(path_id).get()
    if not path_doc.exists:
        await interaction.followup.send("Path not found.", ephemeral=True)
        return

    path_data = path_doc.to_dict()
    topics_ref = db.collection('paths').document(path_id).collection('topics')
    topics = [topic.to_dict() for topic in topics_ref.stream()]
    print(f"Topics: {topics}")  # Debugging

    all_weeks = range(1, get_path_duration(path_id) + 1)
    weeks_with_incomplete_tasks = [
        week for week in all_weeks
        if any(
            not any(
                ut['task_id'] == task_id and ut['completed']
                for ut in user_tasks
            )
            for topic in topics
            if topic['week'] == week
            for task_id in topic.get('tasks', [])
        )
    ]

    if not weeks_with_incomplete_tasks:
        await interaction.followup.send("You have no incomplete tasks.", ephemeral=True)
        return

    class WeekButton(Button):
        def __init__(self, week):
            super().__init__(label=f"Week {week}", style=discord.ButtonStyle.primary)
            self.week = week

        async def callback(self, button_interaction: discord.Interaction):
            await button_interaction.response.defer(ephemeral=True)

            incomplete_tasks = [
                (task_id, get_task_name(task_id))
                for topic in topics
                if topic['week'] == self.week
                for task_id in topic.get('tasks', [])
                if not any(
                    ut['task_id'] == task_id and ut['completed']
                    for ut in get_user_tasks_by_path(user_id, path_id)
                )
            ]

            if not incomplete_tasks:
                await button_interaction.followup.send("No incomplete tasks found for this week.", ephemeral=True)
                return

            class TaskButton(Button):
                def __init__(self, task_id, task_name):
                    super().__init__(label=task_name, style=discord.ButtonStyle.secondary)
                    self.task_id = task_id
                    self.task_name = task_name

                async def callback(self, task_button_interaction: discord.Interaction):
                    modal = ProofModal(user_id=user_id, path_id=path_id, task_id=self.task_id, task_name=self.task_name)
                    await task_button_interaction.response.send_modal(modal)

            task_view = View()
            for task_id, task_name in incomplete_tasks:
                task_view.add_item(TaskButton(task_id, task_name))

            await button_interaction.followup.send("Please select a task to mark as completed:", view=task_view, ephemeral=True)

    week_view = View()
    for week in weeks_with_incomplete_tasks:
        week_view.add_item(WeekButton(week))

    await interaction.followup.send("Please select a week:", view=week_view, ephemeral=True)
    record_function_usage(user_id, 'complete', channel_id)

    # Randomly trigger satisfaction survey after completing a task
    if random.random() < 0.1:  # 10% chance to trigger survey
        await send_satisfaction_survey_follow_up(interaction=interaction, user=interaction.user)



@tree.command(name="listtopics", description="List topics for a specific path and week")
@app_commands.describe(path_id="The ID of the path", week="The week number")
async def listtopics(interaction: discord.Interaction, path_id: str, week: int):
    topics = get_topics(path_id, week)
    
    if not topics:
        await interaction.response.send_message(f"No topics found for path ID {path_id} and week {week}.", ephemeral=True)
        return
    
    response = f"Topics for Path ID {path_id}, Week {week}:\n"
    response += '```\n'
    for topic in topics:
        response += f"- {topic['name']}\n"
    response += '```'
    
    await interaction.response.send_message(response, ephemeral=True)
    record_function_usage(interaction.user.id, 'listtopics', interaction.channel_id)


@tree.command(name="channel", description="Show the current channel information")
async def channel(interaction: discord.Interaction):
    channel_name = interaction.channel.name
    channel_id = interaction.channel_id
    await interaction.response.send_message(f'Estás en el canal: **{channel_name}**', ephemeral=True)
    record_function_usage(interaction.user.id, 'channel', channel_id)


@tree.command(name="path", description="Show the path associated with the current channel")
async def path(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    path = get_path_by_channel(channel_id)

    if path is None:
        await interaction.response.send_message("Este canal no está asociado con ningún path.", ephemeral=True)
        return

    path_name = path[1]
    await interaction.response.send_message(path_name, ephemeral=True)
    record_function_usage(interaction.user.id, 'path', channel_id)


#  Judge0
language_choices = [
    app_commands.Choice(name='Python', value='python'),
    app_commands.Choice(name='C', value='c'),
    app_commands.Choice(name='C++', value='cpp'),
    app_commands.Choice(name='JavaScript', value='javascript'),
    app_commands.Choice(name="Java", value="java"),
]

@tree.command(name="submit-code", description="Submit your code to run")
@app_commands.describe(language='Programming language')
@app_commands.choices(language=language_choices)
async def submit_code(interaction: discord.Interaction, language: app_commands.Choice[str]):
    language_value = language.value

    class CodeSubmissionModal(discord.ui.Modal):
        def __init__(self):
            super().__init__(title="Submit Code")

            self.source_code = discord.ui.TextInput(
                label="Source Code",
                style=discord.TextStyle.paragraph,
                custom_id="source_code_input",
                required=True,
                max_length=4000  # As necessary
            )
            self.add_item(self.source_code)
            
            if language_value == 'java':
                self.java_hint = discord.ui.TextInput(
                    label="Hint",
                    style=discord.TextStyle.short,
                    placeholder="Please use 'Main' as the class name for Java.",
                    required=False,
                )
                self.add_item(self.java_hint)

        async def on_submit(self, interaction: discord.Interaction):
            source_code = self.source_code.value
            await run_code(interaction, language_value, source_code)

    await interaction.response.send_modal(CodeSubmissionModal())

async def run_code(interaction: discord.Interaction, language_value: str, source_code: str):  #change
    language_map = {  #change
        'python': 71,
        'cpp': 54,
        'c': 50,
        'javascript': 63,
        'java': 62
    }

    if language_value not in language_map:
        await interaction.response.send_message(f"Lenguaje no soportado: {language_value}")
        return

    # Ensure proper formatting of the source code
    formatted_source_code = "\n".join(line.rstrip() for line in source_code.splitlines())
    language_id = language_map[language_value]
    source_code_encoded = base64.b64encode(formatted_source_code.encode('utf-8')).decode('utf-8')

    payload = {
        "language_id": language_id,
        "source_code": source_code_encoded,
        "stdin": ""
    }

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "judge0-ce.p.rapidapi.com",
        "Content-Type": "application/json"
    }
    
    response = requests.post(
        "https://judge0-ce.p.rapidapi.com/submissions?base64_encoded=true&wait=true",
        json=payload,
        headers=headers
    )

    try:
        result_data = response.json()
        # print("Parsed result data:", json.dumps(result_data, indent=2))

        stdout = result_data.get('stdout')
        stderr = result_data.get('stderr')

        output = base64.b64decode(stdout).decode('utf-8') if stdout else None
        error = base64.b64decode(stderr).decode('utf-8') if stderr else None

        print("stdout:", output)
        print("stderr:", error)

        if output:
            await interaction.response.send_message(f"Resultado:\n```{output}```")
        elif error:
            await interaction.response.send_message(f"Error:\n```{error}```")
        else:
            await interaction.response.send_message("No output or error returned.")
    except requests.exceptions.RequestException as e:
        await interaction.response.send_message(f"Error al comunicarse con Judge0: {e}")
    except Exception as e:
        await interaction.response.send_message(f"Unexpected error: {e}")


@tree.command(name="usersummary", description="Show a summary of task completion for users in the current channel")
async def usersummary(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    channel_id = interaction.channel_id
    path = get_path_by_channel(channel_id)

    if path is None:
        await interaction.followup.send("This channel is not associated with any path.", ephemeral=True)
        return

    path_id, path_name = path
    users = [member for member in interaction.guild.get_channel(channel_id).members if not member.bot and not is_admin(member)]

    if not users:
        await interaction.followup.send("No users found in this channel.", ephemeral=True)
        return

    summary = []

    total_tasks = len(get_all_tasks_for_path(path_id))

    for user in users:
        user_tasks = get_user_tasks_by_path(user.id, path_id)
        completed_tasks = sum(1 for task in user_tasks if task['completed'])
        pending_tasks = total_tasks - completed_tasks
        summary.append((user.name, completed_tasks, pending_tasks))

    summary_str = "```\n"
    summary_str += "{:<20} {:<15} {:<15}\n".format("User", "Completed", "Pending")
    summary_str += "-" * 50 + "\n"
    for user_name, completed, pending in summary:
        summary_str += "{:<20} {:<15} {:<15}\n".format(user_name, completed, pending)
    summary_str += "```"

    await interaction.followup.send(f"Task Summary for Path: **{path_name}**\n{summary_str}", ephemeral=True)
    record_function_usage(interaction.user.id, 'usersummary', channel_id)



@tree.command(name="listusers", description="Get a list of users in the current channel")
async def listusers(interaction: discord.Interaction):
    channel = interaction.channel
    if not channel:
        await interaction.response.send_message("This command can only be executed in a text channel.", ephemeral=True)
        return

    user_names = [member.display_name for member in channel.members if not member.bot]
    user_list_message = "Users in this channel:\n" + "\n".join(user_names)

    await interaction.response.send_message(user_list_message, ephemeral=True)

    # Record function usage if you have such a function
    record_function_usage(interaction.user.id, 'listusers', channel.id)



@tree.command(name="userprogress6", description="Show a user's progress for tasks in the current channel")
async def userprogress(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    channel_id = interaction.channel_id
    path = get_path_by_channel(channel_id)

    if path is None:
        await interaction.followup.send("This channel is not associated with any path.", ephemeral=True)
        return

    path_id, path_name = path
    tasks = get_all_tasks_for_path(path_id)  # Function to fetch all tasks for the path
    users = [member for member in interaction.guild.get_channel(channel_id).members if not member.bot and not is_admin(member)]

    if not users:
        await interaction.followup.send("No users found in this channel.", ephemeral=True)
        return

    current_user_index = 0

    async def send_user_progress(index):
        user = users[index]
        user_tasks = get_user_tasks(user.id, path_id)
        user_task_status = ["✅" if any(ut[0] == tasks[i][0] and ut[1] for ut in user_tasks) else "❌" for i in range(len(tasks))]

        # Create a header row for the table
        header_row = ["Task"] + [f"Task {i+1}" for i in range(len(tasks))]
        user_row = [user.name] + user_task_status

        # Format the table as a string with fixed-width columns
        table_str = "```\n"
        table_str += "{:<10}".format(header_row[0])
        for cell in header_row[1:]:
            table_str += "{:<10}".format(cell)
        table_str += "\n"
        table_str += "{:<10}".format(user_row[0])
        for cell in user_row[1:]:
            table_str += "{:<10}".format(cell)
        table_str += "\n"
        table_str += "```"

        view = View()

        if index > 0:
            view.add_item(Button(label="Previous", style=discord.ButtonStyle.primary, custom_id="prev"))

        if index < len(users) - 1:
            view.add_item(Button(label="Next", style=discord.ButtonStyle.primary, custom_id="next"))

        await interaction.followup.send(f"User Progress for Path: **{path_name}**\n{table_str}", view=view, ephemeral=True)

    await send_user_progress(current_user_index)

    @client.event
    async def on_interaction(interaction: discord.Interaction):
        nonlocal current_user_index

        if interaction.data["custom_id"] == "prev":
            current_user_index -= 1
            await interaction.response.edit_message(content=None, view=None)
            await send_user_progress(current_user_index)

        elif interaction.data["custom_id"] == "next":
            current_user_index += 1
            await interaction.response.edit_message(content=None, view=None)
            await send_user_progress(current_user_index)



# %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


# Function to record satisfaction response in Firestore
def record_satisfaction_response(user_id, responses):
    response_id = str(uuid.uuid4())
    responses["user_id"] = user_id
    db.collection('satisfaction_responses').document(response_id).set(responses)

# Satisfaction Survey Modal
class SatisfactionSurveyModal(ui.Modal, title="Satisfaction Survey"):
    overall_satisfaction = ui.TextInput(
        label="Overall Satisfaction (1-10)",
        style=discord.TextStyle.short,
        placeholder="Enter a number between 1 and 10",
        required=True
    )
    ease_of_use = ui.TextInput(
        label="Ease of Use (1-10)",
        style=discord.TextStyle.short,
        placeholder="Enter a number between 1 and 10",
        required=True
    )
    reliability = ui.TextInput(
        label="Reliability (1-10)",
        style=discord.TextStyle.short,
        placeholder="Enter a number between 1 and 10",
        required=True
    )
    support_satisfaction = ui.TextInput(
        label="Support Satisfaction (1-10)",
        style=discord.TextStyle.short,
        placeholder="Enter a number between 1 and 10",
        required=True
    )
    suggestions = ui.TextInput(
        label="Suggestions for Improvement",
        style=discord.TextStyle.paragraph,
        placeholder="Any suggestions for improving the bot?",
        required=False
    )

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        responses = {
            "overall_satisfaction": self.overall_satisfaction.value,
            "ease_of_use": self.ease_of_use.value,
            "reliability": self.reliability.value,
            "support_satisfaction": self.support_satisfaction.value,
            "suggestions": self.suggestions.value,
        }
        record_satisfaction_response(self.user_id, responses)
        await interaction.response.send_message("Thank you for your feedback!", ephemeral=True)

# Function to send satisfaction survey to a user
async def send_satisfaction_survey(interaction: discord.Interaction, user: discord.Member):
    try:
        await interaction.response.send_modal(SatisfactionSurveyModal(user_id=user.id))
    except Exception as e:
        print(f"Error sending survey to {user.name}: {e}")

async def send_satisfaction_survey_follow_up(interaction: discord.Interaction, user: discord.Member):
    modal = SatisfactionSurveyModal(user_id=user.id)
    await interaction.followup.send_modal(modal)

# Command to request satisfaction feedback from all users in the channel
@tree.command(name="request_satisfaction", description="Request satisfaction feedback from all users in the channel")
async def request_satisfaction(interaction: discord.Interaction):
    channel = interaction.channel
    members = [member for member in channel.members if not member.bot]

    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send(f"Requesting satisfaction feedback from {len(members)} users in the channel.", ephemeral=True)

    for member in members:
        try:
            await send_satisfaction_survey_follow_up(interaction, member)
        except Exception as e:
            print(f"Error sending survey to {member.name}: {e}")

    record_function_usage(interaction.user.id, 'request_satisfaction', interaction.channel_id)


@tree.command(name="add_users_from_channel", description="Add all users from the current channel to Firestore, excluding bots and admins")
async def addusersfromchannel(interaction: discord.Interaction):
    channel = interaction.channel
    if not channel:
        await interaction.response.send_message("This command can only be executed in a text channel.", ephemeral=True)
        return

    for member in channel.members:
        if not member.bot and not any(role.permissions.administrator for role in member.roles):
            add_path_to_user(member, interaction.channel_id)

    await interaction.response.send_message(f"Users from {channel.name} have been added to Firestore, excluding bots and admins.", ephemeral=True)

    # Record function usage if you have such a function
    record_function_usage(interaction.user.id, 'addusersfromchannel', interaction.channel_id)





@tree.command(name='comandos', description="Show available commands")
async def comandos(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    help_text = """
    **Comandos Disponibles:**
    
    `/checklist` - Muestra checklist del path, en qué semana vas y tareas cumplidas.
    `/status` - Muestra el progreso de las tareas, marcando las tareas cumplidas y no cumplidas.
    `/complete` - Marca una tarea como completada y agrega URL como evidencia.
    `/addpath` - Agrega un nuevo path.
    `/addtopic` - Agrega un nuevo tema a un path existente.
    `/addtask` - Agrega una nueva tarea a un tema existente.
    `/linkchannel` - Vincula un canal a un path existente.
    `/channel` - Muestra el nombre y el ID del canal actual.
    `/path` - Muestra el nombre del path asociado al canal actual.
    `/useractivity` - Muestra la actividad del usuario.
    `/functionusage` - Muestra el uso de la función.
    `/nps` - Calcula el NPS.
    `/satisfaction` - Calcula la satisfacción promedio.
    `/commandmetrics`- Command to see the table of command usage metrics.
    `/pregunta`- Command to get help from Hacki.ai.
    """
    await interaction.response.send_message(help_text, ephemeral=True)
    record_function_usage(interaction.user.id, 'comandos', channel_id)
    
    
    

@tree.command(name="commandmetrics", description="Show command metrics")
@app_commands.describe(period="Predefined period (last_7_days, last_30_days, all or custom)", start_date="Custom start date (YYYY-MM-DD)", metric_type="Type of metric (channels or paths)")
@app_commands.choices(
    period=[
        app_commands.Choice(name='Last 7 Days', value='last_7_days'),
        app_commands.Choice(name='Last 30 Days', value='last_30_days'),
        app_commands.Choice(name='All', value='all'),
        app_commands.Choice(name='Custom', value='custom')
    ],
    metric_type=[
        app_commands.Choice(name='By Channels', value='channels'),
        app_commands.Choice(name='By Paths', value='paths')
    ]
)
async def commandmetrics(
    interaction: discord.Interaction, 
    period: Optional[app_commands.Choice[str]] = None, 
    start_date: Optional[str] = None, 
    metric_type: Optional[app_commands.Choice[str]] = None
):
    await interaction.response.defer(ephemeral=True)
    
    print(f"Commandmetrics command called with period: {period}, start_date: {start_date}, metric_type: {metric_type}")

    if period:
        if period.value == 'last_7_days':
            start_date = datetime.now(timezone.utc) - timedelta(days=7)
        elif period.value == 'last_30_days':
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        elif period.value == 'all':
            start_date = None
        elif period.value == 'custom' and start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)

    end_date = datetime.now(timezone.utc) if period and period.value != 'all' else None

    total_count = 0
    response_title = "**Command Metrics**\n"
    response = ""

    if metric_type and metric_type.value == 'channels':
        print(f"Fetching command metrics by channel from {start_date} to {end_date}")
        metrics = get_command_metrics_by_channel(start_date, end_date)
        print(f"Fetched channel metrics: {metrics}")
        response_title = "**Command Metrics by Channel**\n"
        for channel_id, commands in metrics.items():
            channel_name = get_channel_name(channel_id) or "Unknown Channel"
            response += f"\nChannel: {channel_name} (ID: {channel_id})\n"
            response += '```\n'
            response += '{:<20} {:<10}\n'.format('Command', 'Count')
            response += '-' * 30 + '\n'
            channel_total = 0
            for command, count in commands.items():
                response += '{:<20} {:<10}\n'.format(command, count)
                channel_total += count
            response += '-' * 30 + '\n'
            response += '{:>20} {:<10}\n'.format('Total', channel_total)
            response += '```\n'
            total_count += channel_total
    elif metric_type and metric_type.value == 'paths':
        print(f"Fetching command metrics by path from {start_date} to {end_date}")
        metrics = get_command_metrics_by_path(start_date, end_date)
        print(f"Fetched path metrics: {metrics}")
        response_title = "**Command Metrics by Path**\n"
        for path_id, commands in metrics.items():
            path_name = get_path_name(path_id) or "Unknown Path"
            response += f"\nPath: {path_name} (ID: {path_id})\n"
            response += '```\n'
            response += '{:<20} {:<10}\n'.format('Command', 'Count')
            response += '-' * 30 + '\n'
            path_total = 0
            for command, count in commands.items():
                response += '{:<20} {:<10}\n'.format(command, count)
                path_total += count
            response += '-' * 30 + '\n'
            response += '{:>20} {:<10}\n'.format('Total', path_total)
            response += '```\n'
            total_count += path_total
    else:
        print(f"Fetching all command metrics from {start_date} to {end_date}")
        metrics = get_command_metrics(start_date, end_date)
        print(f"Fetched all metrics: {metrics}")
        response_title = "**Command Metrics**\n"
        response += '```\n'
        response += '{:<20} {:<10}\n'.format('Command', 'Count')
        response += '-' * 30 + '\n'
        for command, count in metrics.items():
            response += '{:<20} {:<10}\n'.format(command, count)
            total_count += count
        response += '-' * 30 + '\n'
        response += '{:>20} {:<10}\n'.format('Total', total_count)
        response += '```\n'

    response = response_title + f"**Total Count: {total_count}**\n\n" + response
    await interaction.followup.send(response, ephemeral=True)

# %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    



@tree.command(name="functionusage", description="Show function usage")
async def functionusage(interaction: discord.Interaction, function_name: str):
    function_users = get_function_usage(function_name)
    print(f"Raw function users data: {function_users}")
    user_list = [user_dict['user_id'] for _, user_dict in function_users]
    print(f"User lists extracted: {user_list}")
    await interaction.response.send_message(f"Users who used {function_name}: {', '.join(user_list)}", ephemeral=True)

        
client.run(DISCORD_TOKEN)






# Command to interact with the AI API
# @tree.command(name="ask-ai", description="Ask the AI a question or review code")
# @app_commands.describe(question='Your question or code to review')
# async def ask_ai(interaction: discord.Interaction, question: str):
#     url = "http://20.15.202.125:8080/generate"
#     payload = {
#         "inputs": question,
#         "parameters": {
#             "max_new_tokens": 500
#         }
#     }
#     headers = {
#         "Content-Type": "application/json"
#     }

#     response = requests.post(url, json=payload, headers=headers)

#     if response.status_code == 200:
#         ai_response = response.json().get('generated_text', 'No response from AI.')
#         await interaction.response.send_message(f"AI Response:\n```{ai_response}```")
#     else:
#         await interaction.response.send_message(f"Failed to get response from AI. Status code: {response.status_code}")