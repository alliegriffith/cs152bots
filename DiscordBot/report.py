from enum import Enum, auto
import discord
import re
import json

class State(Enum):
    REPORT_START = auto()
    AWAITING_MESSAGE = auto()
    IN_USER_REPORTING_FLOW = auto()
    AWAITING_ADDITIONAL_DETAILS = auto()
    FINISHED_USER_REPORTING_FLOW = auto()
    AWAITING_MODERATION = auto()
    DETERMINE_SEVERITY = auto()
    REPORT_COMPLETE = auto()

class Report:
    START_KEYWORD = "report"
    CANCEL_KEYWORD = "cancel"
    HELP_KEYWORD = "help"

    def __init__(self, client, author):
        self.state = State.REPORT_START
        self.client = client
        self.author = author
        self.message = None
        with open("user_report_tree.json", "r") as f:
            self.user_report_tree = json.load(f)

        self.current_node = self.user_report_tree
        self.report_path = []  # list of keys chosen so far
        self.author_message = ""  # 500 character message submitted by author
        self.author_skipped = False
    
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
                reported_message = await channel.fetch_message(int(m.group(3)))
            except discord.errors.NotFound:
                return ["It seems this message was deleted or never existed. Please try again or say `cancel` to cancel."]

            # Here we've found the message - it's up to you to decide what to do next!
            self.state = State.IN_USER_REPORTING_FLOW
            self.message = reported_message
        
        # traverse user_report_tree
        if self.state == State.IN_USER_REPORTING_FLOW:
            node = self.current_node
            reply = ""

            # if there are options on current ndoe, try to move to next node (given digit)
            if node.get("options") and message.content.strip().isdigit():
                choice_idx = int(message.content.strip()) - 1
                options = list(node["options"].keys())
                skip_idx = len(options)

                # user selects tree option
                if 0 <= choice_idx < len(options):
                    selected = options[choice_idx]
                    self.report_path.append(selected)
                    node = node["options"][selected]
                    self.current_node = node

                # user selects skip option
                elif choice_idx == skip_idx:
                    self.report_path.append("Skipped questionnaire")
                    self.author_skipped = True
                    self.state = State.AWAITING_ADDITIONAL_DETAILS
                    return ["Skipping questionnaire and sending report.\n" "Please provide any additional details to help our moderators best address your situation. (500 characters, or enter \'None\' if you have no notes.)\n"]
                
                else:
                    return ["Invalid choice. Please pick one of the numbers above"]
            
            # display warning then prompt
            if node.get("warning"):
                reply += f"{node['warning']}\n\n"
            if node.get("prompt"):
                reply += f"{node['prompt']}\n"

            # display options
            if node.get("options"):
                for idx, opt in enumerate(node["options"].keys(), start=1):
                    reply += f"` {idx}. ` {opt}\n"
                
                # display skip option
                reply += f"` {len(node['options'])+1}. ` Skip questionnaire and send report\n"
                reply += f"Please enter a number from the list above.\n"

                return [reply]
                
            else:
                reply += "Please provide any additional details to help our moderators best address your situation. (500 characters, or enter \'None\' if you have no notes.)\n"
                if node.get("final_note"):
                    reply += f"{node['final_note']}\n"
                self.state = State.AWAITING_ADDITIONAL_DETAILS
                return [reply]

        
        if self.state == State.AWAITING_ADDITIONAL_DETAILS:
            self.author_message = message.content[:500]
            self.state = State.FINISHED_USER_REPORTING_FLOW

        if self.state == State.FINISHED_USER_REPORTING_FLOW:
            mod_channel = None
            for guild in self.client.guilds:
                if self.message.guild.id in self.client.mod_channels:
                    mod_channel = self.client.mod_channels[self.message.guild.id]
                    break

            if mod_channel:
                report_notification = "🚨 A user has submitted a report!"
                report_notification += "🚨 A user has submitted a report!"
                report_notification += f"Reported message from {self.message.author.display_name}:"
                report_notification += f"> {self.message.content}"
                report_notification += f"Message link: {self.message.jump_url}"

                author_information = f"Information provided by the author"
                author_information += "------------------------------------------\n"
                author_information += "User report path:\n"
                for key in self.report_path:
                    author_information += f"` -> `{key}\n"
                author_information += f"Additional details provided by author:\n{self.author_message}\n"
                author_information += "------------------------------------------\n"
                await mod_channel.send(report_notification + author_information)

                self.TOS_check = await mod_channel.send(f"Does the content violate our standing policies? Select yes (✅) or no (❌)")
                await self.TOS_check.add_reaction("✅")
                await self.TOS_check.add_reaction("❌")
                self.state = State.AWAITING_MODERATION
                self.client.reaction_to_report[self.TOS_check.id] = self

            return [
                "Thank you for your report. Our moderators have been notified and will address your report immediately.",
            ]

        return []
    
    def report_complete(self):
        return self.state == State.REPORT_COMPLETE