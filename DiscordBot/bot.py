# bot.py
import discord
from discord.ext import commands
import os
import json
import logging
import re
import requests
from report import Report, State
import pdb
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch.nn as nn
import pandas as pd

knownViolators = {} # global! keeps track over all messages

# code for importing and running automatic bot
class Critic(nn.Module):
    def __init__(self, hidden_size):
        super().__init__()
        self.critic = nn.Sequential(
            nn.Linear(hidden_size, 2048),
            nn.ReLU(),
            nn.Linear(2048, 2048),
            nn.ReLU(),
            nn.Linear(2048, 1)
        )

    def forward(self, hidden_vec):
        return self.critic(hidden_vec)   # returns shape [batch_size, 1]


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


base_model_name = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
model = AutoModelForCausalLM.from_pretrained(
    base_model_name,
    output_hidden_states=True
).to(device)
model.eval()

tokenizer = AutoTokenizer.from_pretrained(
    base_model_name,
    padding_side="left"
)

# create new critic and load trained values into it
hidden_size = model.config.hidden_size 
print("hidden size of tiny llama:", hidden_size)
critic = Critic(hidden_size).to(device)
critic_load_path = "critic_sextortion.pt"
critic.load_state_dict(torch.load(critic_load_path, map_location=device))
critic.eval()
print(f"Loaded critic weights from {critic_load_path}")

# use critic to predict if message is from perpetrator of sextortion
def predict_sextortion(text: str) -> float:
    """
    Returns a float in [0,1], the critic’s predicted probability
    that ‘text’ is a sextortion message.
    """
    # tokenize message
    toks = tokenizer(
        text,
        return_tensors="pt",
        padding=True,
        truncation=True
    )
    
    input_ids      = toks["input_ids"].to(device)      # [1, seq_len]
    attention_mask = toks["attention_mask"].to(device)

    # forward pass through TinyLlama (to get hidden states)
    with torch.no_grad():
        outputs = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_hidden_states=True,
            return_dict=True
        )
        # take the last hidden state for the last token (bc tinyllama is causal, reps all previous tokens)
        last_token_hidden = outputs.hidden_states[-1][:, -1, :]       # [1, seq_len, hidden_size]
        

        # forward pass through critic → raw score
        score = critic(last_token_hidden).view(-1)                # [1]

        # convert to prob via sigmoid
        prob = torch.sigmoid(score).item()             # Python float in [0,1]
        
        return prob

# Set up logging to the console
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# There should be a file called 'tokens.json' inside the same folder as this file
token_path = 'tokens.json'
if not os.path.isfile(token_path):
    raise Exception(f"{token_path} not found!")
with open(token_path) as f:
    # If you get an error here, it means your token is formatted incorrectly. Did you put it in quotes?
    tokens = json.load(f)
    discord_token = tokens['discord']


class ModBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='.', intents=intents)
        self.group_num = None
        self.mod_channels = {}  # Map from guild to the mod channel id for that guild
        self.reports = {}  # Map from user IDs to the state of their report
        self.reaction_to_report = {}
        self.past_reports = {}

    async def on_ready(self):
        print(f'{self.user.name} has connected to Discord! It is these guilds:')
        for guild in self.guilds:
            print(f' - {guild.name}')
        print('Press Ctrl-C to quit.')

        # Parse the group number out of the bot's name
        match = re.search('[gG]roup (\d+) [bB]ot', self.user.name)
        if match:
            self.group_num = match.group(1)
        else:
            raise Exception("Group number not found in bot's name. Name format should be \"Group # Bot\".")

        # Find the mod channel in each guild that this bot should report to
        for guild in self.guilds:
            for channel in guild.text_channels:
                if channel.name == f'group-{self.group_num}-mod':
                    self.mod_channels[guild.id] = channel

    async def on_message(self, message):
        '''
        This function is called whenever a message is sent in a channel that the bot can see (including DMs).
        Currently the bot is configured to only handle messages that are sent over DMs or in your group's "group-#" channel.
        '''
        # Ignore messages from the bot
        if message.author.id == self.user.id:
            return

        # Check if this message was sent in a server ("guild") or if it's a DM
        if message.guild:
            await self.handle_channel_message(message)
        else:
            await self.handle_dm(message)

    async def handle_dm(self, message):
        # Handle a help message
        if message.content == Report.HELP_KEYWORD:
            reply = "Use the `report` command to begin the reporting process.\n"
            reply += "Use the `cancel` command to cancel the report process.\n"
            await message.channel.send(reply)
            return

        author_id = message.author.id
        responses = []

        # Only respond to messages if they're part of a reporting flow
        if author_id not in self.reports and not message.content.startswith(Report.START_KEYWORD):
            return

        # If we don't currently have an active report for this user, add one
        if author_id not in self.reports:
            self.reports[author_id] = Report(self, message.author)

        # Let the report class handle this message; forward all the messages it returns to uss
        responses = await self.reports[author_id].handle_message(message)
        for r in responses:
            await message.channel.send(r)

        # If the report is complete or cancelled, remove it from our map
        if self.reports[author_id].report_complete():
            self.reports.pop(author_id)

    async def on_reaction_add(self, reaction, user):
        if user == self.user:
            return
        report = self.reaction_to_report.get(reaction.message.id)
        del self.reaction_to_report[reaction.message.id]
        if report == None:
            return
        if report.state == State.AWAITING_MODERATION:
            if str(reaction.emoji) == "✅":
                await reaction.message.channel.send("Report acknowledged, determining severity")
                msg = await reaction.message.channel.send("Select the severity of the infraction:"
                                                          "select 🔹 for a minor infraction or 🔷 for a major infraction")
                self.reaction_to_report[msg.id] = report
                report.state = State.DETERMINE_SEVERITY
                await msg.add_reaction("🔹")
                await msg.add_reaction("🔷")
            if str(reaction.emoji) == "❌":
                await reaction.message.channel.send("Report dismissed, closing report.")
                report.state = State.REPORT_COMPLETE
        if report.state == State.DETERMINE_SEVERITY:
            if str(reaction.emoji) == "🔹":
                if report.message.author.name not in self.past_reports:
                    self.past_reports[report.message.author.name] = 1
                else:
                    self.past_reports[report.message.author.name] += 1
                match self.past_reports[report.message.author.name]:
                    case 1 | 2:
                        await reaction.message.channel.send(f"Warning user {report.message.author.display_name}, minor "
                                                            f"infraction number {self.past_reports[report.message.author.name]}")
                        await report.message.author.send("We've noticed that your recent message violated our"
                                                         " community guidelines. Please review our policies to "
                                                         "avoid further action. Continued violations may result "
                                                         "in suspension or removal from the platform.")
                        await reaction.message.channel.send("Report complete, closing report.")
                        report.state = State.REPORT_COMPLETE
                    case 3:
                        await reaction.message.channel.send(
                            f"Simulating suspending user {report.message.author.display_name}, minor "
                            f"infraction number {self.past_reports[report.message.author.name]}")
                        await report.message.author.send("Your account has been temporarily suspended due to repeated "
                                                         "violations of our community policies. You may log back in after "
                                                         "7 days. Please review our guidelines to continue participating safely.")
                        await reaction.message.channel.send("Report complete, closing report.")
                        report.state = State.REPORT_COMPLETE
                    case n if n >= 4:
                        await reaction.message.channel.send(
                            f"Simulating banning user {report.message.author.display_name}, minor "
                            f"infraction number {self.past_reports[report.message.author.name]}")
                        await report.message.author.send(
                            "Your account has been permanently removed due to a serious violation of"
                            " our community standards. If you believe this was an error, you may submit"
                            " an appeal within 7 days.")
                        await reaction.message.channel.send("Report complete, closing report.")
                        report.state = State.REPORT_COMPLETE
            if str(reaction.emoji) == "🔷":
                await reaction.message.channel.send(
                    f"Simulating banning user {report.message.author.display_name}, major infraction")
                await report.message.author.send(
                    "Your account has been permanently removed due to a serious violation of"
                    " our community standards. If you believe this was an error, you may submit"
                    " an appeal within 7 days.")
                await reaction.message.channel.send("Report complete, closing report.")
                report.state = State.REPORT_COMPLETE

        if self.reports[report.author.id].report_complete():
            self.reports.pop(report.author.id)

    async def handle_channel_message(self, message):
        # Only handle messages sent in the "group-#" channel
        if not message.channel.name == f'group-{self.group_num}':
            return

        # Forward the message to the mod channel
        mod_channel = self.mod_channels[message.guild.id]
        await mod_channel.send(f'Forwarded message:\n{message.author.name}: "{message.content}"')
        scores = self.eval_text(message.content)
        await mod_channel.send(self.code_format(scores))
        # if score is above 0.4 confidence warn channel that the message may be an instance of sextortion, to seek help 
        # not send nudes to people you don't trust HELP CHAT!
        if 0.4 < scores < 0.5:
            await message.channel.send("Warning! Please be warry of sharing intimate images of yourself. People online may not be who they claim they are and relationships can change. Shared nude images can be used as blackmail against you in the future.")
        if scores >= 0.5:
            await message.channel.send("Warning! The previous message was flagged by our automated content moderation system "
                                       "for signs of sextortion. If someone is threatening to share your intemate content, there is hope! Please" 
                                       " reach out to a loved one for support and cease complying with demands. If you feel comfortable,"
                                       " please report the user to law enforcement. Our content moderation team is already reviewing the situation."
                                       "  Additionally, if you are under the age of 18, you can go to https://takeitdown.ncmec.org/ to have all nude images of you removed from the internet.")
        if scores > 0.5:
            report = Report(self, self.user, initial_state=State.FINISHED_USER_REPORTING_FLOW)
            report.message = message
            self.reports[self.user.id] = report
            
            # update known violators
            if message.author.name in knownViolators:
                # repeat offender, increase count of violations
                knownViolators[message.author.name] += 1
            else:
                knownViolators[message.author.name] = 0
            await mod_channel.send(f'Automatic report triggered from user {message.author.name}. User has {knownViolators[message.author.name]} previous automatic flags.')
            self.TOS_check = await mod_channel.send(
                f"Does the content violate our standing policies? Select yes (✅) or no (❌)")
            await self.TOS_check.add_reaction("✅")
            await self.TOS_check.add_reaction("❌")
            report.state = State.AWAITING_MODERATION
            report.client.reaction_to_report[self.TOS_check.id] = report

    def eval_text(self, message):
        ''''
        TODO: Once you know how you want to evaluate messages in your channel,
        insert your code here! This will primarily be used in Milestone 3.
        '''
        score = predict_sextortion(message)
        return score

    def code_format(self, text):
        ''''
        TODO: Once you know how you want to show that a message has been
        evaluated, insert your code here for formatting the string to be
        shown in the mod channel.
        '''
        return f"Evaluated: {text}"


client = ModBot()
client.run(discord_token)
