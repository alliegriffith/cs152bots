from enum import Enum, auto
import discord
import re

class State(Enum):
    REPORT_START = auto()
    AWAITING_MESSAGE = auto()
    MESSAGE_IDENTIFIED = auto()
    IN_USER_REPORTING_FLOW = auto()
    AWAITING_MODERATION = auto()
    DETERMINE_SEVERITY = auto()
    REPORT_COMPLETE = auto()

class Report:
    START_KEYWORD = "report"
    CANCEL_KEYWORD = "cancel"
    HELP_KEYWORD = "help"

    def __init__(self, client):
        self.state = State.REPORT_START
        self.client = client
        self.message = None
    
    async def handle_message(self, message):
        '''
        This function makes up the meat of the user-side reporting flow. It defines how we transition between states and what 
        prompts to offer at each of those states. You're welcome to change anything you want; this skeleton is just here to
        get you started and give you a model for working with Discord. 
        '''

        if message.content == self.CANCEL_KEYWORD:
            self.state = State.REPORT_COMPLETE
            return ["Report cancelled."]
        
        if self.state == State.REPORT_START:
            reply =  "Thank you for starting the reporting process. "
            reply += "Say `help` at any time for more information.\n\n"
            reply += "Please copy paste the link to the message you want to report.\n"
            reply += "You can obtain this link by right-clicking the message and clicking `Copy Message Link`."
            self.state = State.AWAITING_MESSAGE
            return [reply]
        
        if self.state == State.AWAITING_MESSAGE:
            # Parse out the three ID strings from the message link
            m = re.search('/(\d+)/(\d+)/(\d+)', message.content)
            if not m:
                return ["I'm sorry, I couldn't read that link. Please try again or say `cancel` to cancel."]
            guild = self.client.get_guild(int(m.group(1)))
            if not guild:
                return ["I cannot accept reports of messages from guilds that I'm not in. Please have the guild owner add me to the guild and try again."]
            channel = guild.get_channel(int(m.group(2)))
            if not channel:
                return ["It seems this channel was deleted or never existed. Please try again or say `cancel` to cancel."]
            try:
                message = await channel.fetch_message(int(m.group(3)))
            except discord.errors.NotFound:
                return ["It seems this message was deleted or never existed. Please try again or say `cancel` to cancel."]

            # Here we've found the message - it's up to you to decide what to do next!
            self.state = State.MESSAGE_IDENTIFIED
            self.message = message
        
        if self.state == State.MESSAGE_IDENTIFIED:
            mod_channel = None
            for guild in self.client.guilds:
                if message.guild.id in self.client.mod_channels:
                    mod_channel = self.client.mod_channels[message.guild.id]
                    break

            if mod_channel:
                await mod_channel.send("🚨 A user has submitted a report!")
                await mod_channel.send(f"Reported message from {message.author.display_name}:")
                await mod_channel.send(f"> {message.content}")
                await mod_channel.send(f"Message link: {message.jump_url}")
                self.TOS_check = await mod_channel.send(f"Does the content violate our standing policies? Select yes (✅) or no (❌)")
                await self.TOS_check.add_reaction("✅")
                await self.TOS_check.add_reaction("❌")
                self.state = State.AWAITING_MODERATION
                self.client.reaction_to_report[self.TOS_check.id] = self


            return [
                "Thank you for your report. Our moderators have been notified and will take action if necessary.",
            ]

        return []
    

    def report_complete(self):
        return self.state == State.REPORT_COMPLETE
    


    

